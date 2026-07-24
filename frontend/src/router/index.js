import { createRouter, createWebHistory } from 'vue-router';
import { ROUTE_META, resolveInitialTab, SCREENSHOT_TABS } from '../modules/tabNav.js';

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
    maintenance: () => import('../views/MaintenanceTab.vue'),
};

const routes = Object.entries(ROUTE_META).map(([name, meta]) => ({
    path: meta.path,
    name,
    component: loaders[name],
    meta: { label: meta.label },
}));

routes.push({
    path: '/:pathMatch(.*)*',
    redirect: () => {
        const tab = resolveInitialTab();
        return { name: SCREENSHOT_TABS.includes(tab) ? tab : 'overview' };
    },
});

const router = createRouter({
    history: createWebHistory(),
    routes,
    scrollBehavior() {
        return { top: 0 };
    },
});

// 兼容旧链接 ?tab=holdings
router.beforeEach((to) => {
    const tab = typeof to.query.tab === 'string' ? to.query.tab : '';
    if (tab && SCREENSHOT_TABS.includes(tab) && to.name !== tab) {
        return { name: tab, query: {} };
    }
    return true;
});

export default router;
