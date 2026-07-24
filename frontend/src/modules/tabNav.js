/** Tab grouping for header navigation (日常 / 分析 / 维护). */

export const SCREENSHOT_TABS = [
    'decision', 'snapshots', 'allocation', 'performance', 'market', 'discipline',
    'holdings', 'deposits', 'transactions', 'broker', 'cash', 'maintenance',
];

export const TAB_GROUPS = [
    { id: 'daily', label: '日常', tabs: ['holdings', 'transactions', 'broker', 'deposits', 'cash'] },
    { id: 'analysis', label: '分析', tabs: ['decision', 'performance', 'allocation', 'snapshots', 'market', 'discipline'] },
    { id: 'ops', label: '维护', tabs: ['maintenance'] },
];

export function tabGroupOf(tab) {
    const hit = TAB_GROUPS.find(g => g.tabs.includes(tab));
    return hit ? hit.id : 'analysis';
}

export function resolveInitialTab(searchParams = null) {
    const params = searchParams || new URLSearchParams(window.location.search);
    const requested = params.get('tab');
    return SCREENSHOT_TABS.includes(requested) ? requested : 'snapshots';
}
