import os
import threading
import time
import logging
from typing import Dict

import requests

logger = logging.getLogger(__name__)

# Short in-process cache to cut Eastmoney chatter (summary + alerts in same minute).
# Keyed by the resolved Eastmoney secid (e.g. "1.000001" for the SSE index,
# "0.000001" for the stock 000001) so the same numeric code fetched under
# different secids never cross-contaminates quotes.
_QUOTE_CACHE_LOCK = threading.Lock()
_QUOTE_CACHE: Dict[str, dict] = {}  # secid -> {quote, ts}
_CACHE_TTL = max(0, int(os.environ.get("MARKET_QUOTE_CACHE_SECONDS", "120")))


def clear_quote_cache() -> None:
    """Test / admin helper."""
    with _QUOTE_CACHE_LOCK:
        _QUOTE_CACHE.clear()


def eastmoney_sec_id(code: str) -> str:
    """Eastmoney secid: A股/深市ETF=0.xxx，上市沪市股票/ETF/REIT=1.xxx。"""
    c = str(code or "").strip().lower().replace("f", "")
    if c.startswith(("6", "5")):
        return f"1.{c}"
    return f"0.{c}"


def tencent_symbol(code: str) -> str:
    """腾讯行情符号：sh/sz/bj + 6 位代码。

    直接复用东方财富的 secid 前缀（1=沪、0=深），北交所单列。
    """
    raw = str(code or "").strip().lower()
    # 场外基金（f 前缀）不走行情接口，直接判空，避免把 f002864 当成深市 002864 去查
    if raw.startswith("f"):
        return ""
    c = raw
    if not (c.isdigit() and len(c) == 6):
        return ""
    if c.startswith(("4", "8", "9")):
        return f"bj{c}"
    secid = eastmoney_sec_id(c)
    return ("sh" if secid.startswith("1.") else "sz") + c


def fetch_tencent_quotes(codes):
    """腾讯行情兜底，返回结构与 fetch_eastmoney_quotes 一致。

    为什么需要：东方财富的实时报价接口（push2/push2delay 的 /api/qt/*）会整段不可用
    —— 实测 TLS 握手成功、证书正常，但请求发出后远端直接断开（RemoteDisconnected），
    东财其他域名与它的 K 线接口（push2his）却正常；本机换网络同样失败，所以不是
    服务器 IP 被封，是那个接口本身关掉/改了。而 qt.gtimg.cn 一直可用（K 线走的
    就是腾讯这条线），所以拿它兜底，否则一次报价故障会让当天快照沿用旧价、
    当日收益显示成 0 并污染后续所有指标。
    """
    symbol_to_code = {}
    for c in codes:
        sym = tencent_symbol(c)
        if sym:
            symbol_to_code[sym] = str(c).strip().lower().replace("f", "")
    if not symbol_to_code:
        return {}

    quotes = {}
    symbols = list(symbol_to_code)
    for i in range(0, len(symbols), 60):
        batch = symbols[i : i + 60]
        # 整批（请求 + 解析）都兜住：兜底路径自身出问题不能反过来把抓价搞崩，
        # 最坏就是这一批没有价格，保持"取不到价 → 保留旧价"的原有语义。
        try:
            res = requests.get(
                "https://qt.gtimg.cn/q=" + ",".join(batch),
                timeout=8,
                headers={"Referer": "https://gu.qq.com/", "User-Agent": "Mozilla/5.0"},
            )
            res.raise_for_status()
            res.encoding = "gbk"  # 腾讯返回 GBK，不设会拿到乱码名称
            text = str(res.text or "")
        except Exception as exc:
            logger.warning("腾讯行情请求失败: %s", exc)
            continue

        for line in text.split(";"):
            line = line.strip()
            if not line.startswith("v_") or "=" not in line:
                continue
            head, payload = line.split("=", 1)
            sym = head[2:].strip()
            code = symbol_to_code.get(sym)
            if not code:
                continue
            parts = payload.strip().strip('"').split("~")
            # 0 市场标识 1 名称 2 代码 3 现价 4 昨收 5 今开 …
            if len(parts) < 5:
                continue
            try:
                price = float(parts[3])
            except (TypeError, ValueError):
                continue
            if price <= 0:  # 停牌/无报价
                continue
            try:
                prev_close = float(parts[4]) if parts[4] not in ("", "-") else None
            except (TypeError, ValueError):
                prev_close = None
            change_pct = None
            if prev_close and prev_close > 0:
                change_pct = round((price / prev_close - 1.0) * 100.0, 2)
            quotes[code] = {
                "price": price,
                "change_pct": change_pct,
                "name": (parts[1] or "").strip(),
                "prev_close": prev_close,
                "source": "腾讯行情",
            }
    return quotes

