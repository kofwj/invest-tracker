"""N1 一句话记账 → 交易草稿：payload、prompt、字段级复核。

AI 只把原话拆成字段，**绝不落库**：写入仍走既有的「提交记录 → POST /transactions」，
与项目「草稿确认后才入账」的立场同构。

为什么这里不套 `ai_payload.validate_output`：那是**文本**校验器，它的「数字可溯」靠
`_walk_numbers()`，只遍历 int/float、**不解析字符串**。而本用例 payload 里
utterance / available_codes / today 全是字符串 → payload 数字集合为空 → 草稿里的
510880、1.85 会被一律判成「数字不可溯」，strict 模式下整条草稿被丢弃，功能一上线就是死的。
改用字段级复核 + 结构化可溯（`_review_draft`）：
  code           必须命中 available_codes（库外新标的一律拒绝，不许猜）
  quantity/price 必须能在用户原话里找到（找不到就说"没听懂"，不预填来源不明的数字）
  date           只认原话里明写的日期，其余归 null（不让模型算"昨天"，也就没有时区账）
也**不要**给 nl_entry 打开 `TRADE_ADVICE_TERMS` 那类词表：它含「买入 / 卖出」，
而本用例合法的 direction 正是这两个词，一开就满盘拦。
"""
from __future__ import annotations

import json
import logging
import math
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from .ai_client import call_ai, load_ai_config, stamp_ai_warnings
    from .ai_payload import ALLOWED_KEYS, build_payload
    from .database import local_today_iso
    from .market import get_watchlist
except ImportError:
    from ai_client import call_ai, load_ai_config, stamp_ai_warnings
    from ai_payload import ALLOWED_KEYS, build_payload
    from database import local_today_iso
    from market import get_watchlist

ENTRY_MAX_TOKENS = 200
# 交互式等人：30s 是"还愿意盯着转圈"的上限（方案原写 45s）。超时就回落成"没听懂"，
# 绝不拖住表单 —— 手填流程永远是兜底。
ENTRY_TIMEOUT_S = 30
ENTRY_MAX_UTTERANCE = 200
# 候选标的清单上限：持仓 ∪ 关注 ∪ 交易历史合并后可能上百条，越长模型消歧越差、请求越贵。
# 持仓与关注优先（最可能是下一笔），交易历史按最近交易时间降序补足。
ENTRY_AVAILABLE_LIMIT = 200
ENTRY_DIRECTIONS = ("买入", "卖出", "分红", "分红再投资", "申购待确认")
ENTRY_MIN_DATE = "2000-01-01"

HINT = "草稿仅供参考，请核对后提交；AI 不会直接入账"
SHADOW_HINT = "影子模式：仅预览，不会自动填入表单"

SYSTEM_PROMPT = """你是记账助手。只输出一个 JSON 对象，不要解释、不要 markdown 围栏。
字段：code / name / direction / date / quantity / price / fee
硬规则：
1. code 只能从 available_codes 里选，不许编造；选不出来就把 code 置为 null。
2. direction 只能是：买入 / 卖出 / 分红 / 分红再投资 / 申购待确认。
3. quantity 与 price 只能取用户原话里出现的数字，不许换算、不许估算
   （"一手""一万块"这类需要换算的，宁可给 null）。
4. date 只在原话明写了日期（如 2026-09-25、9月25日）时填写；"昨天""上周"一律输出 null。
5. fee 一律输出 null（手续费由系统按费率表自动估算），不要输出 amount。
6. 任何拿不准的字段就输出 null，不要猜。

示例输入：
{"utterance": "昨天 1.85 买了 2000 份红利ETF华泰柏瑞", "available_codes": ["510880 红利ETF华泰柏瑞"], "today": "2026-09-26"}
示例输出：
{"code": "510880", "name": "红利ETF华泰柏瑞", "direction": "买入", "date": null, "quantity": 2000, "price": 1.85, "fee": null}
"""

_FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")
# 千分位逗号（仅当后面正好跟三位数字时才算分隔符，避免把"1,5"这种小数当成数字）
_THOUSANDS_RE = re.compile(r"(?<=\d),(?=\d{3}(?:\D|$))")
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)
# 日期：2025-09-25 / 2026/09/25 / 2025年9月25日 / 9月25日（"9月25"这种省略"日"的写法也算）。
# 日后面的边界不能只看数字，否则"9月1.85""9月25块"会把价格/金额的前半截当成日期抹掉：
#   有「日/号」→ 后面不许直接跟数字；
#   没有「日/号」→ 后面不许是数字、小数点的开头（. 后面跟数字）或「元/块」。
# 句末句点（"9月25."）不算小数点，仍然认；"12月买了 3000 份"里的 3000 也不会被当日期。
_DAY_END = r"(?:\s*[日号](?!\d)|(?!(?:\d|\.\d|元|块)))"
_ISO_DATE_RE = re.compile(r"(\d{4})\s*[-/.]\s*(\d{1,2})\s*[-/.]\s*(\d{1,2})(?!(?:\d|\.\d))")
_CJK_YEAR_DATE_RE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})" + _DAY_END)
_CN_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})" + _DAY_END)
_FULLWIDTH_PUNCT = str.maketrans({"．": ".", "－": "-", "–": "-", "—": "-", "，": ","})
# 方向关键词：只用来**否决**模型给的反向方向，不做正向识别（原话千变万化，正向认定交模型）。
_BUY_TERMS = ("买入", "买进", "买了", "加仓")
_SELL_TERMS = ("卖出", "卖掉", "卖了", "赎回", "清仓", "减仓")
# 紧邻单位：份/股/手/张 后面是数量；元/块 后面是金额。
_SHARE_SUFFIX = ("份", "股", "手", "张")
_MONEY_SUFFIX = ("元", "块")
# "花了 3700 元"这类口径里的 3700 是**总额**，不是单价。
# 只用完整的支出词：单字"花""共"会被标的名称吃掉（梅花生物 / 共进股份）
_SPEND_MARKERS = ("花了", "花掉", "一共", "总共", "合计", "总价", "总计")
# 数字与单位之间可能有空格（"2000  份"），窗口给宽一点再 lstrip
_UNIT_LOOKAHEAD = 4


def _cell(row: Any, index: int, key: str) -> Any:
    if hasattr(row, "keys"):
        try:
            return row[key]
        except Exception:
            return None
    try:
        return row[index]
    except Exception:
        return None


def _add_asset(out: List[str], seen: set, code: Any, name: Any) -> None:
    text = str(code or "").strip()
    if not text or text in seen:
        return
    seen.add(text)
    label = str(name or "").strip() or text
    out.append("%s %s" % (text, label))


def available_assets(conn) -> Optional[List[str]]:
    """["{code} {name}", ...]：持仓(数量>0) ∪ 关注 ∪ 交易历史。

    **持仓是主源**：它读失败就直接返回 None。否则一次读失败会退化成一份残缺（可能为空）的
    清单，被表现出来成"所有代码都不认识"，用户只看到一句"没听懂"、还以为库里没数据。
    关注与交易历史是补充源，单独失败只记日志、清单照给（照 dividend_calendar 的
    「空 vs 读失败」口径）。
    """
    seen: set = set()
    out: List[str] = []
    holdings_ok = True

    try:
        rows = conn.execute("SELECT code, name FROM holdings WHERE quantity > 0").fetchall()
    except Exception:
        logger.exception("ai_entry: holdings failed")
        holdings_ok = False
        rows = []
    for row in rows:
        _add_asset(out, seen, _cell(row, 0, "code"), _cell(row, 1, "name"))

    try:
        watch = get_watchlist(conn) or []
    except Exception:
        logger.exception("ai_entry: watchlist failed")
        watch = []
    for item in watch:
        if isinstance(item, dict):
            _add_asset(out, seen, item.get("code"), item.get("name"))

    try:
        # 已清仓的也要能命中（以前买过、卖光了，下次可能再买），所以并上交易历史；
        # 按最近一笔交易时间降序，超上限时先丢最久没碰过的。
        rows = conn.execute(
            "SELECT code, name, MAX(date) AS last_date FROM transactions "
            "GROUP BY code ORDER BY last_date DESC"
        ).fetchall()
    except Exception:
        logger.exception("ai_entry: transactions failed")
        rows = []
    for row in rows:
        _add_asset(out, seen, _cell(row, 0, "code"), _cell(row, 1, "name"))

    if not holdings_ok:
        return None
    return out[:ENTRY_AVAILABLE_LIMIT]


