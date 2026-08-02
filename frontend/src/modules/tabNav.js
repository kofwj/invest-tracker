/** 顶栏导航 + 路由名映射（日常 / 分析 / 设置 + 今日总览）。 */

export const SCREENSHOT_TABS = [
    'overview',
    'decision', 'snapshots', 'allocation', 'performance', 'klines', 'market', 'discipline',
    'holdings', 'deposits', 'transactions', 'broker', 'cash',
    'ops_notify', 'ops_backup',
    // 旧名兼容（截图/书签）
    'maintenance',
];

/** @type {{ id: string, label: string, tabs: string[] }[]} */
export const TAB_GROUPS = [
    { id: 'home', label: '总览', tabs: ['overview'] },
    { id: 'daily', label: '日常', tabs: ['holdings', 'transactions', 'deposits'] },
    // P2 真合并：决策+市场 → decision；配置+纪律 → allocation
    { id: 'analysis', label: '分析', tabs: ['decision', 'performance', 'allocation', 'klines'] },
    // 原「维护」→「设置」：推送 / 证券账户(费率+现金) / 备份
    { id: 'ops', label: '设置', tabs: ['ops_notify', 'cash', 'ops_backup'] },
];

/** 路由元信息：path 与中文标签 */
export const ROUTE_META = {
    overview: { path: '/', label: '今日总览' },
    holdings: { path: '/holdings', label: '持仓明细' },
    transactions: { path: '/transactions', label: '交易录入/管理' },
    broker: { path: '/broker', label: '券商对账' },
    deposits: { path: '/deposits', label: '银行存款' },
    cash: { path: '/cash', label: '证券账户' },
    decision: { path: '/decision', label: '今天该看' },
    performance: { path: '/performance', label: '收益分析' },
    allocation: { path: '/allocation', label: '结构与目标' },
    klines: { path: '/klines', label: 'K线查询' },
    snapshots: { path: '/snapshots', label: '资产快照' },
    market: { path: '/market', label: '市场摘要' },
    discipline: { path: '/discipline', label: '纪律与再平衡' },
    ops_notify: { path: '/ops/notify', label: '消息推送' },
    ops_backup: { path: '/ops/backup', label: '数据备份' },
};

/** 旧 tab / path → 新路由名 */
export const LEGACY_TAB_REDIRECT = {
    maintenance: 'ops_notify',
    market: 'decision',
    discipline: 'allocation',
};

export function tabGroupOf(tab) {
    const normalized = LEGACY_TAB_REDIRECT[tab] || tab;
    const hit = TAB_GROUPS.find((g) => g.tabs.includes(normalized));
    return hit ? hit.id : 'home';
}

export function tabLabel(tab) {
    const normalized = LEGACY_TAB_REDIRECT[tab] || tab;
    return ROUTE_META[normalized]?.label || tab;
}

/** 兼容旧 ?tab=xxx；默认今日总览 */
export function resolveInitialTab(searchParams = null) {
    const params = searchParams || new URLSearchParams(window.location.search);
    const requested = params.get('tab');
    if (requested && SCREENSHOT_TABS.includes(requested)) {
        return LEGACY_TAB_REDIRECT[requested] || requested;
    }
    return 'overview';
}

export function pathForTab(tab) {
    const normalized = LEGACY_TAB_REDIRECT[tab] || tab;
    return ROUTE_META[normalized]?.path || '/';
}
