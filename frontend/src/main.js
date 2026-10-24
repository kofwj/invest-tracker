import { createApp, ref, computed, onMounted, nextTick, watch, provide } from 'vue';
import { ElLoading, ElMessage, ElMessageBox } from 'element-plus';
import zhCn from 'element-plus/es/locale/lang/zh-cn';
import 'element-plus/es/components/message/style/css';
import 'element-plus/es/components/message-box/style/css';
import 'element-plus/es/components/loading/style/css';
import 'element-plus/theme-chalk/dark/css-vars.css';
import App from './App.vue';
import router from './router/index.js';
import { storeToRefs } from 'pinia';
import {
    pinia,
    useThemeStore,
    useAuthStore,
    useNotifyStore,
    useMarketStore,
    usePortfolioStore,
    useCashStore,
    useTransactionsStore,
    usePerformanceStore,
    useAllocationStore,
    useDisciplineStore,
    useSnapshotsStore,
    useBrokerStore,
    useMaintenanceStore,
    useDividendStore,
} from './stores/index.js';
import { APP_CTX_KEY } from './composables/useAppCtx.js';
import {
    normalizeText,
    daysUntil,
    formatMoney,
    formatPercent,
    pct,
    inferCategoryByCode,
    holdingFloatProfit,
    holdingLifetimeProfit,
    holdingFloatProfitRate,
    holdingLifetimeProfitRate,
    todayLocalIso,
} from './utils/index.js';
import api from './api/index.js';
import { createAppInit } from './modules/appInit.js';
import { TAB_GROUPS, tabGroupOf, SCREENSHOT_TABS, ROUTE_META, LEGACY_TAB_REDIRECT } from './modules/tabNav.js';
import './styles/styles.css';