def _code_name_map(assets: List[str]) -> Dict[str, str]:
    """清单 → {code: name}；名称一律以库里为准，模型给的名字只作参考。"""
    out: Dict[str, str] = {}
    for item in assets:
        parts = str(item or "").strip().split(None, 1)
        if not parts or not parts[0]:
            continue
        out[parts[0]] = parts[1].strip() if len(parts) > 1 else parts[0]
    return out


def _normalize_text(text: str) -> str:
    """全角数字/标点归一 + 去千分位逗号（"１．８５"、"1,850" 都要能对上）。"""
    body = str(text or "").translate(_FULLWIDTH_DIGITS).translate(_FULLWIDTH_PUNCT)
    return _THOUSANDS_RE.sub("", body)


def _code_digits(codes) -> List[str]:
    """候选代码里的纯数字部分（够长才算：太短会把原话里正常的数字也抹掉）。"""
    out: List[str] = []
    for code in codes or ():
        digits = "".join(ch for ch in str(code) if ch.isdigit())
        if len(digits) >= 4:
            out.append(digits)
    return out


def _traceable_body(text: str, codes=None) -> str:
    """可溯数字的来源文本：先抹掉日期段与证券代码 —— 它们不是数量/单价的来源。

    "2025年9月25日 1.85 买了 2000 份" 里只有 1.85 与 2000 可用；日期里的 2025 / 25 与
    "代码 510880" 都必须是空格，否则模型给 price=25 / price=2025 / quantity=510880 也会被放行。
    """
    body = _normalize_text(text)
    body = _ISO_DATE_RE.sub(lambda m: " " * len(m.group(0)), body)
    body = _CJK_YEAR_DATE_RE.sub(lambda m: " " * len(m.group(0)), body)
    body = _CN_DATE_RE.sub(lambda m: " " * len(m.group(0)), body)
    for digits in _code_digits(codes):
        if digits in body:
            body = body.replace(digits, " " * len(digits))
    return body


def _numbers_in_text(text: str, *, codes=None) -> List[float]:
    """原话里的数字（全角/千分位归一；日期分量与证券代码不计）。"""
    out: List[float] = []
    for match in _NUMBER_RE.finditer(_traceable_body(text, codes)):
        try:
            out.append(float(match.group(0)))
        except ValueError:
            continue
    return out


def _text_has_number(text: str, value: Any, *, codes=None) -> bool:
    try:
        target = float(value)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(target):
        return False
    tolerance = max(1e-6, abs(target) * 1e-6)
    return any(abs(item - target) <= tolerance for item in _numbers_in_text(text, codes=codes))


def _hits(numbers: List[float], value: Any) -> bool:
    """value 是否命中 numbers 里的某个数（容差口径与 _text_has_number 一致）。"""
    try:
        target = float(value)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(target):
        return False
    tolerance = max(1e-6, abs(target) * 1e-6)
    return any(abs(item - target) <= tolerance for item in numbers)


def _number_positions(text: str, *, codes=None) -> Tuple[List[float], List[float]]:
    """按紧邻的后缀把原话里的数字分成 (份额/股数, 金额)。

    "2000 份" → 股数；"3700 元" → 金额；"1.85 买了" 两边都不进（不做正向认定）。
    日期与证券代码先被抹掉，所以"9月25日"的 25、"510880" 都不会进任何一组。
    """
    body = _traceable_body(text, codes)
    shares: List[float] = []
    monies: List[float] = []
    for match in _NUMBER_RE.finditer(body):
        try:
            value = float(match.group(0))
        except ValueError:
            continue
        tail = body[match.end() : match.end() + _UNIT_LOOKAHEAD].lstrip()
        if tail[:1] in _SHARE_SUFFIX:
            shares.append(value)
        elif tail[:1] in _MONEY_SUFFIX:
            monies.append(value)
    return shares, monies