def fetch_sina_quotes(codes):
    """新浪行情兜底（第二数据源），返回结构与 fetch_tencent_quotes 一致。

    为什么需要：东方财富 push2 / push2delay 的 /api/qt/* 从**这台服务器**的出口
    访问不了（两者都直接 RemoteDisconnected；同一时刻在别的网络上是通的，所以不是
    接口下线，是这条线路走不通）。结果是 `fetch_eastmoney_quotes` 内部那层腾讯兜底
    成了唯一实际生效的路径 —— 生产只剩腾讯一条线。腾讯一旦抽风，盘中提醒与日终
    快照会同时失明，所以在这里再补一路独立的源。

    新浪返回的是 GBK 文本：``var hq_str_sz000651="名称,今开,昨收,现价,最高,最低,...";``
    字段 0=名称 1=今开 2=昨收 3=现价。与腾讯不同，新浪没有现成涨跌幅，这里自己按
    昨收算，口径与腾讯保持一致。
    """
    symbol_to_code = {}
    for c in codes:
        sym = tencent_symbol(c)
        if sym:
            symbol_to_code[sym] = str(c).strip().lower().replace("f", "")
    if not symbol_to_code:
        return {}

    quotes = {}
    symbols = list(symbol_to_code)
    for i in range(0, len(symbols), 60):
        batch = symbols[i : i + 60]
        # 兜底路径自身出问题不能反过来把抓价搞崩：整批（请求 + 解析）都兜住，
        # 最坏就是这一批没有价格，保持"取不到价 → 保留旧价"的原有语义。
        try:
            res = requests.get(
                "https://hq.sinajs.cn/list=" + ",".join(batch),
                timeout=8,
                headers={
                    "Referer": "https://finance.sina.com.cn/",
                    "User-Agent": "Mozilla/5.0",
                },
            )
            res.raise_for_status()
            res.encoding = "gbk"  # 新浪返回 GBK，不设会拿到乱码名称
            text = str(res.text or "")
        except Exception as exc:
            logger.warning("新浪行情请求失败: %s", exc)
            continue

        for line in text.split(";"):
            line = line.strip()
            if not line.startswith("var hq_str_") or "=" not in line:
                continue
            head, payload = line.split("=", 1)
            sym = head[len("var hq_str_") :].strip()
            code = symbol_to_code.get(sym)
            if not code:
                continue
            parts = payload.strip().strip('"').split(",")
            # 0 名称 1 今开 2 昨收 3 现价 4 最高 5 最低 …
            if len(parts) < 4:
                continue
            try:
                price = float(parts[3])
            except (TypeError, ValueError):
                continue
            if price <= 0:  # 停牌/无报价
                continue
            try:
                prev_close = float(parts[2]) if parts[2] not in ("", "-") else None
            except (TypeError, ValueError):
                prev_close = None
            if prev_close is not None and prev_close <= 0:
                prev_close = None
            change_pct = None
            if prev_close:
                change_pct = round((price / prev_close - 1.0) * 100.0, 2)
            quotes[code] = {
                "price": price,
                "change_pct": change_pct,
                "name": (parts[0] or "").strip(),
                "prev_close": prev_close,
                "source": "新浪行情",
            }
    return quotes


