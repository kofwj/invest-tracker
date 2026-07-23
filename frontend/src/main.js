import { createApp, ref, onMounted, nextTick, watch, provide } from 'vue';
import { ElLoading, ElMessage, ElMessageBox } from 'element-plus';
import zhCn from 'element-plus/es/locale/lang/zh-cn';
import 'element-plus/es/components/message/style/css';
import 'element-plus/es/components/message-box/style/css';
import 'element-plus/es/components/loading/style/css';
import App from './App.vue';
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
import api, { API } from './api/index.js';
import { createTransactionsModule } from './modules/transactions.js';
import { createDepositsModule } from './modules/deposits.js';
import { createCashModule } from './modules/cash.js';
import { createSnapshotsModule } from './modules/snapshots.js';
import { createPerformanceModule } from './modules/performance.js';
import { createBrokerReconcileModule } from './modules/brokerReconcile.js';
import { createMarketModule } from './modules/market.js';
import { createDisciplineModule } from './modules/discipline.js';
import { createHoldingCorrectionHelpers } from './modules/holdingCorrections.js';
import { createUziAnalysisHelper } from './modules/uziAnalysis.js';
import { createDataSync } from './modules/dataSync.js';
import { createAuthMask } from './composables/authMask.js';
import {
    createFeeHelpers,
    createMaintenanceHelpers,
    createImportExportHelpers,

} from './composables/domainHelpers.js';
import { createDividendHelpers } from './modules/dividends.js';
import { createAllocationModule } from './modules/allocation.js';
import { createAppInit } from './modules/appInit.js';
import { createBriefHelpers } from './modules/brief.js';
import { TAB_GROUPS, tabGroupOf, resolveInitialTab } from './modules/tabNav.js';
import './styles/styles.css';

