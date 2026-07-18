"""组合级辅助：外部流水草稿建议、晚间简报。"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from .database import local_today_iso
    from .discipline import build_discipline_report
    from .market import check_alerts
    from .performance import build_performance_story, build_performance_summary
    from .portfolio_totals import compute_portfolio_totals
    from .snapshots import snapshots_summary_data
except ImportError:
    from database import local_today_iso
    from discipline import build_discipline_report
    from market import check_alerts
    from performance import build_performance_story, build_performance_summary
    from portfolio_totals import compute_portfolio_totals
    from snapshots import snapshots_summary_data


def suggest_portfolio_cash_flows(conn) -> Dict[str, Any]:
    """从证券现金「银证转入/转出」流水，生成组合外部投入/取出草稿建议（不自动写入）。"""
    existing = [
        dict(r)
        for r in conn.execute(
            "SELECT date, flow_type, amount, remark FROM portfolio_cash_flows ORDER BY date, id"
        ).fetchall()
    ]
    existing_keys = {
        (str(r["date"])[:10], r["flow_type"], round(float(r["amount"] or 0), 2))
        for r in existing
    }

    try:
        cash_rows = [
            dict(r)
            for r in conn.execute(
                """
                SELECT date, account, flow_type, amount, remark
                FROM cash_flows
                WHERE flow_type IN ('银证转入', '银证转出')
                ORDER BY date DESC, id DESC
                LIMIT 80
                """
            ).fetchall()
        ]
    except Exception as exc:
        logger.warning("suggest_portfolio_cash_flows: read cash_flows failed: %s", exc)
        cash_rows = []

    drafts: List[Dict[str, Any]] = []
    for r in cash_rows:
        ft = r.get("flow_type")
        amt = abs(float(r.get("amount") or 0))
        if amt < 1:
            continue
        d = str(r.get("date") or "")[:10]
        if ft == "银证转入":
            mapped = "投入"
        elif ft == "银证转出":
            mapped = "取出"
        else:
            continue
        key = (d, mapped, round(amt, 2))
        if key in existing_keys:
            continue
        drafts.append(
            {
                "date": d,
                "flow_type": mapped,
                "amount": round(amt, 2),
                "source": r.get("account") or "银证",
                "remark": f"来自证券现金流水：{ft}" + (f" · {r.get('remark')}" if r.get("remark") else ""),
                "origin_flow_type": ft,
                "already_recorded": False,
            }
        )

    seen = set()
    uniq = []
    for d in drafts:
        k = (d["date"], d["flow_type"], d["amount"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(d)

    return {
        "as_of_date": local_today_iso(),
        "count": len(uniq),
        "drafts": uniq[:30],
        "hint": "根据「银证转入/转出」推测组合外部投入/取出。工资入金若走银证可点一条确认；内部调仓不要录。",
    }


def build_evening_brief(conn, *, check_price_alerts: bool = True) -> Dict[str, Any]:
    """晚间简报：总资产、绩效一句、纪律、预警、快照异常。"""
    totals = compute_portfolio_totals(conn)
    story = build_performance_story(conn)
    summary = build_performance_summary(conn)
    try:
        disc = build_discipline_report(conn)
    except Exception as exc:
        logger.warning("evening_brief: discipline report failed: %s", exc)
        disc = {"summary_text": "纪律报告暂不可用", "breaches": [], "plans": []}

    alert_part: Dict[str, Any] = {"triggered_count": 0, "messages": []}
    if check_price_alerts:
        try:
            ar = check_alerts(conn, record_events=False, notify=False)
            triggered = ar.get("triggered") or []
            if isinstance(triggered, list):
                alert_part["triggered_count"] = len(triggered)
                alert_part["messages"] = [
                    (t.get("message") or t.get("title") or str(t))[:120] for t in triggered[:8]
                ]
        except Exception as exc:
            logger.warning("evening_brief: check_alerts failed: %s", exc)
            alert_part["error"] = str(exc)

    anomaly_text = None
    try:
        end = local_today_iso()
        start = (datetime.fromisoformat(end) - timedelta(days=14)).date().isoformat()
        snap_sum = snapshots_summary_data(conn, start, end)
        an = (snap_sum or {}).get("day_over_day_anomaly")
        if an:
            anomaly_text = an.get("text") or str(an)
    except Exception as exc:
        logger.warning("evening_brief: snapshot anomaly failed: %s", exc)

    plan_lines = []
    for p in (disc.get("plans") or [])[:4]:
        plan_lines.append(f"{p.get('title')}: {p.get('text')}")

    lines = [
        f"【晚间简报】{local_today_iso()}",
        f"总资产约 {float(totals.get('total_assets') or 0):,.0f} 元",
        story.get("headline") or "（无绩效结论）",
        disc.get("summary_text") or "",
    ]
    if plan_lines:
        lines.append("计划：" + "；".join(plan_lines[:2]))
    if alert_part["triggered_count"]:
        lines.append(f"价格预警触发 {alert_part['triggered_count']} 条")
        lines.extend(f"- {m}" for m in alert_part["messages"][:5])
    else:
        lines.append("价格预警：无新触发")
    if anomaly_text:
        lines.append(f"快照异常：{anomaly_text}")

    text = "\n".join([x for x in lines if x])

    return {
        "as_of_date": local_today_iso(),
        "text": text,
        "headline": story.get("headline"),
        "total_assets": totals.get("total_assets"),
        "discipline_summary": disc.get("summary_text"),
        "plans": disc.get("plans") or [],
        "alerts": alert_part,
        "snapshot_anomaly": anomaly_text,
        "metrics": {
            "lifetime_profit": summary.get("lifetime_profit"),
            "ytd_gain": summary.get("ytd_gain"),
            "xirr": summary.get("xirr"),
        },
    }


def send_evening_brief(conn, *, webhook: Optional[str] = None, notify: bool = True) -> Dict[str, Any]:
    brief = build_evening_brief(conn, check_price_alerts=True)
    webhook = (webhook if webhook is not None else os.environ.get("FEISHU_ALERT_WEBHOOK", "")).strip()
    sent = {"sent": False, "reason": "skipped"}
    if notify and webhook:
        try:
            import requests

            payload = {
                "msg_type": "text",
                "content": {"text": brief.get("text") or "（空简报）"},
            }
            res = requests.post(webhook, json=payload, timeout=10)
            sent = {"sent": res.ok, "status_code": res.status_code}
            if not res.ok:
                sent["reason"] = res.text[:200]
        except Exception as exc:
            sent = {"sent": False, "reason": str(exc)}
    elif notify and not webhook:
        sent = {"sent": False, "reason": "no_webhook"}
    return {**brief, "notify": sent}
