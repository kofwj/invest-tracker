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

Object.assign(window, { normalizeText, daysUntil, formatMoney, formatPercent, pct, inferCategoryByCode });