def _spend_total_in_text(text: str, *, codes=None) -> Optional[float]:
    """「花了 / 一共 / 合计 3700 元」里的那个总额；没有这种口径就 None。

    只用**完整的支出词**匹配：单字"花""共"会被标的名称吃掉（梅花生物 / 共进股份），
    那会把"买了 2000 份梅花生物 12.5 元"误判成总额对不上。
    """
    body = _traceable_body(text, codes)
    for match in _NUMBER_RE.finditer(body):
        tail = body[match.end() : match.end() + _UNIT_LOOKAHEAD].lstrip()
        if tail[:1] not in _MONEY_SUFFIX:
            continue
        head = body[max(0, match.start() - 6) : match.start()]
        if any(marker in head for marker in _SPEND_MARKERS):
            try:
                return float(match.group(0))
            except ValueError:
                continue
    return None


def _direction_conflict(direction: str, utterance: str) -> bool:
    """原话明确说了卖、模型却给买（或反之）→ True。两边都提到时不否决（多笔留给人看）。"""
    text = _normalize_text(utterance)
    buy = any(term in text for term in _BUY_TERMS)
    sell = any(term in text for term in _SELL_TERMS)
    if direction == "买入" and sell and not buy:
        return True
    if direction == "卖出" and buy and not sell:
        return True
    return False


def _safe_iso(year: Any, month: Any, day: Any) -> Optional[str]:
    try:
        return datetime(int(year), int(month), int(day)).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return None


def explicit_date_in_text(text: str, *, today: str) -> Optional[str]:
    """原话里**明写**的日期；没有就 None（"昨天"这类相对词不在这里算）。

    三种写法都认：2025-09-25 / 2026/09/25 / 2025年9月25日 / 9月25日（"9月25"也行）。
    分两个分支：**带年**的按原话说的年份走（不做任何回退）；**不带年**的才用今天的年，
    并在"年末说月初"这一种语境下回退到去年。
    """
    body = _normalize_text(text)
    match = _ISO_DATE_RE.search(body) or _CJK_YEAR_DATE_RE.search(body)
    if match:
        return _safe_iso(match.group(1), match.group(2), match.group(3))
    match = _CN_DATE_RE.search(body)
    if not match:
        return None
    day = str(today or "")[:10]
    try:
        year = int(day[:4])
        month_now = int(day[5:7])
    except (ValueError, IndexError):
        return None
    iso = _safe_iso(year, match.group(1), match.group(2))
    if iso and iso > day:
        # 只有"年末说月初"（说的是 12 月、今天在 1-2 月）才算跨年回退；
        # 其余未来日期一律不猜，与带年分支同一口径：置空，交给前端补默认的今天。
        if int(match.group(1)) == 12 and month_now <= 2:
            return _safe_iso(year - 1, match.group(1), match.group(2))
        return None
    return iso


def _json_object(raw_text: str) -> Optional[Dict[str, Any]]:
    """允许 ``` 围栏与首尾杂字；拿不到对象就 None。"""
    raw = str(raw_text or "").strip()
    match = _FENCE_RE.search(raw)
    if match:
        raw = match.group(1).strip()
    try:
        data = json.loads(raw)
    except Exception:
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(raw[start : end + 1])
        except Exception:
            return None
    return data if isinstance(data, dict) else None


def _positive_number(raw: Any) -> Optional[float]:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    return value


