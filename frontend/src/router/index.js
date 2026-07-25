import { createRouter, createWebHistory } from 'vue-router';
import { ROUTE_META, resolveInitialTab, SCREENSHOT_TABS, LEGACY_TAB_REDIRECT } from '../modules/tabNav.js';

const loaders = {
    overview: () => import('../views/OverviewTab.vue'),
    holdings: () => import('../views/HoldingsTab.vue'),
    transactions: () => import('../views/TransactionsTab.vue'),
    broker: () => import('../views/BrokerReconcileTab.vue'),
    deposits: () => import('../views/DepositsTab.vue'),
    cash: () => import('../views/CashTab.vue'),
    decision: () => import('../views/DecisionTab.vue'),
    performance: () => import('../views/PerformanceTab.vue'),
    allocation: () => import('../views/AllocationTab.vue'),
    snapshots: () => import('../views/SnapshotsTab.vue'),
    market: () => import('../views/MarketTab.vue'),
    discipline: () => import('../views/DisciplineTab.vue'),
    ops_notify: () => import('../views/NotifyOpsTab.vue'),
    ops_backup: () => import('../views/BackupOpsTab.vue'),
};

const routes = Object.entries(ROUTE_META).map(([name, meta]) => ({
    path: meta.path,
    name,
    component: loaders[name],
    meta: { label: meta.label },
}));

// 旧 /maintenance → 消息推送
routes.push({
    path: '/maintenance',
    redirect: { name: 'ops_notify' },
});

routes.push({
    path: '/:pathMatch(.*)*',
    redirect: () => {
        const tab = resolveInitialTab();
        const name = SCREENSHOT_TABS.includes(tab) ? (LEGACY_TAB_REDIRECT[tab] || tab) : 'overview';
        return { name: ROUTE_META[name] ? name : 'overview' };
    },
});

const router = createRouter({
    history: createWebHistory(),
    routes,
    scrollBehavior() {
        return { top: 0 };
    },
});

// 兼容旧链接 ?tab=holdings / ?tab=maintenance
router.beforeEach((to) => {
    const tab = typeof to.query.tab === 'string' ? to.query.tab : '';
    if (tab && SCREENSHOT_TABS.includes(tab)) {
        const name = LEGACY_TAB_REDIRECT[tab] || tab;
        if (to.name !== name) {
            return { name, query: {} };
        }
    }
    return true;
});

export default router;