const app = createApp({
    extends: App,
    setup() {
        const tabGroups = TAB_GROUPS;

        // Deferred bootstrap after login unlock (wired below after helpers exist)
        let bootstrapAfterAuth = async () => {};

        const {
            isMasked,
            toggleMask,
            showLoginOverlay,
            loginLoading,
            loginPassword,
            loginError,
            authEnabled,
            handleLogin,
            handleLogout,
        } = createAuthMask({
            onUnlocked: () => bootstrapAfterAuth(),
        });

        const activeTab = ref(resolveInitialTab());
        const tabGroup = ref(tabGroupOf(activeTab.value));
        watch(tabGroup, (gid) => {
            const g = tabGroups.find(x => x.id === gid);
            if (g && !g.tabs.includes(activeTab.value)) activeTab.value = g.tabs[0];
        });
        watch(activeTab, (tab) => {
            const gid = tabGroupOf(tab);
            if (tabGroup.value !== gid) tabGroup.value = gid;
        });
        const dashboard = ref({});
        const holdings = ref([]);
        const deposits = ref([]);
        const syncing = ref(false);
        const trailingSyncing = ref(false);
        const syncNotice = ref({ text: '', type: '' });
        let syncNoticeTimer = null;
        const showSyncNotice = (text, type = '') => {
            syncNotice.value.text = text;
            syncNotice.value.type = type;
            if (syncNoticeTimer) clearTimeout(syncNoticeTimer);
            syncNoticeTimer = setTimeout(() => {
                syncNotice.value.text = '';
                syncNotice.value.type = '';
            }, 12000);
        };
        const cashForm = ref({ amount: 0 });
        const cashFlows = ref([]);
        const cashFlowForm = ref({ date: todayLocalIso(), account: '华泰证券', flow_type: '银证转入', amount: 0, remark: '' });
        const cashFlowQuery = ref({ dateRange: [], account: '', flow_type: '' });
        const cashFlowEditDialog = ref({ visible: false, editId: null, form: { date: '', account: '', flow_type: '', amount: 0, remark: '' } });
        const snapshots = ref([]);
        const snapshotRange = ref([]);
        const snapshotSummary = ref(null);
        const snapshotMetrics = ref([]);
        const snapshotChangeRows = ref([]);
        const snapshotLoading = ref(false);
        const maintenanceStatus = ref({});
        const backups = ref([]);
        const maintenanceLoading = ref(false);
        const dividendLoading = ref(false);
        const dividendConfirming = ref(false);
        const dividendTableRef = ref(null);
        const dividendDialog = ref({
            visible: false,
            lookbackDays: 400,
            drafts: [],
            selected: [],
            summary: null,
            unsupported: [],
            failed: [],
        });

        const transForm = ref({
            date: todayLocalIso(),
            code: '', name: '', category: '', account: '华泰证券', direction: '买入',
            quantity: 0, price: 0, amount: 0, fee: 0
        });
        const feeManuallyEdited = ref(false);
        const feeSettings = ref({});
        const feeAccounts = ref(['华泰证券']);
        const activeFeeAccount = ref('华泰证券');
        const newFeeAccountName = ref('');
        const feeCategories = ['A股权益', 'A股ETF', '港股ETF', 'REITs', '黄金', '债基', '其他'];
        const feeAutoHint = ref('');

        const depositDialog = ref({
            visible: false, isEdit: false, editId: null,
            form: { bank_name: '', amount: 0, interest_rate: 0, start_date: '', due_date: '', remark: '' }
        });

        const transDialog = ref({
            visible: false,
            title: '',
            transactions: []
        });

        const allTransactions = ref([]);
        const filteredTransactions = ref([]);
        const pendingTransactions = ref([]);
        const pendingPurchaseTotal = ref(0);
        const transPage = ref({ page: 1, pageSize: 100, total: 0 });
        const transQuery = ref({
            dateRange: [],
            code: '',
            name: '',
            direction: ''
        });
        const transEditDialog = ref({
            visible: false,
            editId: null,
            form: { date: '', code: '', name: '', category: '', account: '', direction: '', quantity: 0, price: 0, amount: 0, fee: 0, remark: '' }
        });

        const expectedReturnDialog = ref({
            visible: false,
            form: { code: '', name: '', expected_return: 0 }
        });
        const holdingCorrectionDialog = ref({
            visible: false,
            current: {},
            form: { date: todayLocalIso(), code: '', name: '', category: '', actual_quantity: 0, actual_avg_cost: 0, actual_total_dividend: 0, remark: '' }
        });
        const holdingCorrectionHistoryDialog = ref({ visible: false, title: '持仓校正记录', records: [] });

        const uziAnalysisDialog = ref({
            visible: false,
            row: null,
            depth: "medium",
            prompt: ""
        });

        const allocationAnalysis = ref([]);
        const macroAllocationAnalysis = ref([]);
        const portfolioExpectedReturn = ref(0);

        const {
            feeSettingRows,
            loadFeeSettingsToForm,
            estimateFeeIfAuto,
            markFeeManual,
            saveFeeSettings,
            resetFeeSettings,
            addFeeAccount,
            removeFeeAccount,
            onActiveFeeAccountChange,
        } = createFeeHelpers({
            feeSettings,
            feeAccounts,
            activeFeeAccount,
            newFeeAccountName,
            feeCategories,
            feeManuallyEdited,
            feeAutoHint,
            transForm,
        });

        const { calculateAllocationAnalysis, allocationSummary, allocationHealth, renderAllocationCharts } = createAllocationModule({
            holdings,
            deposits,
            dashboard,
            pendingTransactions,
            allocationAnalysis,
            macroAllocationAnalysis,
            portfolioExpectedReturn,
        });

        // Core data + sync (extracted to module)
        const {
            fetchData,
            syncPrices,
            syncTrailingReturns,
            todayIso,
            todaySnapshotDone,
            latestPriceStatusText,
            latestBackupText,
        } = createDataSync({
            dashboard,
            holdings,
            deposits,
            cashForm,
            cashFlowForm,
            activeFeeAccount,
            syncing,
            trailingSyncing,
            syncNotice,
            maintenanceStatus,
            loadFeeSettingsToForm,
            calculateAllocationAnalysis,
            activeTab,
            showSyncNotice,
            renderAllocationCharts,
        });

        const {
            openExpectedReturnDialog,
            saveExpectedReturn,
            openHoldingCorrectionDialog,
            saveHoldingCorrection,
            openHoldingCorrectionHistory,
            deleteHoldingCorrection,
        } = createHoldingCorrectionHelpers({
            expectedReturnDialog,
            holdingCorrectionDialog,
            holdingCorrectionHistoryDialog,
            fetchData,
            todayLocalIso,
        });

        // === UZI-Skill 混合分析（防御包装，不影响主流程）===
        let uziFns = {};
        try {
            const uziHelper = createUziAnalysisHelper({ dashboard, formatMoney });

            const openUziAnalysisDialog = (row) => {
                if (!row || !row.code) return;
                const d = 'medium';
                uziAnalysisDialog.value = {
                    visible: true,
                    row: { ...row },
                    depth: d,
                    prompt: uziHelper.buildUziPrompt(row, d)
                };
            };

            const updateUziDepth = (newDepth) => {
                const dlg = uziAnalysisDialog.value;
                if (!dlg || !dlg.row) return;
                dlg.depth = newDepth;
                dlg.prompt = uziHelper.buildUziPrompt(dlg.row, newDepth);
            };

            const copyUziPrompt = async () => {
                const t = uziAnalysisDialog.value?.prompt || '';
                if (!t) return;
                try {
                    await navigator.clipboard.writeText(t);
                    ElMessage.success('提示词已复制，可直接粘贴到本地 Hermes 执行');
                } catch (e) {
                    ElMessage.warning('复制失败，请手动全选复制');
                }
            };

            const closeUziAnalysisDialog = () => {
                uziAnalysisDialog.value.visible = false;
            };

            uziFns = {
                uziAnalysisDialog,
                openUziAnalysisDialog,
                updateUziDepth,
                copyUziPrompt,
                closeUziAnalysisDialog,
            };
        } catch (e) {
            console.warn('[UZI] 初始化失败（不影响主功能）', e);
            uziFns = {
                uziAnalysisDialog: ref({ visible: false, row: null, depth: 'medium', prompt: '' }),
                openUziAnalysisDialog: () => {},
                updateUziDepth: () => {},
                copyUziPrompt: async () => {},
                closeUziAnalysisDialog: () => {},
            };
        }
        const { buildUziPrompt } = createUziAnalysisHelper({ dashboard, formatMoney });

        const openUziAnalysisDialog = (row) => {
            if (!row || !row.code) return;
            const d = "medium";
            uziAnalysisDialog.value = {
                visible: true,
                row: { ...row },
                depth: d,
                prompt: buildUziPrompt(row, d)
            };
        };

        const updateUziDepth = (newDepth) => {
            const dlg = uziAnalysisDialog.value;
            if (!dlg || !dlg.row) return;
            dlg.depth = newDepth;
            dlg.prompt = buildUziPrompt(dlg.row, newDepth);
        };

        const copyUziPrompt = async () => {
            const t = uziAnalysisDialog.value?.prompt || "";
            if (!t) return;
            try {
                await navigator.clipboard.writeText(t);
                ElMessage.success("提示词已复制，可直接粘贴到本地 Hermes 执行");
            } catch (e) {
                ElMessage.warning("复制失败，请手动全选复制");
            }
        };

        const closeUziAnalysisDialog = () => {
            uziAnalysisDialog.value.visible = false;
        };

        const {
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
            // now provided by transactions module (asset helpers merged in)
            queryAssetByCode,
            queryAssetByName,
            selectTransAsset,
            autoMatchTransAsset,
        } = createTransactionsModule({
            activeTab,
            allTransactions,
            filteredTransactions,
            pendingTransactions,
            pendingPurchaseTotal,
            transDialog,
            transEditDialog,
            transForm,
            transQuery,
            transPage,
            activeFeeAccount,
            feeAccounts,
            feeManuallyEdited,
            feeAutoHint,
            holdings,
            estimateFeeIfAuto,
            fetchData,
        });

        const {
            openDepositDialog, saveDeposit, deleteDeposit,
            depositRows, depositSummary, depositBankBreakdown, depositMaturityBuckets,
        } = createDepositsModule({ depositDialog, deposits, fetchData });

        const {
            updateCash,
            queryCashFlows,
            resetCashFlowQuery,
            cashFlowSummary,
            cashFlowTagType,
            addCashFlow,
            openCashFlowEditDialog,
            saveCashFlowEdit,
            deleteCashFlow,
        } = createCashModule({
            dashboard,
            cashForm,
            cashFlows,
            cashFlowForm,
            cashFlowQuery,
            cashFlowEditDialog,
            activeFeeAccount,
            fetchData,
        });

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
        } = createDividendHelpers({
            dividendDialog,
            dividendTableRef,
            dividendLoading,
            dividendConfirming,
            activeFeeAccount,
            fetchData,
            queryTransactions,
        });

        const {
            downloadTransactionsTemplate,
            exportTransactions,
            importTransactions,
            downloadDepositsTemplate,
            exportDeposits,
            importDeposits,
            downloadDividendTemplate,
            importDividends,
        } = createImportExportHelpers({
            todayLocalIso,
            queryTransactions,
            fetchData,
            transQuery,
        });

        const { createSnapshot, buildSnapshotAnalysis, renderSnapshotCharts, fetchSnapshots, exportSnapshots, compactSnapshots, snapshotInsights } = createSnapshotsModule({
            activeTab,
            snapshots,
            snapshotRange,
            snapshotSummary,
            snapshotMetrics,
            snapshotChangeRows,
            snapshotLoading,
            fetchData,
            nextTick,
        });

        const {
            fetchMaintenance,
            createDbBackup,
            downloadBackup,
            restoreBackup,
            deleteBackup,
            restoreUploadedBackup,
            notifyStatus,
            notifyLogs,
            notifyLoading,
            notifyEventDraft,
            fetchNotifyPanel,
            saveNotifyPanel,
            testNotifyPush,
            pushDepositDueNow,
            pushDisciplineNow,
        } = createMaintenanceHelpers({
            maintenanceStatus,
            backups,
            maintenanceLoading,
            fetchData,
            fetchSnapshots,
            queryTransactions,
            API,
        });



        const perfSummary = ref(null);
        const perfTimeline = ref([]);
        const perfContribution = ref([]);
        const perfFlows = ref([]);
        const perfStory = ref(null);
        const perfLoading = ref(false);
        const perfContributionFilter = ref('all');
        const perfContributionSort = ref('contribution');
        const perfFlowForm = ref({
            date: todayLocalIso(),
            flow_type: '投入',
            amount: 100000,
            source: '',
            remark: ''
        });

        const {
            hasPerfFlows,
            perfStoryToneType,
            perfGuideSteps,
            perfLensRows,
            perfReadTips,
            perfCards,
            displayedPerfContribution,
            perfContributionHeadline,
            perfContributionMix,
            contributionBarStyle,
            renderPerfChart,
            fetchPerformance,
            addPerfFlow,
            updatePerfFlow,
            deletePerfFlow,
            loadPerfFlowSuggestions,
            applyPerfFlowSuggestion,
        } = createPerformanceModule({
            perfSummary,
            perfTimeline,
            perfContribution,
            perfFlows,
            perfStory,
            perfLoading,
            perfContributionFilter,
            perfContributionSort,
            perfFlowForm,
            showSyncNotice,
            nextTick,
        });

        const brokerResult = ref(null);
        const brokerLoading = ref(false);
        const brokerSelected = ref([]);
        const brokerAsOfDate = ref(todayLocalIso());
        const brokerCashInput = ref('');
        const {
            statusLabel: brokerStatusLabel,
            statusType: brokerStatusType,
            onBrokerFileChange,
            onBrokerSelectionChange,
            selectAllSuggestions,
            clearBrokerSelection,
            applySelectedCorrections,
        } = createBrokerReconcileModule({
            brokerResult,
            brokerLoading,
            brokerSelected,
            brokerAsOfDate,
            brokerCashInput,
            fetchData,
            showSyncNotice,
        });

        const marketSummary = ref({});
        const alertRules = ref([]);
        const alertEvents = ref([]);
        const marketLoading = ref(false);
        const alertChecking = ref(false);
        const alertEventsLoading = ref(false);
        const alertEditDialog = ref(false);
        const triggeredAlerts = ref([]);
        const alertEventCodeFilter = ref('');
        const alertEventStartDate = ref('');
        const alertEventEndDate = ref('');
        const watchlistDraft = ref([]);
        const watchlistSaving = ref(false);
        const alertForm = ref({
            target_type: 'holding',
            code: '',
            name: '',
            condition: 'above',
            threshold: 0,
            enabled: true,
        });

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
            toggleAlertEnabled,
            deleteAlertRule,
            checkAlerts,
            addWatchlistRow,
            removeWatchlistRow,
            saveWatchlist,
            indexRows,
            watchlistRows,
            holdingsDayRows,
            marketSignals,
            marketHighlights,
            marketComparisons,
            marketUpdatedAt,
            quoteCacheSeconds,
            alertCooldownMinutes,
        } = createMarketModule({
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
        });

        const disciplineReport = ref({});
        const disciplineDrafts = ref([]);
        const disciplinePolicy = ref({
            equity_min_pct: 35,
            equity_max_pct: 55,
            defensive_min_pct: 40,
            single_holding_max_pct: 20,
            rebalance_band_pct: 3,
            preferred_buy_code: '159352',
            preferred_buy_name: '中证A500ETF',
            preferred_buy_category: 'A股ETF',
            preferred_buy_account: '华泰证券',
            targets: { equity_pct: 45, fixed_income_pct: 30, deposit_pct: 25 },
            plans: { a500_batch_target_amount: 200000, gree_soft_max_pct: 15, a500_batch_code: '159352', gree_code: '000651' },
            named_limits: [],
            no_new_codes: [],
        });
        const disciplineLoading = ref(false);
        const disciplineDraftLoading = ref(false);
        const disciplinePolicyDialog = ref(false);
        const disciplineDraftEditDialog = ref(false);
        const disciplineDraftEditForm = ref({});
        const disciplineSelectedDraftIds = ref([]);

        const {
            fetchDisciplineReport,
            fetchDisciplineDrafts,
            refreshDiscipline,
            openPolicyDialog,
            savePolicy,
            createDraftsFromReport,
            openDraftEdit,
            saveDraftEdit,
            deleteDraft,
            confirmDraft,
            onDraftSelectionChange,
            confirmSelectedDrafts,
            breaches,
            actions,
            planItems,
            helpNotes,
            snapshot,
            targets,
            summaryText,
        } = createDisciplineModule({
            disciplineReport,
            disciplineDrafts,
            disciplinePolicy,
            disciplineLoading,
            disciplineDraftLoading,
            disciplinePolicyDialog,
            disciplineDraftEditDialog,
            disciplineDraftEditForm,
            disciplineSelectedDraftIds,
            fetchData,
            queryTransactions,
        });

        watch(activeTab, (val) => {
            if (val === 'transactions') queryTransactions();
            if (val === 'allocation') nextTick(renderAllocationCharts);
            if (val === 'performance') fetchPerformance();
            if (val === 'market') refreshMarket();
            if (val === 'discipline') refreshDiscipline();
            if (val === 'snapshots') {
                fetchSnapshots().then(() => nextTick(renderSnapshotCharts));
            }
            if (val === 'maintenance') {
                fetchMaintenance();
                fetchNotifyPanel();
            }
        });

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
        });

        bootstrapAfterAuth = doBootstrap;

        onMounted(setupOnMounted);


        const { eveningBriefDialog, openEveningBrief } = createBriefHelpers();

        const appCtx = {
            zhCn,
            isMasked, toggleMask,
            showLoginOverlay, loginLoading, loginPassword, loginError, authEnabled, handleLogin, handleLogout,
            activeTab, tabGroup, tabGroups, dashboard, holdings, deposits, depositRows, depositSummary, depositBankBreakdown, depositMaturityBuckets, syncing, trailingSyncing, syncNotice,
            snapshots, snapshotRange, snapshotSummary, snapshotMetrics, snapshotChangeRows, snapshotInsights, snapshotLoading, maintenanceStatus, backups, maintenanceLoading, dividendLoading, dividendConfirming, dividendDialog, dividendTableRef, todayIso, todaySnapshotDone, latestPriceStatusText, latestBackupText,
            transForm, feeSettings, feeAccounts, activeFeeAccount, newFeeAccountName, feeCategories, feeSettingRows, feeAutoHint, depositDialog, cashForm, cashFlows, cashFlowForm, cashFlowQuery, cashFlowSummary, cashFlowEditDialog, transDialog, allocationAnalysis, macroAllocationAnalysis,
            allTransactions, filteredTransactions, pendingTransactions, pendingPurchaseTotal, transQuery, transPage, transEditDialog,
            syncPrices, syncTrailingReturns, openDividendDraftDialog, openEveningBrief, eveningBriefDialog, scanDividendDrafts, confirmSelectedDividends, selectSelectableDividendDrafts, clearDividendDraftSelection, onDividendSelectionChange, isDividendDraftSelectable, dividendStatusLabel, dividendStatusType, submitTrans, resetForm, fetchData, markFeeManual, saveFeeSettings, resetFeeSettings, addFeeAccount, removeFeeAccount, onActiveFeeAccountChange,
            downloadTransactionsTemplate, exportTransactions, importTransactions, downloadDepositsTemplate, exportDeposits, importDeposits, downloadDividendTemplate, importDividends,
            queryAssetByCode, queryAssetByName, selectTransAsset, autoMatchTransAsset,
            openDepositDialog, saveDeposit, deleteDeposit, updateCash, queryCashFlows, resetCashFlowQuery, addCashFlow, openCashFlowEditDialog, saveCashFlowEdit, deleteCashFlow, cashFlowTagType,
            createSnapshot, fetchSnapshots, exportSnapshots, compactSnapshots, showTransactions,
            queryTransactions, applyTransFilter, resetTransQuery, handleTransPageChange, handleTransPageSizeChange, goPendingTransactions, openTransEditDialog, saveTransactionEdit, deleteTransaction,
            openExpectedReturnDialog, saveExpectedReturn, openHoldingCorrectionDialog, saveHoldingCorrection, openHoldingCorrectionHistory, deleteHoldingCorrection, ...Object.values(uziFns), uziAnalysisDialog: uziFns.uziAnalysisDialog, openUziAnalysisDialog: uziFns.openUziAnalysisDialog, updateUziDepth: uziFns.updateUziDepth, copyUziPrompt: uziFns.copyUziPrompt, closeUziAnalysisDialog: uziFns.closeUziAnalysisDialog, formatMoney, formatPercent, pct, holdingFloatProfit, holdingLifetimeProfit, holdingFloatProfitRate, holdingLifetimeProfitRate,
            perfSummary, perfTimeline, perfContribution, perfFlows, perfStory, perfLoading, perfFlowForm, hasPerfFlows, perfStoryToneType, perfGuideSteps, perfLensRows, perfReadTips, perfCards,
            displayedPerfContribution, perfContributionFilter, perfContributionSort, perfContributionHeadline, perfContributionMix,
            fetchPerformance, addPerfFlow, updatePerfFlow, deletePerfFlow, loadPerfFlowSuggestions, applyPerfFlowSuggestion, contributionBarStyle, fetchMaintenance, createDbBackup, downloadBackup, restoreBackup, deleteBackup, restoreUploadedBackup,
            notifyStatus, notifyLogs, notifyLoading, notifyEventDraft, fetchNotifyPanel, saveNotifyPanel, testNotifyPush, pushDepositDueNow, pushDisciplineNow,
            brokerResult, brokerLoading, brokerSelected, brokerAsOfDate, brokerCashInput,
            statusLabel: brokerStatusLabel, statusType: brokerStatusType,
            onBrokerFileChange, onBrokerSelectionChange, selectAllSuggestions, clearBrokerSelection, applySelectedCorrections,
            marketSummary, alertRules, alertEvents, marketLoading, alertChecking, alertEventsLoading, alertForm, alertEditDialog, triggeredAlerts,
            alertEventCodeFilter, alertEventStartDate, alertEventEndDate, watchlistDraft, watchlistSaving,
            fetchMarketSummary, fetchAlertRules, fetchAlertEvents, exportAlertEvents, clearAlertEvents, refreshMarket, resetAlertForm, saveAlertRule, openAlertCreate, openAlertEdit,
            toggleAlertEnabled, deleteAlertRule, checkAlerts, addWatchlistRow, removeWatchlistRow, saveWatchlist,
            indexRows, watchlistRows, holdingsDayRows, marketSignals, marketHighlights, marketComparisons, marketUpdatedAt, quoteCacheSeconds, alertCooldownMinutes,
            disciplineReport, disciplineDrafts, disciplinePolicy, disciplineLoading, disciplineDraftLoading, disciplinePolicyDialog,
            disciplineDraftEditDialog, disciplineDraftEditForm, disciplineSelectedDraftIds,
            fetchDisciplineReport, fetchDisciplineDrafts, refreshDiscipline, openPolicyDialog, savePolicy, createDraftsFromReport,
            openDraftEdit, saveDraftEdit, deleteDraft, confirmDraft, onDraftSelectionChange, confirmSelectedDrafts,
            breaches, actions, planItems, helpNotes, snapshot, targets, summaryText,
        };
        provide(APP_CTX_KEY, appCtx);
        return appCtx;
    }
});
app.mount('#app');