def _review_draft(
    raw_text: str,
    *,
    allowed_names: Dict[str, str],
    utterance: str,
    today: str,
) -> Dict[str, Any]:
    """字段级复核：任一失败即拒绝，**不产生半截草稿**。

    返回 {"draft": dict|None, "reason": str, "warnings": [...]}；reason 与端点 mode 同名，
    失败原因不用二次翻译。
    """
    warnings: List[str] = []
    data = _json_object(raw_text)
    if data is None:
        return {"draft": None, "reason": "unparsable", "warnings": warnings}

    code = str(data.get("code") or "").strip()
    if not code or code not in allowed_names:
        # 库里没有这个代码就不给草稿（拍板点 1：不许猜库外新标的）。用户手输一次之后它自然
        # 进清单、下次就能识别 —— 代价是第一次要手填，收益是永远不会写错代码。
        return {"draft": None, "reason": "unknown_code", "warnings": warnings}

    direction = str(data.get("direction") or "").strip()
    if direction not in ENTRY_DIRECTIONS:
        return {"draft": None, "reason": "invalid_direction", "warnings": warnings}

    # 方向是唯一没有数字可溯的字段，而"买反了"会直接写错账：所以只做**反向否决**
    # （原话明确说了卖出、模型却给买入 → 拒绝），正向识别仍交给模型。
    if _direction_conflict(direction, utterance):
        warnings.append("direction 与原话里的买卖词矛盾")
        return {"draft": None, "reason": "direction_conflict", "warnings": warnings}

    quantity = _positive_number(data.get("quantity"))
    price = _positive_number(data.get("price"))
    if quantity is None or price is None:
        return {"draft": None, "reason": "invalid_value", "warnings": warnings}

    # 数字必须能在原话里找到：宁可说"没听懂"，也不预填一个来源不明的价格/数量。
    # 日期分量与证券代码不算来源（否则"9月25日"的 25、"510880" 这个代码都能冒充数量/单价）。
    codes = list(allowed_names.keys())
    if not _text_has_number(utterance, quantity, codes=codes):
        warnings.append("quantity 未在原话中出现")
        return {"draft": None, "reason": "untraceable_number", "warnings": warnings}
    if not _text_has_number(utterance, price, codes=codes):
        warnings.append("price 未在原话中出现")
        return {"draft": None, "reason": "untraceable_number", "warnings": warnings}

    # 位置证据（只否决"张冠李戴"，不做正向认定）：份额位置（份/股/手/张）的数字不能当单价，
    # 金额位置（元/块）的数字不能当股数。
    shares, monies = _number_positions(utterance, codes=codes)
    if _hits(monies, quantity) and not _hits(shares, quantity):
        warnings.append("quantity 取自「元」金额位置")
        return {"draft": None, "reason": "unit_conflict", "warnings": warnings}
    if _hits(shares, price) and not _hits(monies, price):
        warnings.append("price 取自「份/股」数量位置")
        return {"draft": None, "reason": "unit_conflict", "warnings": warnings}
    # 原话既然写了「份/股/手/张」，数量就必须来自那一组，不许取别的数字
    # （"1.85 买了 2000 份 510880" 里把代码当数量，靠这条拦住）。
    if shares and not _hits(shares, quantity):
        warnings.append("quantity 未命中「份/股/手/张」前面的数字")
        return {"draft": None, "reason": "unit_conflict", "warnings": warnings}

    # 「花了/一共 X 元」里的 X 是总额：与 数量×单价 对不上就拒绝 ——
    # 否则模型把总额当单价，草稿会凭空多出好几个数量级的金额。
    total = _spend_total_in_text(utterance, codes=codes)
    if total is not None and abs(quantity * price - total) > max(0.5, abs(total) * 0.01):
        warnings.append("数量×单价 与「花了/一共」的总额对不上")
        return {"draft": None, "reason": "amount_mismatch", "warnings": warnings}

    # 日期只认原话里明写的那一个，模型给的只作对照（这里的"可溯"对象是用户原话）：
    # "昨天"不猜，于是容器时区与浏览器时区的差异都不会渗进账本。
    date = explicit_date_in_text(utterance, today=today)
    model_date = str(data.get("date") or "").strip()[:10]
    if model_date and model_date != date:
        warnings.append("date 以原话为准，模型给的 %s 已忽略" % model_date)
    if date and not (ENTRY_MIN_DATE <= date <= str(today)[:10]):
        warnings.append("date 超出可用范围，已置空: %s" % date)
        date = None

    name = allowed_names.get(code) or code
    model_name = str(data.get("name") or "").strip()
    if model_name and model_name != name:
        warnings.append("name 以库内为准，模型给的 %s 已忽略" % model_name[:40])

    return {
        "draft": {
            "code": code,
            "name": name,
            "direction": direction,
            "date": date,
            "quantity": quantity,
            "price": price,
            # fee 不猜（拍板点 2）：交给前端既有费率表的自动估算。
            "fee": None,
        },
        "reason": "",
        "warnings": warnings,
    }