const app = createApp({
    extends: App,
    setup() {
        const tabGroups = TAB_GROUPS;

        // Deferred bootstrap after login unlock (wired below after helpers exist)
        let bootstrapAfterAuth = async () => {};

        const authStore = useAuthStore(pinia);
        authStore.setOnUnlocked(() => bootstrapAfterAuth());
        const {
            isMasked,
            showLoginOverlay,
            loginLoading,
            loginPassword,
            loginError,
            authEnabled,
            sessionExpired,
        } = storeToRefs(authStore);
        const {
            toggleMask,
            handleLogin,
            handleLogout,
            reloadForRelogin,
        } = authStore;

        // 路由驱动当前页；activeTab 兼容旧模块跳转
        const goTab = (tab) => {
            if (!tab || !SCREENSHOT_TABS.includes(tab)) return;
            const name = LEGACY_TAB_REDIRECT[tab] || tab;
            if (!ROUTE_META[name]) return;
            if (router.currentRoute.value.name === name) return;
            router.push({ name }).catch(() => {});
        };
        const activeTab = computed({
            get() {
                const name = router.currentRoute.value.name;
                return typeof name === 'string' && SCREENSHOT_TABS.includes(name) ? name : 'overview';
            },
            set(tab) {
                goTab(tab);
            },
        });
        const tabGroup = computed(() => tabGroupOf(activeTab.value));
        const portfolioStore = usePortfolioStore(pinia);
        const {
            dashboard,
            holdings,
            deposits,
            syncing,
            trailingSyncing,
            syncNotice,
            todayIso,
            todaySnapshotDone,
            latestPriceStatusText,
            latestBackupText,
            depositDialog,
            depositRows,
            depositSummary,
            depositBankBreakdown,
            depositMaturityBuckets,
        } = storeToRefs(portfolioStore);
        const {
            showSyncNotice,
            refreshTodayIso,
            fetchData,
            syncPrices,
            syncTrailingReturns,
            openDepositDialog,
            saveDeposit,
            deleteDeposit,
            downloadDepositsTemplate,
            exportDeposits,
            importDeposits,
        } = portfolioStore;

        const cashStore = useCashStore(pinia);
        const {
            cashForm,
            cashFlows,
            cashFlowForm,
            cashFlowQuery,
            cashFlowEditDialog,
            cashAudit,
            cashFlowSummary,
        } = storeToRefs(cashStore);
        const {
            updateCash,
            queryCashFlows,
            resetCashFlowQuery,
            cashFlowTagType,
            addCashFlow,
            openCashFlowEditDialog,
            saveCashFlowEdit,
            deleteCashFlow,
            fetchCashAudit,
        } = cashStore;

        const transactionsStore = useTransactionsStore(pinia);
        const {
            allTransactions,
            filteredTransactions,
            pendingTransactions,
            pendingPurchaseTotal,
            transPage,
            transQuery,
            transEditDialog,
            transDialog,
            transForm,
            feeManuallyEdited,
            feeSettings,
            feeAccounts,
            activeFeeAccount,
            newFeeAccountName,
            feeAutoHint,
            feeSettingRows,
        } = storeToRefs(transactionsStore);
        const {
            feeCategories,
            markFeeManual,
            saveFeeSettings,
            resetFeeSettings,
            addFeeAccount,
            removeFeeAccount,
            onActiveFeeAccountChange,
            submitTrans,
            resetForm,
            showTransactions,
            updatePendingTransactions,
            queryTransactions,
            applyTransFilter,
            resetTransQuery,
            handleTransPageChange,
            handleTransPageSizeChange,
            goPendingTransactions,
            openTransEditDialog,
            saveTransactionEdit,
            deleteTransaction,
            queryAssetByCode,
            queryAssetByName,
            selectTransAsset,
            autoMatchTransAsset,
            parseNlEntry,
            downloadTransactionsTemplate,
            exportTransactions,
            importTransactions,
        } = transactionsStore;

        const snapshotsStore = useSnapshotsStore(pinia);
        const {
            snapshots,
            snapshotRange,
            snapshotSummary,
            snapshotMetrics,
            snapshotChangeRows,
            snapshotLoading,
            reconcileData,
            reconcileForm,
            reconcileSaving,
        } = storeToRefs(snapshotsStore);
        const {
            createSnapshot,
            buildSnapshotAnalysis,
            renderSnapshotCharts,
            fetchSnapshots,
            exportSnapshots,
            compactSnapshots,
            snapshotInsights,
            fetchReconcile,
            saveReconcile,
        } = snapshotsStore;

        const allocationStore = useAllocationStore(pinia);
        const {
            allocationAnalysis,
            macroAllocationAnalysis,
            portfolioExpectedReturn,
            allocationStory,
            allocationStoryLoading,
            expectedReturnDialog,
            holdingCorrectionDialog,
            holdingCorrectionHistoryDialog,
            allocationSummary,
            allocationHealth,
        } = storeToRefs(allocationStore);
        const {
            calculateAllocationAnalysis,
            renderAllocationCharts,
            fetchAllocationStory,
            openExpectedReturnDialog,
            saveExpectedReturn,
            openHoldingCorrectionDialog,
            saveHoldingCorrection,
            openHoldingCorrectionHistory,
            deleteHoldingCorrection,
        } = allocationStore;

        const dividendStore = useDividendStore(pinia);
        const {
            dividendLoading,
            dividendConfirming,
            dividendTableRef,
            dividendDialog,
        } = storeToRefs(dividendStore);
        const {
            openDividendDraftDialog,
            dividendStatusLabel,
            dividendStatusType,
            isDividendDraftSelectable,
            onDividendSelectionChange,
            selectSelectableDividendDrafts,
            clearDividendDraftSelection,
            scanDividendDrafts,
            confirmSelectedDividends,
            downloadDividendTemplate,
            importDividends,
        } = dividendStore;

        const notifyStore = useNotifyStore(pinia);
        const {
            notifyStatus,
            notifyLogs,
            notifyLoading,
            notifyEventDraft,
            notifyChannelDraft,
            notifyChannelClear,
            eveningBriefDialog,
        } = storeToRefs(notifyStore);
        const {
            fetchNotifyPanel,
            saveNotifyPanel,
            testNotifyPush,
            pushDepositDueNow,
            pushDisciplineNow,
            openEveningBrief,
        } = notifyStore;

        const maintenanceStore = useMaintenanceStore(pinia);
        const {
            maintenanceStatus,
            backups,
            maintenanceLoading,
        } = storeToRefs(maintenanceStore);
        const {
            fetchMaintenance,
            createDbBackup,
            downloadBackup,
            restoreBackup,
            deleteBackup,
            restoreUploadedBackup,
        } = maintenanceStore;



        const performanceStore = usePerformanceStore(pinia);
        const {
            perfSummary,
            perfTimeline,
            perfContribution,
            perfFlows,
            perfStory,
            perfWindows,
            perfLoading,
            perfContributionFilter,
            perfContributionSort,
            perfTimelineRange,
            perfFlowForm,
            hasPerfFlows,
            perfStoryToneType,
            perfPrimaryCards,
            perfSecondaryCards,
            perfCards,
            perfCategoryBars,
            displayedPerfContribution,
            perfContributionHeadline,
            perfContributionMix,
            contributionBarStyle,
            perfRiskMetrics,
            perfContributionSummary,
            perfWindowCards,
            perfDailyRows,
            perfDailyStats,
            perfLatestSnapshotDate,
            perfTodayPnl,
            perfTodayRow,
        } = storeToRefs(performanceStore);
        const {
            fetchPerformance,
            setPerfTimelineRange,
            addPerfFlow,
            updatePerfFlow,
            deletePerfFlow,
            loadPerfFlowSuggestions,
            applyPerfFlowSuggestion,
            selectPerfWindow,
        } = performanceStore;

        const brokerStore = useBrokerStore(pinia);
        const {
            brokerResult,
            brokerLoading,
            brokerSelected,
            brokerAsOfDate,
            brokerCashInput,
            brokerHistory,
        } = storeToRefs(brokerStore);
        const {
            statusLabel: brokerStatusLabel,
            statusType: brokerStatusType,
            onBrokerFileChange,
            onBrokerSelectionChange,
            selectAllSuggestions,
            clearBrokerSelection,
            applySelectedCorrections,
            fetchBrokerHistory,
        } = brokerStore;

        const refreshLocalDates = () => {
            if (typeof refreshTodayIso === 'function') refreshTodayIso();
            const today = todayIso.value || todayLocalIso();
            cashFlowForm.value.date = today;
            reconcileForm.value.date = today;
            transForm.value.date = today;
            holdingCorrectionDialog.value.form.date = today;
            perfFlowForm.value.date = today;
            brokerAsOfDate.value = today;
        };

        const marketStore = useMarketStore(pinia);
        const {
            marketSummary,
            alertRules,
            alertEvents,
            marketLoading,
            alertChecking,
            alertEventsLoading,
            alertForm,
            alertEditDialog,
            triggeredAlerts,
            alertEventCodeFilter,
            alertEventStartDate,
            alertEventEndDate,
            watchlistDraft,
            watchlistSaving,
            indexRows,
            watchlistRows,
            holdingsDayRows,
            marketSignals,
            marketHighlights,
            marketComparisons,
            marketUpdatedAt,
            quoteCacheSeconds,
            alertCooldownMinutes,
        } = storeToRefs(marketStore);
        const {
            fetchMarketSummary,
            fetchAlertRules,
            fetchAlertEvents,
            exportAlertEvents,
            clearAlertEvents,
            refreshMarket,
            resetAlertForm,
            saveAlertRule,
            openAlertCreate,
            openAlertEdit,
            parseNlRule,
            toggleAlertEnabled,
            deleteAlertRule,
            checkAlerts,
            addWatchlistRow,
            removeWatchlistRow,
            saveWatchlist,
        } = marketStore;

        const disciplineStore = useDisciplineStore(pinia);
        const {
            disciplineReport,
            disciplineDrafts,
            disciplinePolicy,
            disciplineLoading,
            disciplineDraftLoading,
            disciplinePolicyDialog,
            disciplineDraftEditDialog,
            disciplineDraftEditForm,
            disciplineSelectedDraftIds,
            disciplinePresets,
            disciplinePresetActiveId,
            disciplinePresetLoading,
            greeReducePct,
            breaches,
            actions,
            planItems,
            helpNotes,
            snapshot,
            targets,
            summaryText,
        } = storeToRefs(disciplineStore);
        const {
            fetchDisciplineReport,
            fetchDisciplineDrafts,
            fetchDisciplinePresets,
            applyDisciplinePreset,
            refreshDiscipline,
            openPolicyDialog,
            cancelPolicy,
            savePolicy,
            createDraftsFromReport,
            openDraftEdit,
            saveDraftEdit,
            deleteDraft,
            confirmDraft,
            onDraftSelectionChange,
            confirmSelectedDrafts,
        } = disciplineStore;

        watch(activeTab, (val) => {
            // P2：decision 含市场；allocation 含纪律
            if (val === 'overview' || val === 'decision') {
                refreshMarket();
                if (val === 'decision') refreshDiscipline();
            }
            if (val === 'transactions') queryTransactions();
            if (val === 'allocation') {
                nextTick(renderAllocationCharts);
                refreshDiscipline();
                fetchAllocationStory();
            }
            // 「收益与快照」= 原来的收益分析 + 资产快照两页合并，进这一页要拉两边的数据
            if (val === 'performance') {
                fetchPerformance();
                fetchSnapshots().then(() => nextTick(renderSnapshotCharts));
            }
            // 首页第一段要用「今日盈亏/本月/今年」，那几张卡的数据来自 performance 模块：
            // 停在总览时也拉一次（silent：不在首页弹「收益分析已刷新」），否则一直显示「—」。
            if (val === 'overview') fetchPerformance({ silent: true });
            if (val === 'ops_notify' || val === 'maintenance') {
                fetchNotifyPanel();
            }
            if (val === 'ops_backup') {
                fetchMaintenance();
            }
            if (val === 'cash') {
                queryCashFlows();
            }
            if (val === 'broker') {
                fetchBrokerHistory();
            }
        });

        // 首屏就落在总览时，上面的 watch 不会触发 → 等路由就绪后补拉一次，
        // 否则首页第一段那几张卡会一直显示「—」。
        if (typeof router.isReady === 'function') {
            router.isReady().then(() => {
                if (activeTab.value === 'overview') fetchPerformance({ silent: true });
            });
        }

        /**
         * 顶栏「刷新」= 刷新「当前页」。
         *
         * 以前顶栏刷新只调 fetchData（dashboard/holdings/deposits/现金/费率），
         * 在「分析」组里点它，收益分析 / 今天该看 / 结构与目标的数据一个都没动，
         * 页面上自然"刷新不出来"。
         */
        const refreshCurrentTab = async () => {
            const tab = activeTab.value;
            const jobs = [fetchData()];
            if (tab === 'performance') jobs.push(fetchPerformance(), fetchSnapshots().then(() => nextTick(renderSnapshotCharts)));
            if (tab === 'decision') jobs.push(refreshMarket(), refreshDiscipline());
            if (tab === 'allocation') {
                jobs.push(
                    fetchAllocationStory(),
                    refreshDiscipline(),
                    fetchDisciplineDrafts().then(() => nextTick(renderAllocationCharts)),
                );
            }
            if (tab === 'transactions') jobs.push(queryTransactions());
            if (tab === 'cash') jobs.push(queryCashFlows());
            if (tab === 'broker') jobs.push(fetchBrokerHistory());
            if (tab === 'ops_notify' || tab === 'maintenance') jobs.push(fetchNotifyPanel());
            if (tab === 'ops_ai') window.dispatchEvent(new CustomEvent('invest-tab-refresh'));
            if (tab === 'ops_backup') jobs.push(fetchMaintenance());

            const results = await Promise.allSettled(jobs);
            const failed = results.filter((r) => r.status === 'rejected');
            if (failed.length) {
                const detail = failed[0].reason?.response?.data?.detail
                    || failed[0].reason?.message
                    || '未知错误';
                showSyncNotice(`刷新失败：${detail}`, 'error');
            } else {
                showSyncNotice('已刷新', 'success');
            }
            return { failed: failed.length };
        };

        // Bootstrap + init extracted
        const { bootstrapAfterAuth: doBootstrap, setupOnMounted } = createAppInit({
            api,
            authEnabled,
            showLoginOverlay,
            fetchData,
            queryTransactions,
            queryCashFlows,
            fetchSnapshots,
            fetchMaintenance,
            refreshLocalDates,
        });

        bootstrapAfterAuth = doBootstrap;

        const themeStore = useThemeStore(pinia);
        const {
            themeMode,
            resolvedTheme,
            themeLabel,
        } = storeToRefs(themeStore);
        const {
            setThemeMode,
            cycleThemeMode,
            setupThemeListeners,
        } = themeStore;

        onMounted(() => {
            setupThemeListeners();
            setupOnMounted();
        });

        const appCtx = {
            zhCn,
            isMasked, toggleMask,
            themeMode, resolvedTheme, themeLabel, setThemeMode, cycleThemeMode,
            showLoginOverlay, loginLoading, loginPassword, loginError, authEnabled, handleLogin, handleLogout, sessionExpired, reloadForRelogin,
            activeTab, tabGroup, tabGroups, goTab, dashboard, holdings, deposits, depositRows, depositSummary, depositBankBreakdown, depositMaturityBuckets, syncing, trailingSyncing, syncNotice,
            snapshots, snapshotRange, snapshotSummary, snapshotMetrics, snapshotChangeRows, snapshotInsights, snapshotLoading, reconcileData, reconcileForm, reconcileSaving, fetchReconcile, saveReconcile, maintenanceStatus, backups, maintenanceLoading, dividendLoading, dividendConfirming, dividendDialog, dividendTableRef, todayIso, todaySnapshotDone, latestPriceStatusText, latestBackupText,
            transForm, feeSettings, feeAccounts, activeFeeAccount, newFeeAccountName, feeCategories, feeSettingRows, feeAutoHint, depositDialog, cashForm, cashFlows, cashFlowForm, cashFlowQuery, cashFlowSummary, cashFlowEditDialog, cashAudit, transDialog, allocationAnalysis, macroAllocationAnalysis, allocationSummary, allocationHealth, portfolioExpectedReturn, allocationStory, allocationStoryLoading, fetchAllocationStory,
            allTransactions, filteredTransactions, pendingTransactions, pendingPurchaseTotal, transQuery, transPage, transEditDialog,
            syncPrices, syncTrailingReturns, openDividendDraftDialog, openEveningBrief, eveningBriefDialog, scanDividendDrafts, confirmSelectedDividends, selectSelectableDividendDrafts, clearDividendDraftSelection, onDividendSelectionChange, isDividendDraftSelectable, dividendStatusLabel, dividendStatusType, submitTrans, resetForm, fetchData, markFeeManual, saveFeeSettings, resetFeeSettings, addFeeAccount, removeFeeAccount, onActiveFeeAccountChange,
            downloadTransactionsTemplate, exportTransactions, importTransactions, downloadDepositsTemplate, exportDeposits, importDeposits, downloadDividendTemplate, importDividends,
            queryAssetByCode, queryAssetByName, selectTransAsset, autoMatchTransAsset,
            openDepositDialog, saveDeposit, deleteDeposit, updateCash, queryCashFlows, resetCashFlowQuery, addCashFlow, openCashFlowEditDialog, saveCashFlowEdit, deleteCashFlow, cashFlowTagType, fetchCashAudit,
            createSnapshot, fetchSnapshots, exportSnapshots, compactSnapshots, showTransactions,
            queryTransactions, applyTransFilter, resetTransQuery, handleTransPageChange, handleTransPageSizeChange, goPendingTransactions, openTransEditDialog, saveTransactionEdit, deleteTransaction, parseNlEntry,
            openExpectedReturnDialog, saveExpectedReturn, openHoldingCorrectionDialog, saveHoldingCorrection, openHoldingCorrectionHistory, deleteHoldingCorrection,
            expectedReturnDialog, holdingCorrectionDialog, holdingCorrectionHistoryDialog,
            formatMoney, formatPercent, pct, holdingFloatProfit, holdingLifetimeProfit, holdingFloatProfitRate, holdingLifetimeProfitRate,
            perfSummary, perfTimeline, perfContribution, perfFlows, perfStory, perfLoading, perfFlowForm, hasPerfFlows, perfStoryToneType, perfPrimaryCards, perfSecondaryCards, perfCards, perfCategoryBars,
            displayedPerfContribution, perfContributionFilter, perfContributionSort, perfContributionHeadline, perfContributionMix, perfTimelineRange,
            fetchPerformance, setPerfTimelineRange, addPerfFlow, updatePerfFlow, deletePerfFlow, loadPerfFlowSuggestions, applyPerfFlowSuggestion, contributionBarStyle, fetchMaintenance, createDbBackup, downloadBackup, restoreBackup, deleteBackup, restoreUploadedBackup,
            perfRiskMetrics, perfContributionSummary, perfWindowCards, selectPerfWindow,
            perfDailyRows, perfDailyStats, perfLatestSnapshotDate, perfTodayPnl, perfTodayRow,
            refreshCurrentTab,
            notifyStatus, notifyLogs, notifyLoading, notifyEventDraft, notifyChannelDraft, notifyChannelClear, fetchNotifyPanel, saveNotifyPanel, testNotifyPush, pushDepositDueNow, pushDisciplineNow,
            brokerResult, brokerLoading, brokerSelected, brokerAsOfDate, brokerCashInput, brokerHistory,
            statusLabel: brokerStatusLabel, statusType: brokerStatusType,
            onBrokerFileChange, onBrokerSelectionChange, selectAllSuggestions, clearBrokerSelection, applySelectedCorrections, fetchBrokerHistory,
            marketSummary, alertRules, alertEvents, marketLoading, alertChecking, alertEventsLoading, alertForm, alertEditDialog, triggeredAlerts,
            alertEventCodeFilter, alertEventStartDate, alertEventEndDate, watchlistDraft, watchlistSaving,
            fetchMarketSummary, fetchAlertRules, fetchAlertEvents, exportAlertEvents, clearAlertEvents, refreshMarket, resetAlertForm, saveAlertRule, openAlertCreate, openAlertEdit, parseNlRule,
            toggleAlertEnabled, deleteAlertRule, checkAlerts, addWatchlistRow, removeWatchlistRow, saveWatchlist,
            indexRows, watchlistRows, holdingsDayRows, marketSignals, marketHighlights, marketComparisons, marketUpdatedAt, quoteCacheSeconds, alertCooldownMinutes,
            disciplineReport, disciplineDrafts, disciplinePolicy, disciplineLoading, disciplineDraftLoading, disciplinePolicyDialog,
            disciplineDraftEditDialog, disciplineDraftEditForm, disciplineSelectedDraftIds,
            disciplinePresets, disciplinePresetActiveId, disciplinePresetLoading,
            fetchDisciplineReport, fetchDisciplineDrafts, fetchDisciplinePresets, applyDisciplinePreset, refreshDiscipline, openPolicyDialog, cancelPolicy, savePolicy, greeReducePct, createDraftsFromReport,
            openDraftEdit, saveDraftEdit, deleteDraft, confirmDraft, onDraftSelectionChange, confirmSelectedDrafts,
            breaches, actions, planItems, helpNotes, snapshot, targets, summaryText,
        };
        provide(APP_CTX_KEY, appCtx);
        return appCtx;
    }
});
app.use(pinia);
app.use(router);
app.mount('#app');

