/** 顶栏导航 + 路由名映射（日常 / 分析 / 维护 + 今日总览）。 */

export const SCREENSHOT_TABS = [
    'overview',
    'decision', 'snapshots', 'allocation', 'performance', 'market', 'discipline',
    'holdings', 'deposits', 'transactions', 'broker', 'cash', 'maintenance',
];

/** @type {{ id: string, label: string, tabs: string[] }[]} */
export const TAB_GROUPS = [
    { id: 'home', label: '总览', tabs: ['overview'] },
    { id: 'daily', label: '日常', tabs: ['holdings', 'transactions', 'broker', 'deposits', 'cash'] },
    { id: 'analysis', label: '分析', tabs: ['decision', 'performance', 'allocation', 'snapshots', 'market', 'discipline'] },
    { id: 'ops', label: '维护', tabs: ['maintenance'] },
];

/** 路由元信息：path 与中文标签 */
export const ROUTE_META = {
    overview: { path: '/', label: '今日总览' },
    holdings: { path: '/holdings', label: '持仓明细' },
    transactions: { path: '/transactions', label: '交易录入/管理' },
    broker: { path: '/broker', label: '券商对账' },
    deposits: { path: '/deposits', label: '银行存款' },
    cash: { path: '/cash', label: '现金设置' },
    decision: { path: '/decision', label: '今天该看' },
    performance: { path: '/performance', label: '收益分析' },
    allocation: { path: '/allocation', label: '资产配置' },
    snapshots: { path: '/snapshots', label: '资产快照' },
    market: { path: '/market', label: '市场摘要' },
    discipline: { path: '/discipline', label: '纪律与再平衡' },
    maintenance: { path: '/maintenance', label: '数据维护' },
};

export function tabGroupOf(tab) {
    const hit = TAB_GROUPS.find((g) => g.tabs.includes(tab));
    return hit ? hit.id : 'home';
}

export function tabLabel(tab) {
    return ROUTE_META[tab]?.label || tab;
}

/** 兼容旧 ?tab=xxx；默认今日总览 */
export function resolveInitialTab(searchParams = null) {
    const params = searchParams || new URLSearchParams(window.location.search);
    const requested = params.get('tab');
    if (requested && SCREENSHOT_TABS.includes(requested)) return requested;
    return 'overview';
}

export function pathForTab(tab) {
    return ROUTE_META[tab]?.path || '/';
}