def entry_messages(payload: Dict[str, Any]) -> List[Dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def _payload_from_assets(utterance: str, assets: List[str], day: str) -> Dict[str, Any]:
    payload = build_payload(
        "nl_entry",
        utterance=str(utterance or "")[:ENTRY_MAX_UTTERANCE],
        available_codes=assets,
        today=day,
    )
    if set(payload) != ALLOWED_KEYS["nl_entry"]:
        raise AssertionError("nl_entry payload keys drifted: %s" % sorted(payload))
    return payload


def assemble_entry_payload(conn, utterance: str, *, today: Optional[str] = None) -> Dict[str, Any]:
    """先取候选清单再按白名单构造 payload；读失败直接抛（调用方转成 blocked）。"""
    day = str(today or local_today_iso())[:10]
    assets = available_assets(conn)
    if assets is None:
        raise RuntimeError("asset universe unavailable")
    return _payload_from_assets(utterance, assets, day)


def _failure_mode(reason: str) -> str:
    if reason in ("timeout", "budget", "disabled", "feature_disabled", "not_configured"):
        return reason
    return "blocked"


def _result(
    *,
    mode: str,
    draft: Optional[Dict[str, Any]] = None,
    warnings=None,
    model: str = "",
    reason: str = "",
    shadow: bool = False,
) -> Dict[str, Any]:
    return {
        "ok": draft is not None,
        "mode": mode,
        "draft": draft,
        "warnings": list(warnings or []),
        "model": model or "",
        "reason": reason or "",
        "shadow": bool(shadow),
        "hint": SHADOW_HINT if shadow else HINT,
    }


def parse_entry_draft(conn, utterance: str, *, today: Optional[str] = None) -> Dict[str, Any]:
    """一句话 → 交易草稿。永不抛；失败给 mode，不给半截草稿。"""
    day = str(today or local_today_iso())[:10]
    text = str(utterance or "").strip()
    if not text:
        return _result(mode="unparsable", reason="empty_utterance")
    if len(text) > ENTRY_MAX_UTTERANCE:
        return _result(mode="unparsable", reason="utterance_too_long")

    cfg = load_ai_config(conn)
    if not cfg.enabled:
        return _result(mode="disabled", model=cfg.model)
    if not bool(cfg.features.get("nl_entry")):
        # 用例关闭时不取数、不调模型（与 N6 同口径）。
        return _result(mode="feature_disabled", model=cfg.model)

    try:
        assets = available_assets(conn)
    except Exception:
        logger.exception("parse_entry_draft: available_assets raised")
        assets = None
    # 这两条是"本地就能确定"的原因，所以 mode 直接给具体值 —— 前端是按 mode 查人话表的，
    # 都塞进 blocked 会让新用户看到"AI 暂时不可用"，而不是"先手填第一笔"。
    if assets is None:
        return _result(mode="assets_unavailable", reason="assets_unavailable", model=cfg.model)
    if not assets:
        return _result(mode="empty_universe", reason="empty_universe", model=cfg.model)

    try:
        conn.commit()
    except Exception:
        pass

    try:
        payload = _payload_from_assets(text, assets, day)
    except Exception:
        logger.exception("parse_entry_draft: payload failed")
        return _result(mode="blocked", reason="payload_failed", model=cfg.model)

    result = call_ai(
        conn,
        cfg,
        "nl_entry",
        entry_messages(payload),
        max_tokens=ENTRY_MAX_TOKENS,
        # 拆字段要的是稳不是灵：温度 0，同一个说法尽量给同一份草稿。
        temperature=0.0,
        timeout_seconds=ENTRY_TIMEOUT_S,
    )
    if not result.get("ok"):
        reason = str(result.get("reason") or "blocked")
        return _result(mode=_failure_mode(reason), reason=reason, model=cfg.model)

    reviewed = _review_draft(
        str(result.get("text") or ""),
        allowed_names=_code_name_map(assets),
        utterance=text,
        today=day,
    )
    try:
        stamp_ai_warnings(conn, result.get("audit_id"), reviewed.get("warnings") or [])
    except Exception:
        logger.exception("parse_entry_draft: stamp warnings failed")

    if reviewed.get("draft") is None:
        reason = str(reviewed.get("reason") or "unparsable")
        return _result(mode=reason, reason=reason, warnings=reviewed.get("warnings"), model=cfg.model)

    return _result(
        mode="ok",
        draft=reviewed.get("draft"),
        warnings=reviewed.get("warnings"),
        model=cfg.model,
        # 影子模式与 A3 同语义：照常调用、照写审计，但**不生效**（前端只预览、不填表）。
        shadow=bool(cfg.shadow_mode),
    )