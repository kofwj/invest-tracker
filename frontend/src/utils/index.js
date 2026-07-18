// Shared frontend utility helpers. Keep this file framework-agnostic.
const normalizeText = (value) => String(value || '').trim().toLowerCase();

const daysUntil = (dateStr) => {
    if (!dateStr) return null;
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const due = new Date(dateStr + 'T00:00:00');
    if (Number.isNaN(due.getTime())) return null;
    return Math.ceil((due - today) / 86400000);
};

/** Inclusive day count between two YYYY-MM-DD dates (start → end). */
const daysBetween = (startStr, endStr) => {
    if (!startStr || !endStr) return null;
    const start = new Date(String(startStr) + 'T00:00:00');
    const end = new Date(String(endStr) + 'T00:00:00');
    if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return null;
    return Math.round((end - start) / 86400000);
};

const formatMoney = (value, digits = 2, showSign = false) => {
    if (value === null || value === undefined || value === '') return '—';
    const num = Number(value);
    if (Number.isNaN(num)) return '—';
    const sign = showSign && num > 0 ? '+' : (num < 0 ? '-' : '');
    const absValue = Math.abs(num).toLocaleString(undefined, {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
    });
    return `${sign}¥${absValue}`;
};

const formatPercent = (value, digits = 2) => {
    if (value === null || value === undefined || value === '') return '—';
    const num = Number(value);
    if (Number.isNaN(num)) return '—';
    return `${num >= 0 ? '+' : ''}${num.toFixed(digits)}%`;
};

const pct = (part, total, digits = 1) => {
    const p = Number(part || 0);
    const t = Number(total || 0);
    return t > 0 ? `${(p / t * 100).toFixed(digits)}%` : '—';
};

const inferCategoryByCode = (code, name) => {
    const c = String(code || '').trim().toLowerCase();
    const n = String(name || '');
    if (c.startsWith('f')) return '债基';
    if (c === '513530') return '港股ETF';
    if (c === '518880') return '黄金';
    if (c.startsWith('508') || /reit/i.test(n)) return 'REITs';
    if (c.startsWith('159') || c.startsWith('51')) return 'A股ETF';
    if (/短债|债|丰享/.test(n)) return '债基';
    if (/黄金/.test(n)) return '黄金';
    if (/港股|恒生|红利ETF/.test(n)) return '港股ETF';
    if (/ETF/i.test(n)) return 'A股ETF';
    if (/^\d{6}$/.test(c)) return 'A股权益';
    return '';
};


const holdingFloatProfit = (row) => {
    const qty = Number(row?.quantity || 0);
    const last = Number(row?.last_price || 0);
    const avg = Number(row?.avg_cost || 0);
    const div = Number(row?.total_dividend || 0);
    return (last - avg) * qty + div;
};

const holdingLifetimeProfit = (row) => {
    const qty = Number(row?.quantity || 0);
    const last = Number(row?.last_price || 0);
    // 摊薄成本缺省时回退普通成本，与后端口径一致
    const dilutedRaw = row?.diluted_cost;
    const diluted = (dilutedRaw === null || dilutedRaw === undefined || dilutedRaw === '')
        ? Number(row?.avg_cost || 0)
        : Number(dilutedRaw);
    // 全周期 ≈ 市值 - 净投入；摊薄成本 = 净投入/数量，故 (现价-摊薄)*数量
    // 分红已体现在 net_invested/摊薄成本中，不再重复加 total_dividend
    return (last - diluted) * qty;
};

const holdingFloatProfitRate = (row) => {
    const qty = Number(row?.quantity || 0);
    const avg = Number(row?.avg_cost || 0);
    const cost = avg * qty;
    if (!(cost > 0)) return null;
    return holdingFloatProfit(row) / cost * 100;
};

const holdingLifetimeProfitRate = (row) => {
    const qty = Number(row?.quantity || 0);
    const diluted = Number(row?.diluted_cost || 0);
    const net = diluted * qty;
    // 净投入为 0 或负（回本后仍持仓）时不展示比率
    if (!(net > 0)) return null;
    return holdingLifetimeProfit(row) / net * 100;
};

const todayLocalIso = () => {
    const d = new Date();
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
};

/** Simple interest for N days at annual rate % (365-day year). */
const interestForDays = (amount, ratePct, days) => {
    if (days == null || Number.isNaN(Number(days))) return null;
    const d = Number(days);
    if (d < 0) return 0;
    return Number(amount || 0) * Number(ratePct || 0) / 100 * d / 365;
};

/** Extract FastAPI/axios error message for UI toasts. */
const apiErrorDetail = (e, fallback = '未知错误') => {
    const d = e?.response?.data?.detail;
    if (typeof d === 'string' && d.trim()) return d;
    if (Array.isArray(d) && d.length) {
        const first = d[0];
        if (typeof first === 'string') return first;
        if (first?.msg) return String(first.msg);
    }
    if (d && typeof d === 'object' && d.msg) return String(d.msg);
    if (e?.message) return String(e.message);
    return fallback;
};

Object.assign(window, {
    normalizeText, daysUntil, daysBetween, formatMoney, formatPercent, pct,
    inferCategoryByCode, holdingFloatProfit, holdingLifetimeProfit,
    holdingFloatProfitRate, holdingLifetimeProfitRate, todayLocalIso,
    interestForDays, apiErrorDetail,
});

export {
    normalizeText,
    daysUntil,
    daysBetween,
    formatMoney,
    formatPercent,
    pct,
    inferCategoryByCode,
    holdingFloatProfit,
    holdingLifetimeProfit,
    holdingFloatProfitRate,
    holdingLifetimeProfitRate,
    todayLocalIso,
    interestForDays,
    apiErrorDetail,
};
