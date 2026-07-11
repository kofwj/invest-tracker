import { createApp, ref, onMounted, nextTick, watch, computed } from 'vue/dist/vue.esm-bundler.js';
import ElementPlus, { ElLoading, ElMessage, ElMessageBox } from 'element-plus';
import zhCn from 'element-plus/es/locale/lang/zh-cn';
import 'element-plus/dist/index.css';
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
} from './utils/index.js';
import api, { API } from './api/index.js';
import { createTransactionsModule } from './modules/transactions.js';
import { createDepositsModule } from './modules/deposits.js';
import { createCashModule } from './modules/cash.js';
import { createSnapshotsModule } from './modules/snapshots.js';
import { createPerformanceModule } from './modules/performance.js';
import { createAuthMask } from './composables/authMask.js';
import {
    createFeeHelpers,
    createDividendHelpers,
    createMaintenanceHelpers,
    createImportExportHelpers,
    createAllocationAnalysis,
} from './composables/domainHelpers.js';
import './styles/styles.css';

const todayLocalIso = () => {
    const d = new Date();
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
};

const app = createApp({
    setup() {
        const screenshotParams = new URLSearchParams(window.location.search);
        const screenshotTabs = ['snapshots', 'allocation', 'performance', 'holdings', 'deposits', 'transactions', 'cash'];
        const requestedTab = screenshotParams.get('tab');

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

        const activeTab = ref(screenshotTabs.includes(requestedTab) ? requestedTab : 'snapshots');
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
            form: { bank_name: '', amount: 0, interest_rate: 0, due_date: '', remark: '' }
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

        const { calculateAllocationAnalysis } = createAllocationAnalysis({
            holdings,
            deposits,
            dashboard,
            pendingTransactions,
            allocationAnalysis,
            macroAllocationAnalysis,
            portfolioExpectedReturn,
        });

        const allocationSummary = computed(() => {
            const total = Number(dashboard.value.total_assets || 0);
            const getGroup = (name) => macroAllocationAnalysis.value.find(x => x.group === name) || { amount: 0, percentage: 0, expected_return: 0 };
            const equity = getGroup('权益');
            const fixed = getGroup('固收');
            const deposit = getGroup('存款');
            const defensiveAmount = Number(fixed.amount || 0) + Number(deposit.amount || 0);
            const equityRatio = Number(equity.percentage || 0);
            const defensiveRatio = total > 0 ? defensiveAmount / total * 100 : 0;
            let comment = '当前配置以稳健防守为主，权益、固收和存款比例可在这里快速核对。';
            if (equityRatio > 55) comment = '权益资产占比偏高，若市场回撤，组合波动会明显放大。';
            else if (equityRatio < 35) comment = '权益资产占比较低，组合更稳，但长期收益弹性可能不足。';
            else comment = '权益占比处于相对均衡区间，固收和存款仍能提供较强缓冲。';
            return { total, equityAmount: Number(equity.amount || 0), equityRatio, defensiveAmount, defensiveRatio, fixedAmount: Number(fixed.amount || 0), depositAmount: Number(deposit.amount || 0), comment };
        });

        const allocationHealth = computed(() => {
            const eq = allocationSummary.value.equityRatio;
            const defensive = allocationSummary.value.defensiveRatio;
            const maxCat = allocationAnalysis.value.length ? allocationAnalysis.value[0] : null;
            const pending = Number(dashboard.value.pending_purchase || 0);
            return [
                {
                    label: '权益波动暴露',
                    status: eq > 55 ? '偏高' : (eq < 35 ? '偏低' : '适中'),
                    type: eq > 55 ? 'warning' : 'success',
                    text: `权益占总资产 ${eq.toFixed(1)}%，用于判断组合对股市波动的敏感度。`
                },
                {
                    label: '防守缓冲',
                    status: defensive >= 40 ? '充足' : '偏少',
                    type: defensive >= 40 ? 'success' : 'warning',
                    text: `固收、证券现金、银行存款和申购在途合计 ${defensive.toFixed(1)}%，是组合回撤缓冲。`
                },
                {
                    label: '单类集中度',
                    status: maxCat && maxCat.percentage > 35 ? '集中' : '分散',
                    type: maxCat && maxCat.percentage > 35 ? 'warning' : 'success',
                    text: maxCat ? `${maxCat.category} 占 ${maxCat.percentage.toFixed(1)}%，金额 ${formatMoney(maxCat.market_value)}。` : '暂无资产分类数据。'
                },
                {
                    label: '申购在途',
                    status: pending > 0 ? '待确认' : '无',
                    type: pending > 0 ? 'info' : 'success',
                    text: pending > 0 ? `当前申购在途 ${formatMoney(pending)}，已计入固收/总资产，但不计入持仓盈亏。` : '当前没有申购待确认资产。'
                }
            ];
        });

        const depositRows = computed(() => {
            const total = deposits.value.reduce((sum, d) => sum + Number(d.amount || 0), 0);
            return [...deposits.value]
                .map(d => {
                    const amount = Number(d.amount || 0);
                    const rate = Number(d.interest_rate || 0);
                    return {
                        ...d,
                        amount,
                        interest_rate: rate,
                        annual_interest: amount * rate / 100,
                        percentage: total > 0 ? amount / total * 100 : 0,
                        daysLeft: daysUntil(d.due_date)
                    };
                })
                .sort((a, b) => {
                    if (a.daysLeft === null && b.daysLeft === null) return 0;
                    if (a.daysLeft === null) return 1;
                    if (b.daysLeft === null) return -1;
                    return a.daysLeft - b.daysLeft;
                });
        });

        const depositSummary = computed(() => {
            const rows = depositRows.value;
            const total = rows.reduce((sum, d) => sum + d.amount, 0);
            const annualInterest = rows.reduce((sum, d) => sum + d.annual_interest, 0);
            const weightedRate = total > 0 ? annualInterest / total * 100 : 0;
            const nextDue = rows.find(d => d.daysLeft !== null && d.daysLeft >= 0) || null;
            return { total, annualInterest, weightedRate, count: rows.length, nextDue };
        });

        const depositBankBreakdown = computed(() => {
            const map = {};
            depositRows.value.forEach(d => {
                const key = d.bank_name || '未命名';
                map[key] = (map[key] || 0) + d.amount;
            });
            const total = depositSummary.value.total;
            return Object.keys(map)
                .map(bank_name => ({ bank_name, amount: map[bank_name], percentage: total > 0 ? map[bank_name] / total * 100 : 0 }))
                .sort((a, b) => b.amount - a.amount);
        });

        const depositMaturityBuckets = computed(() => {
            const buckets = [
                { bucket: '30天内', amount: 0 },
                { bucket: '31-90天', amount: 0 },
                { bucket: '91-180天', amount: 0 },
                { bucket: '180天以上', amount: 0 },
                { bucket: '未设置到期', amount: 0 }
            ];
            depositRows.value.forEach(d => {
                const days = d.daysLeft;
                if (days === null) buckets[4].amount += d.amount;
                else if (days <= 30) buckets[0].amount += d.amount;
                else if (days <= 90) buckets[1].amount += d.amount;
                else if (days <= 180) buckets[2].amount += d.amount;
                else buckets[3].amount += d.amount;
            });
            const total = depositSummary.value.total;
            return buckets.map(b => ({ ...b, percentage: total > 0 ? b.amount / total * 100 : 0 }));
        });

        const snapshotInsights = computed(() => {
            const rowsAsc = [...snapshots.value].sort((a, b) => String(a.date).localeCompare(String(b.date)));
            const latest = rowsAsc[rowsAsc.length - 1] || null;
            const first = rowsAsc[0] || null;
            const total = Number(latest?.total_assets || 0);
            const liquid = Number(latest?.bank_balance || 0) + Number(latest?.securities_cash || 0) + Number(latest?.pending_purchase || 0);
            const latestMain = latest ? `${latest.date} · ${latest.holdings_count || 0} 个持仓` : '暂无快照';
            const latestSub = latest ? `总资产 ${formatMoney(latest.total_assets)}，投资市值 ${formatMoney(latest.total_market_value)}` : '请先记录快照';

            let focusMain = '至少需要两条快照';
            let focusSub = '区间变化需要期初与期末对比';
            if (rowsAsc.length >= 2 && first && latest) {
                const totalDelta = Number(latest.total_assets || 0) - Number(first.total_assets || 0);
                const profitDelta = Number(latest.total_profit || 0) - Number(first.total_profit || 0);
                focusMain = `总资产 ${formatMoney(totalDelta, 2, true)}`;
                focusSub = `投资盈亏 ${formatMoney(profitDelta, 2, true)} · 区间 ${first.date} → ${latest.date}`;
            }

            const defensiveRatio = total > 0 ? liquid / total * 100 : 0;
            const bufferMain = total > 0 ? `缓冲资产 ${defensiveRatio.toFixed(1)}%` : '暂无缓冲数据';
            const bufferSub = total > 0 ? `现金+存款+在途 ${formatMoney(liquid)}，总资产 ${formatMoney(total)}` : '请先记录快照';

            return [
                { main: latestMain, sub: latestSub },
                { main: focusMain, sub: focusSub },
                { main: bufferMain, sub: bufferSub }
            ];
        });

        const renderAllocationCharts = async () => {
            const { renderAllocationChartsView } = await import('./charts/index.js');
            renderAllocationChartsView(macroAllocationAnalysis.value, allocationAnalysis.value);
        };

        const fetchData = async () => {
            const [dashRes, holdRes, depRes, cashRes, feeRes] = await Promise.all([
                api.getDashboard(),
                api.getHoldings(),
                api.getDeposits(),
                api.getSecuritiesCash(),
                api.getFeeSettings()
            ]);
            dashboard.value = dashRes.data;
            holdings.value = holdRes.data;
            deposits.value = depRes.data;
            cashForm.value.amount = cashRes.data.amount;
            loadFeeSettingsToForm(feeRes.data || {});
            if (!cashFlowForm.value.account) cashFlowForm.value.account = activeFeeAccount.value || '华泰证券';
            calculateAllocationAnalysis();
            if (activeTab.value === 'allocation') renderAllocationCharts();
        };

        const syncPrices = async () => {
            syncing.value = true;
            showSyncNotice('正在同步最新价...', 'success');
            try {
                const priceRes = await api.syncPrices();
                const priceData = priceRes.data || {};
                const priceFailedCount = Array.isArray(priceData.failed) ? priceData.failed.length : 0;
                const msg = `最新价同步完成：检查 ${priceData.checked || 0} 个，价格变化 ${priceData.updated || 0} 个，无变化 ${priceData.unchanged || 0} 个，失败 ${priceFailedCount} 个`;
                const priceFailedText = priceFailedCount > 0
                    ? priceData.failed.slice(0, 3).map(x => `${x.code} ${x.name || ''}: ${x.reason || '失败'}`).join('；')
                    : '';

                syncing.value = false;
                if (priceFailedText) {
                    showSyncNotice(msg + '。' + priceFailedText, 'warning');
                } else {
                    showSyncNotice(msg, 'success');
                }

                fetchData().catch(refreshErr => {
                    const refreshDetail = refreshErr?.response?.data?.detail || refreshErr?.message || '未知错误';
                    showSyncNotice(msg + `。但刷新页面数据失败：${refreshDetail}`, 'warning');
                });
            } catch (e) {
                const detail = e?.response?.data?.detail || e?.message || '未知错误';
                showSyncNotice('最新价同步失败：' + detail, 'error');
            } finally {
                syncing.value = false;
            }
        };

        const syncTrailingReturns = async () => {
            trailingSyncing.value = true;
            const loading = ElLoading.service({ text: '正在同步近一年标的收益率...', background: 'rgba(255, 255, 255, 0.65)' });
            try {
                const res = await api.syncTrailingReturns();
                await fetchData();
                const data = res.data || {};
                const failedCount = Array.isArray(data.failed) ? data.failed.length : 0;
                const msg = `近一年收益率同步完成：检查 ${data.checked || 0} 个，成功 ${data.updated || 0} 个，失败 ${failedCount} 个`;
                if (failedCount > 0) {
                    const failedText = data.failed.slice(0, 3).map(x => `${x.code} ${x.name || ''}: ${x.reason || '失败'}`).join('；');
                    showSyncNotice(msg + '。' + failedText, 'warning');
                    ElMessage.warning(msg + '。' + failedText);
                } else {
                    showSyncNotice(msg, '');
                }
            } catch (e) {
                const detail = e?.response?.data?.detail || e?.message || '未知错误';
                showSyncNotice('近一年收益率同步失败：' + detail, 'error');
                ElMessage.error('近一年收益率同步失败：' + detail);
            } finally {
                loading.close();
                trailingSyncing.value = false;
            }
        };

        const assetOptions = () => holdings.value.map(h => ({
            value: `${h.code} ${h.name} ${h.category || ''}`,
            code: h.code,
            name: h.name,
            category: h.category || '',
            label: `${h.code} - ${h.name} - ${h.category || '未分类'}`
        }));

        const queryAssetByCode = (queryString, cb) => {
            const q = normalizeText(queryString);
            const results = assetOptions()
                .filter(a => !q || normalizeText(a.code).includes(q) || normalizeText(a.name).includes(q))
                .map(a => ({ ...a, value: a.code, label: a.label }));
            cb(results);
        };

        const queryAssetByName = (queryString, cb) => {
            const q = normalizeText(queryString);
            const results = assetOptions()
                .filter(a => !q || normalizeText(a.name).includes(q) || normalizeText(a.code).includes(q))
                .map(a => ({ ...a, value: a.name, label: a.label }));
            cb(results);
        };

        const selectTransAsset = (asset) => {
            transForm.value.code = asset.code;
            transForm.value.name = asset.name;
            transForm.value.category = asset.category || '';
        };

        const autoMatchTransAsset = (field, rawValue = null) => {
            const codeQ = normalizeText(field === 'code' && rawValue !== null ? rawValue : transForm.value.code);
            const nameQ = normalizeText(field === 'name' && rawValue !== null ? rawValue : transForm.value.name);
            if (!codeQ && !nameQ) {
                transForm.value.category = '';
                return;
            }

            let match = null;
            if (field === 'code' && codeQ) {
                match = holdings.value.find(h => normalizeText(h.code) === codeQ);
            } else if (field === 'name' && nameQ) {
                match = holdings.value.find(h => normalizeText(h.name) === nameQ);
                if (!match) {
                    const candidates = holdings.value.filter(h => normalizeText(h.name).includes(nameQ));
                    if (candidates.length === 1) match = candidates[0];
                }
            }

            if (match) {
                transForm.value.code = match.code;
                transForm.value.name = match.name;
                transForm.value.category = match.category || inferCategoryByCode(match.code, match.name);
            } else {
                transForm.value.category = inferCategoryByCode(transForm.value.code, transForm.value.name);
            }
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
            autoMatchTransAsset,
            estimateFeeIfAuto,
            fetchData,
        });

        const { openDepositDialog, saveDeposit, deleteDeposit } = createDepositsModule({ depositDialog, fetchData });

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
            computed,
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
        } = createImportExportHelpers({
            todayLocalIso,
            queryTransactions,
            fetchData,
            transQuery,
        });

        const { createSnapshot, buildSnapshotAnalysis, renderSnapshotCharts, fetchSnapshots, exportSnapshots, compactSnapshots } = createSnapshotsModule({
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
        } = createMaintenanceHelpers({
            maintenanceStatus,
            backups,
            maintenanceLoading,
            fetchData,
            fetchSnapshots,
            queryTransactions,
            API,
        });

        const openExpectedReturnDialog = (row) => {
            expectedReturnDialog.value = {
                visible: true,
                form: {
                    code: row.code,
                    name: row.name,
                    expected_return: row.expected_return ?? 0
                }
            };
        };

        const saveExpectedReturn = async () => {
            try {
                const code = expectedReturnDialog.value.form.code;
                const expected_return = expectedReturnDialog.value.form.expected_return;
                await api.updateExpectedReturn(code, expected_return);
                ElMessage.success('更新成功');
                expectedReturnDialog.value.visible = false;
                await fetchData();
            } catch (e) {
                ElMessage.error('更新失败');
            }
        };

        const openHoldingCorrectionDialog = (row) => {
            holdingCorrectionDialog.value = {
                visible: true,
                current: { ...row },
                form: {
                    date: todayLocalIso(),
                    code: row.code,
                    name: row.name,
                    category: row.category || '',
                    actual_quantity: Number(row.quantity || 0),
                    actual_avg_cost: Number(row.avg_cost || 0),
                    actual_total_dividend: Number(row.total_dividend || 0),
                    remark: '按券商持仓页面强制校正'
                }
            };
        };

        const saveHoldingCorrection = async () => {
            try {
                const f = holdingCorrectionDialog.value.form;
                if (!f.date || !f.code) return ElMessage.warning('校正日期和代码不能为空');
                await api.addHoldingCorrection(f);
                ElMessage.success('持仓校正已保存，并已重新计算持仓');
                holdingCorrectionDialog.value.visible = false;
                await fetchData();
            } catch (e) {
                ElMessage.error(e?.response?.data?.detail || '保存持仓校正失败');
            }
        };

        const openHoldingCorrectionHistory = async (row) => {
            try {
                const res = await api.listHoldingCorrections(row.code);
                holdingCorrectionHistoryDialog.value = {
                    visible: true,
                    title: `${row.name} (${row.code}) 持仓校正记录`,
                    records: res.data || []
                };
            } catch (e) {
                ElMessage.error('获取校正记录失败');
            }
        };

        const deleteHoldingCorrection = async (row) => {
            try {
                await ElMessageBox.confirm(`确定删除 ${row.date} ${row.code} 的持仓校正？删除后会按交易记录重新计算。`, '确认删除', { type: 'warning' });
                await api.deleteHoldingCorrection(row.id);
                ElMessage.success('校正记录已删除，并已重新计算持仓');
                holdingCorrectionHistoryDialog.value.records = holdingCorrectionHistoryDialog.value.records.filter(x => x.id !== row.id);
                await fetchData();
            } catch (e) {}
        };

        const todayIso = computed(() => todayLocalIso());
        const todaySnapshotDone = computed(() => dashboard.value.latest_snapshot_date === todayIso.value);
        const latestPriceStatusText = computed(() => dashboard.value.latest_price_updated_at ? String(dashboard.value.latest_price_updated_at).replace('T', ' ').slice(0, 19) : '暂无同步记录');
        const latestBackupText = computed(() => maintenanceStatus.value.latest_backup_at ? String(maintenanceStatus.value.latest_backup_at).replace('T', ' ').slice(0, 19) : '暂无备份');

        const perfSummary = ref(null);
        const perfTimeline = ref([]);
        const perfContribution = ref([]);
        const perfFlows = ref([]);
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
            deletePerfFlow,
        } = createPerformanceModule({
            perfSummary,
            perfTimeline,
            perfContribution,
            perfFlows,
            perfLoading,
            perfContributionFilter,
            perfContributionSort,
            perfFlowForm,
            showSyncNotice,
            nextTick,
            computed,
        });

        watch(activeTab, (val) => {
            if (val === 'transactions') queryTransactions();
            if (val === 'allocation') nextTick(renderAllocationCharts);
            if (val === 'performance') fetchPerformance();
            if (val === 'snapshots') {
                fetchSnapshots().then(() => nextTick(renderSnapshotCharts));
            }
            if (val === 'maintenance') fetchMaintenance();
        });

        bootstrapAfterAuth = async () => {
            await Promise.all([
                fetchData(),
                queryTransactions(),
                queryCashFlows(),
                fetchSnapshots(),
                fetchMaintenance(),
            ]);
        };

        onMounted(async () => {
            try {
                const statusRes = await api.getAuthStatus();
                authEnabled.value = statusRes.data.auth_enabled;
                if (authEnabled.value) {
                    const token = localStorage.getItem('invest_tracker_token');
                    if (!token) {
                        showLoginOverlay.value = true;
                        return;
                    }
                }
            } catch (e) {
                console.error('获取登录状态失败', e);
            }
            await bootstrapAfterAuth();
        });

        return {
            isMasked, toggleMask,
            showLoginOverlay, loginLoading, loginPassword, loginError, authEnabled, handleLogin, handleLogout,
            activeTab, dashboard, holdings, deposits, depositRows, depositSummary, depositBankBreakdown, depositMaturityBuckets, syncing, trailingSyncing, syncNotice,
            snapshots, snapshotRange, snapshotSummary, snapshotMetrics, snapshotChangeRows, snapshotInsights, snapshotLoading, maintenanceStatus, backups, maintenanceLoading, dividendLoading, dividendConfirming, dividendDialog, dividendTableRef, todayIso, todaySnapshotDone, latestPriceStatusText, latestBackupText,
            transForm, feeSettings, feeAccounts, activeFeeAccount, newFeeAccountName, feeCategories, feeSettingRows, feeAutoHint, depositDialog, cashForm, cashFlows, cashFlowForm, cashFlowQuery, cashFlowSummary, cashFlowEditDialog, transDialog, allocationAnalysis, macroAllocationAnalysis,
            allocationSummary, allocationHealth, portfolioExpectedReturn, expectedReturnDialog, holdingCorrectionDialog, holdingCorrectionHistoryDialog,
            allTransactions, filteredTransactions, pendingTransactions, pendingPurchaseTotal, transQuery, transPage, transEditDialog,
            syncPrices, syncTrailingReturns, openDividendDraftDialog, scanDividendDrafts, confirmSelectedDividends, selectSelectableDividendDrafts, clearDividendDraftSelection, onDividendSelectionChange, isDividendDraftSelectable, dividendStatusLabel, dividendStatusType, submitTrans, resetForm, fetchData, markFeeManual, saveFeeSettings, resetFeeSettings, addFeeAccount, removeFeeAccount, onActiveFeeAccountChange,
            downloadTransactionsTemplate, exportTransactions, importTransactions, downloadDepositsTemplate, exportDeposits, importDeposits,
            queryAssetByCode, queryAssetByName, selectTransAsset, autoMatchTransAsset,
            openDepositDialog, saveDeposit, deleteDeposit, updateCash, queryCashFlows, resetCashFlowQuery, addCashFlow, openCashFlowEditDialog, saveCashFlowEdit, deleteCashFlow, cashFlowTagType,
            createSnapshot, fetchSnapshots, exportSnapshots, compactSnapshots, showTransactions,
            queryTransactions, applyTransFilter, resetTransQuery, handleTransPageChange, handleTransPageSizeChange, goPendingTransactions, openTransEditDialog, saveTransactionEdit, deleteTransaction,
            openExpectedReturnDialog, saveExpectedReturn, openHoldingCorrectionDialog, saveHoldingCorrection, openHoldingCorrectionHistory, deleteHoldingCorrection, formatMoney, formatPercent, pct, holdingFloatProfit, holdingLifetimeProfit, holdingFloatProfitRate, holdingLifetimeProfitRate,
            perfSummary, perfTimeline, perfContribution, perfFlows, perfLoading, perfFlowForm, hasPerfFlows, perfGuideSteps, perfLensRows, perfReadTips, perfCards,
            displayedPerfContribution, perfContributionFilter, perfContributionSort, perfContributionHeadline, perfContributionMix,
            fetchPerformance, addPerfFlow, deletePerfFlow, contributionBarStyle, fetchMaintenance, createDbBackup, downloadBackup, restoreBackup, deleteBackup, restoreUploadedBackup
        };
    }
});
app.use(ElementPlus, { locale: zhCn });
app.mount('#app');