def _cache_get(keys, now: float) -> Dict[str, dict]:
    if _CACHE_TTL <= 0:
        return {}
    out = {}
    with _QUOTE_CACHE_LOCK:
        for c in keys:
            entry = _QUOTE_CACHE.get(c)
            if not entry:
                continue
            if now - entry["ts"] <= _CACHE_TTL:
                out[c] = dict(entry["quote"])
    return out


def _cache_put(quotes: dict, now: float) -> None:
    if _CACHE_TTL <= 0 or not quotes:
        return
    with _QUOTE_CACHE_LOCK:
        for code, q in quotes.items():
            _QUOTE_CACHE[code] = {"quote": dict(q), "ts": now}
        # Opportunistic cleanup: drop expired entries so the cache cannot
        # grow without bound over long uptimes.
        expired = [k for k, e in _QUOTE_CACHE.items() if now - e["ts"] > _CACHE_TTL]
        for k in expired:
            _QUOTE_CACHE.pop(k, None)


def fetch_eastmoney_quotes(codes, secid_map=None, *, use_cache: bool = True):
    """Fetch quotes from Eastmoney push2delay.

    Returns {code: {price, change_pct, name, prev_close?}} for successful rows.
    secid_map: optional {code: "1.000300"} overrides eastmoney_sec_id for indices.

    The cache is keyed by the resolved secid, so an index quote (secid
    "1.000001") and a stock quote with the same numeric code (secid
    "0.000001") are stored and looked up independently.
    """
    secid_map = secid_map or {}
    numeric_codes = []
    skipped = []
    for c in codes:
        raw = str(c).strip().lower().replace("f", "")
        if raw.isdigit() and len(raw) == 6:
            numeric_codes.append(raw)
        elif str(c).strip():
            skipped.append(str(c).strip())
    if skipped:
        logger.warning("跳过无法转东方财富代码的标的: %s", ", ".join(skipped))
    if not numeric_codes:
        return {}

    # Resolve the final secid per code up front; cache entries are per-secid.
    resolved_secids = {c: (secid_map.get(c) or eastmoney_sec_id(c)) for c in numeric_codes}

    now = time.time()
    quotes = {}
    if use_cache:
        cached = _cache_get([resolved_secids[c] for c in numeric_codes], now)
        for c in numeric_codes:
            entry = cached.get(resolved_secids[c])
            if entry:
                quotes[c] = entry
    missing = [c for c in numeric_codes if c not in quotes]
    if not missing:
        return quotes

    for i in range(0, len(missing), 40):
        batch = missing[i : i + 40]
        secids = ",".join(resolved_secids[c] for c in batch)
        url = "https://push2delay.eastmoney.com/api/qt/ulist.np/get"
        params = {
            "fltt": "2",
            "invt": "2",
            # f2 price, f3 change%, f12 code, f14 name, f18 昨收
            "fields": "f12,f14,f2,f3,f18",
            "secids": secids,
        }
        # 单批失败不能拖垮整次同步：东财这个接口会整段不可用（连接被远端断开），
        # 下面是腾讯兜底。以前这里没有 try，异常冒泡到 _sync_prices_impl 被吃掉，
        # 结果是整批报价全部记为 failed。
        try:
            res = requests.get(
                url,
                params=params,
                timeout=8,
                headers={"Referer": "https://quote.eastmoney.com/", "User-Agent": "Mozilla/5.0"},
            )
            res.raise_for_status()
            data = res.json().get("data") or {}
        except Exception as exc:
            logger.warning("东方财富行情请求失败（%s），将用腾讯行情兜底: %s", url, exc)
            continue
        batch_quotes = {}
        for item in data.get("diff") or []:
            code = str(item.get("f12") or "").strip()
            price = item.get("f2")
            if not code or price in (None, "-"):
                continue
            change_pct = item.get("f3")
            if change_pct in (None, "-"):
                change_pct = None
            else:
                try:
                    change_pct = float(change_pct)
                except (TypeError, ValueError):
                    change_pct = None
            prev_close = item.get("f18")
            if prev_close in (None, "-"):
                prev_close = None
            else:
                try:
                    prev_close = float(prev_close)
                except (TypeError, ValueError):
                    prev_close = None
            # If change_pct missing but prev_close present, derive
            px = float(price)
            if change_pct is None and prev_close and prev_close > 0:
                change_pct = (px / prev_close - 1.0) * 100.0
            batch_quotes[code] = {
                "price": px,
                "change_pct": change_pct,
                "name": str(item.get("f14") or "").strip(),
                "prev_close": prev_close,
                "source": "东方财富行情",
            }
        quotes.update(batch_quotes)
        # Cache under the resolved secid so quotes for the same numeric code
        # fetched under different secids (index vs stock) stay separate.
        _cache_put({resolved_secids[c]: q for c, q in batch_quotes.items() if c in resolved_secids}, now)
        no_return = [c for c in missing if c not in batch_quotes]
        if no_return:
            logger.warning("东方财富未返回报价的标的: %s", ", ".join(no_return))

    # 腾讯兜底：东财缺哪些就用腾讯补哪些。
    # 必须自己兜住异常：fetch_tencent_quotes 内部虽然按批 try/except，但一旦它整体
    # 抛出（改版、依赖问题、mock 场景），异常会直接冒到调用方 —— 后面的新浪那一层
    # 就永远走不到，"多源冗余"名存实亡。宁可这一层空手，也要让下一层有机会补。
    still_missing = [c for c in numeric_codes if c not in quotes]
    if still_missing:
        try:
            fallback = fetch_tencent_quotes(still_missing)
        except Exception as exc:
            logger.warning("腾讯行情兜底失败: %s", exc)
            fallback = {}
        if fallback:
            quotes.update(fallback)
            _cache_put(
                {resolved_secids[c]: q for c, q in fallback.items() if c in resolved_secids},
                now,
            )
            logger.info("东方财富缺 %d 个报价，已用腾讯行情补齐 %d 个", len(still_missing), len(fallback))

    # 新浪再兜底：东财与腾讯都拿不到的才走这里。
    # 为什么加这一层：push2/push2delay 从生产服务器的出口访问不了（RemoteDisconnected），
    # 于是"腾讯兜底"成了唯一实际生效的路径 —— 腾讯一抽风，抓价与预警同时失明。
    # 把它放在 fetch_eastmoney_quotes 内部而不是新增一个入口，是为了让**所有**已有
    # 调用点（持仓同步、预警、指数、自选）自动获得这一路冗余，不必逐个改接线。
    still_missing = [c for c in numeric_codes if c not in quotes]
    if still_missing:
        try:
            sina = fetch_sina_quotes(still_missing)
        except Exception as exc:
            logger.warning("新浪行情兜底失败: %s", exc)
            sina = {}
        if sina:
            quotes.update(sina)
            logger.info("腾讯也未取到 %d 个报价，已用新浪行情补齐 %d 个", len(still_missing), len(sina))
    return quotes


def fetch_stock_quotes(codes):
    """A股/场内基金报价（东财 → 腾讯 → 新浪，逐层兜底）。

    与 fetch_eastmoney_prices 的区别：返回完整报价 dict（含 source），
    这样同步价能如实标出某个标的的价格实际来自哪个数据源。

    兜底链在 fetch_eastmoney_quotes 内部，这里不重复接线：抓价是日终快照与盘中提醒
    的共同上游，任何绕过它的入口都会丢掉那两路冗余。
    """
    return fetch_eastmoney_quotes(codes)


def fetch_eastmoney_prices(codes):
    """Backward-compatible: {code: price} only."""
    quotes = fetch_eastmoney_quotes(codes)
    return {code: q["price"] for code, q in quotes.items() if q.get("price") is not None}


def fetch_open_fund_nav(code: str):
    import akshare as ak  # lazy: not required for app boot / unit tests

    fund_code = str(code or "").strip().lower().replace("f", "")
    df = ak.fund_open_fund_info_em(symbol=fund_code, indicator="单位净值走势")
    if df is None or df.empty:
        return None
    return float(df.iloc[-1]["单位净值"])