// 生产环境下注册 Service Worker，支持移动端/Web PWA 离线外壳与安装至主屏幕。
// 本地开发、单进程本地直接运行或 Tauri 桌面外壳环境跳过注册，避免本地磁盘代码与 SW 缓存产生版本滞后。
const isDesktopOrLocal =
    typeof window !== 'undefined' &&
    (window.__TAURI_INTERNALS__ !== undefined ||
     window.location.hostname === '127.0.0.1' ||
     window.location.hostname === 'localhost');

if ('serviceWorker' in navigator) {
    if (isDesktopOrLocal) {
        // 桌面壳或本地直接运行模式：若此前误注册过，主动注销并清理旧缓存，保持磁盘实时性
        navigator.serviceWorker.getRegistrations().then((registrations) => {
            let unregisteredAny = false;
            for (const registration of registrations) {
                registration.unregister().catch(() => {});
                unregisteredAny = true;
            }
            // 若确实注销了控制页面的旧 SW，静默 reload 一次使页面彻底脱钩，
            // 避免旧 SW 在当前生命周期内继续写入 CacheStorage；sessionStorage 防重复刷新。
            if (unregisteredAny && !sessionStorage.getItem('sw_unregistered_reload')) {
                sessionStorage.setItem('sw_unregistered_reload', '1');
                window.location.reload();
            }
        }).catch(() => {});
        if ('caches' in window) {
            caches.keys().then((keys) => {
                for (const key of keys) {
                    if (key.startsWith('invest-tracker-')) {
                        caches.delete(key).catch(() => {});
                    }
                }
            }).catch(() => {});
        }
    } else if (import.meta.env.PROD) {
        window.addEventListener('load', () => {
            navigator.serviceWorker.register('/sw.js').catch((err) => {
                console.warn('PWA service worker registration failed:', err);
            });
        });
    }
}
