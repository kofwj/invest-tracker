import { createApp, ref, onMounted, nextTick, watch, computed } from 'vue/dist/vue.esm-bundler.js';
import ElementPlus, { ElLoading, ElMessage, ElMessageBox } from 'element-plus';
import 'element-plus/dist/index.css';
import axios from 'axios';
import * as echarts from 'echarts';
import './styles/styles.css';
import './utils/index.js';
import './api/index.js';
import './charts/index.js';
import './modules/transactions.js';
import './modules/deposits.js';
import './modules/cash.js';
import './modules/snapshots.js';
import './modules/performance.js';

window.axios = axios;
window.echarts = echarts;
window.ElementPlus = Object.assign({}, ElementPlus, { ElMessage, ElLoading, ElMessageBox });

const app = createApp({
    setup() {
        const screenshotParams = new URLSearchParams(window.location.search);
        const screenshotTabs = ['snapshots', 'allocation', 'performance', 'holdings', 'deposits', 'transactions', 'cash'];
        const requestedTab = screenshotParams.get('tab');
        const screenshotMode = screenshotParams.get('mask') === '1' || screenshotParams.get('screenshot') === '1';
        if (screenshotMode) {
            document.documentElement.classList.add('screenshot-mask');
        }
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
        const cashFlowForm = ref({ date: new Date().toISOString().split('T')[0], account: '华泰证券', flow_type: '银证转入', amount: 0, remark: '' });
        const cashFlowQuery = ref({ dateRange: [], account: '', flow_type: '' });
        const cashFlowEditDialog = ref({ visible: false, editId: null, form: { date: '', account: '', flow_type: '', amount: 0, remark: '' } });
        const snapshots = ref([]);
        const snapshotRange = ref([]);
        const snapshotSummary = ref(null);
        const snapshotMetrics = ref([]);
        const snapshotChangeRows = ref([]);
        const snapshotLoading = ref(false);

        const transForm = ref({
            date: new Date().toISOString().split('T')[0],
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

        // 交易管理相关
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
            form: { date: new Date().toISOString().split('T')[0], code: '', name: '', category: '', actual_quantity: 0, actual_avg_cost: 0, actual_total_dividend: 0, remark: '' }
        });
        const holdingCorrectionHistoryDialog = ref({ visible: false, title: '持仓校正记录', records: [] });

        const allocationAnalysis = ref([]);
        const macroAllocationAnalysis = ref([]);
        const portfolioExpectedReturn = ref(0);

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
                // 输入代码时只做“精确代码”自动填充；新代码不强行匹配旧持仓，避免误覆盖
                match = holdings.value.find(h => normalizeText(h.code) === codeQ);
            } else if (field === 'name' && nameQ) {
                // 输入名称时：精确匹配优先；若只有一个名称包含结果，再自动对应
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
                // 新标的：保留用户输入的代码/名称，只按规则推断分类；分类可手动改
                transForm.value.category = inferCategoryByCode(transForm.value.code, transForm.value.name);
            }
        };


        const defaultFeeRulePct = () => ({
            commission_rate_pct: 0,
            stamp_tax_rate_pct: 0,
            transfer_fee_rate_pct: 0,
            min_commission: 0
        });

        const defaultFeeRulesPct = () => {
            const defaults = {
                'A股权益': { commission_rate_pct: 0.025, stamp_tax_rate_pct: 0.05, transfer_fee_rate_pct: 0.001, min_commission: 0 },
                'A股ETF': { commission_rate_pct: 0.025, stamp_tax_rate_pct: 0, transfer_fee_rate_pct: 0, min_commission: 0 },
                '港股ETF': { commission_rate_pct: 0.025, stamp_tax_rate_pct: 0, transfer_fee_rate_pct: 0, min_commission: 0 },
                'REITs': { commission_rate_pct: 0.025, stamp_tax_rate_pct: 0, transfer_fee_rate_pct: 0, min_commission: 0 },
                '黄金': { commission_rate_pct: 0.025, stamp_tax_rate_pct: 0, transfer_fee_rate_pct: 0, min_commission: 0 },
                '债基': { commission_rate_pct: 0, stamp_tax_rate_pct: 0, transfer_fee_rate_pct: 0, min_commission: 0 },
                '其他': { commission_rate_pct: 0.025, stamp_tax_rate_pct: 0, transfer_fee_rate_pct: 0, min_commission: 0 }
            };
            feeCategories.forEach(cat => defaults[cat] = { ...defaultFeeRulePct(), ...(defaults[cat] || {}) });
            return defaults;
        };

        const rateToPctRule = (rule = {}) => ({
            commission_rate_pct: Number(rule.commission_rate || 0) * 100,
            stamp_tax_rate_pct: Number(rule.stamp_tax_rate || 0) * 100,
            transfer_fee_rate_pct: Number(rule.transfer_fee_rate || 0) * 100,
            min_commission: Number(rule.min_commission || 0)
        });

        const pctRuleToRate = (rule = {}) => ({
            commission_rate: Number(rule.commission_rate_pct || 0) / 100,
            stamp_tax_rate: Number(rule.stamp_tax_rate_pct || 0) / 100,
            transfer_fee_rate: Number(rule.transfer_fee_rate_pct || 0) / 100,
            min_commission: Number(rule.min_commission || 0)
        });

        const ensureFeeAccount = (account) => {
            const acc = account || activeFeeAccount.value || '华泰证券';
            if (!feeAccounts.value.includes(acc)) feeAccounts.value.push(acc);
            if (!feeSettings.value[acc]) feeSettings.value[acc] = defaultFeeRulesPct();
            feeCategories.forEach(cat => {
                if (!feeSettings.value[acc][cat]) feeSettings.value[acc][cat] = defaultFeeRulePct();
            });
            return acc;
        };

        const normalizeFeeApiData = (data = {}) => {
            // compatible with old API shape: {settings:{category:rule}}
            if (data.settings && !data.accounts && feeCategories.some(cat => data.settings[cat])) {
                return { accounts: ['华泰证券'], active_account: '华泰证券', settings: { '华泰证券': data.settings } };
            }
            return data;
        };

        const loadFeeSettingsToForm = (data) => {
            const normalized = normalizeFeeApiData(data || {});
            const accounts = (normalized.accounts || Object.keys(normalized.settings || {}) || ['华泰证券']).filter(Boolean);
            feeAccounts.value = accounts.length ? [...new Set(accounts)] : ['华泰证券'];
            activeFeeAccount.value = normalized.active_account && feeAccounts.value.includes(normalized.active_account) ? normalized.active_account : feeAccounts.value[0];
            const next = {};
            feeAccounts.value.forEach(acc => {
                next[acc] = {};
                const rules = (normalized.settings || {})[acc] || {};
                feeCategories.forEach(cat => next[acc][cat] = rateToPctRule(rules[cat] || pctRuleToRate(defaultFeeRulesPct()[cat])));
            });
            feeSettings.value = next;
            if (!transForm.value.account) transForm.value.account = activeFeeAccount.value;
            estimateFeeIfAuto();
        };

        const feeSettingRows = computed(() => feeCategories.map(category => ({ category })));

        const onActiveFeeAccountChange = () => {
            ensureFeeAccount(activeFeeAccount.value);
            transForm.value.account = activeFeeAccount.value;
            feeManuallyEdited.value = false;
            estimateFeeIfAuto();
        };

        const addFeeAccount = () => {
            const name = String(newFeeAccountName.value || '').trim();
            if (!name) return ElMessage.warning('请输入账户名称');
            if (feeAccounts.value.includes(name)) return ElMessage.warning('账户已存在');
            feeAccounts.value.push(name);
            feeSettings.value[name] = JSON.parse(JSON.stringify(feeSettings.value[activeFeeAccount.value] || defaultFeeRulesPct()));
            activeFeeAccount.value = name;
            transForm.value.account = name;
            newFeeAccountName.value = '';
            feeManuallyEdited.value = false;
            estimateFeeIfAuto();
        };

        const removeFeeAccount = async () => {
            if (feeAccounts.value.length <= 1) return;
            const acc = activeFeeAccount.value;
            try {
                await ElementPlus.ElMessageBox.confirm(`确定删除账户「${acc}」的费率配置？交易记录不会删除。`, '确认删除', { type: 'warning' });
                feeAccounts.value = feeAccounts.value.filter(x => x !== acc);
                const nextSettings = { ...feeSettings.value };
                delete nextSettings[acc];
                feeSettings.value = nextSettings;
                activeFeeAccount.value = feeAccounts.value[0];
                transForm.value.account = activeFeeAccount.value;
                feeManuallyEdited.value = false;
                estimateFeeIfAuto();
                await saveFeeSettings();
            } catch (e) {}
        };

        const calculateEstimatedFee = (form = transForm.value) => {
            const direction = form.direction || '';
            if (direction === '分红' || direction === '分红再投资') return 0;
            const category = form.category || inferCategoryByCode(form.code, form.name) || '其他';
            const account = form.account || activeFeeAccount.value || feeAccounts.value[0] || '华泰证券';
            ensureFeeAccount(account);
            const rulePct = (feeSettings.value[account] || {})[category] || (feeSettings.value[account] || {})['其他'] || defaultFeeRulePct();
            const rule = pctRuleToRate(rulePct);
            const amount = Number(form.amount || 0);
            if (!amount || amount <= 0) return 0;
            const commissionRaw = amount * Number(rule.commission_rate || 0);
            const commission = commissionRaw > 0 ? Math.max(commissionRaw, Number(rule.min_commission || 0)) : 0;
            const stampTax = direction === '卖出' ? amount * Number(rule.stamp_tax_rate || 0) : 0;
            const transferFee = (category === 'A股权益' && (direction === '买入' || direction === '卖出')) ? amount * Number(rule.transfer_fee_rate || 0) : 0;
            return Math.round((commission + stampTax + transferFee) * 100) / 100;
        };

        const estimateFeeIfAuto = () => {
            const estimated = calculateEstimatedFee();
            const category = transForm.value.category || inferCategoryByCode(transForm.value.code, transForm.value.name) || '其他';
            const account = transForm.value.account || activeFeeAccount.value || '华泰证券';
            if (!feeManuallyEdited.value) transForm.value.fee = estimated;
            feeAutoHint.value = transForm.value.amount ? `当前按 ${account} / ${category} / ${transForm.value.direction} 估算：${formatMoney(estimated)}${feeManuallyEdited.value ? '（已手动覆盖，不自动改写）' : ''}` : '';
        };

        const markFeeManual = (val) => {
            const estimated = calculateEstimatedFee();
            if (Math.abs(Number(val || 0) - estimated) > 0.005) feeManuallyEdited.value = true;
        };

        const saveFeeSettings = async () => {
            try {
                const payload = {};
                feeAccounts.value.forEach(acc => {
                    ensureFeeAccount(acc);
                    payload[acc] = {};
                    feeCategories.forEach(cat => payload[acc][cat] = pctRuleToRate(feeSettings.value[acc][cat] || {}));
                });
                const res = await api.updateFeeSettings({ accounts: feeAccounts.value, active_account: activeFeeAccount.value, settings: payload });
                loadFeeSettingsToForm(res.data || { accounts: feeAccounts.value, active_account: activeFeeAccount.value, settings: payload });
                feeManuallyEdited.value = false;
                estimateFeeIfAuto();
                ElMessage.success('费率设置已保存');
            } catch (e) { ElMessage.error('费率保存失败'); }
        };

        const resetFeeSettings = async () => {
            try {
                const res = await api.resetFeeSettings();
                loadFeeSettingsToForm(res.data || {});
                feeManuallyEdited.value = false;
                estimateFeeIfAuto();
                ElMessage.success('已恢复默认费率');
            } catch (e) { ElMessage.error('恢复默认失败'); }
        };

        watch(() => [transForm.value.account, transForm.value.amount, transForm.value.direction, transForm.value.category, transForm.value.code, transForm.value.name], () => {
            estimateFeeIfAuto();
        });

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


        const downloadFile = async (url, filename) => {
            try {
                const res = await api.download(url);
                const blobUrl = window.URL.createObjectURL(new Blob([res.data], { type: 'text/csv;charset=utf-8;' }));
                const link = document.createElement('a');
                link.href = blobUrl;
                link.download = filename;
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                window.URL.revokeObjectURL(blobUrl);
            } catch (e) {
                ElMessage.error('下载失败：' + (e?.response?.data?.detail || e?.message || '未知错误'));
            }
        };

        const downloadTransactionsTemplate = () => downloadFile('/transactions/template', 'transactions_template.csv');
        const exportTransactions = () => downloadFile('/transactions/export', `transactions_${new Date().toISOString().slice(0,10)}.csv`);
        const downloadDepositsTemplate = () => downloadFile('/deposits/template', 'deposits_template.csv');
        const exportDeposits = () => downloadFile('/deposits/export', `deposits_${new Date().toISOString().slice(0,10)}.csv`);

        const uploadCsv = async (url, file, label, afterSuccess) => {
            const raw = file?.raw || file;
            if (!raw) return;
            if (!String(raw.name || '').toLowerCase().endsWith('.csv')) {
                return ElMessage.warning('请上传 CSV 文件');
            }
            try {
                await ElementPlus.ElMessageBox.confirm(`确认导入 ${raw.name}？导入前系统会自动备份数据库，成功行会写入真实数据。`, `导入${label}`, { type: 'warning' });
                const fd = new FormData();
                fd.append('file', raw);
                const res = await api.uploadCsv(url, fd);
                const data = res.data || {};
                const errorText = data.failed ? `，失败 ${data.failed} 行：${(data.errors || []).slice(0, 3).map(e => `第${e.row}行 ${e.error}`).join('；')}` : '';
                ElMessage.success(`${label}导入完成：成功 ${data.imported || 0} 行${errorText}`);
                if (afterSuccess) await afterSuccess();
            } catch (e) {
                if (e === 'cancel') return;
                const detail = e?.response?.data?.detail || e?.message || '未知错误';
                ElMessage.error(`${label}导入失败：${detail}`);
            }
        };

        const importTransactions = (file) => uploadCsv('/transactions/import', file, '交易记录', async () => { await queryTransactions(); await fetchData(); });
        const importDeposits = (file) => uploadCsv('/deposits/import', file, '银行存款', async () => { await fetchData(); });

        // 预计年化收益编辑
        const openExpectedReturnDialog = (row) => {
            expectedReturnDialog.value = {
                visible: true,
                form: {
                    code: row.code,
                    name: row.name,
                    expected_return: row.expected_return || 0
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
                    date: new Date().toISOString().split('T')[0],
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
                await ElementPlus.ElMessageBox.confirm(`确定删除 ${row.date} ${row.code} 的持仓校正？删除后会按交易记录重新计算。`, '确认删除', { type: 'warning' });
                await api.deleteHoldingCorrection(row.id);
                ElMessage.success('校正记录已删除，并已重新计算持仓');
                holdingCorrectionHistoryDialog.value.records = holdingCorrectionHistoryDialog.value.records.filter(x => x.id !== row.id);
                await fetchData();
            } catch (e) {}
        };

        // 监听交易管理标签页切换
        watch(activeTab, (val) => {
            if (val === 'transactions') {
                queryTransactions();
            }
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

        // 计算资产配置分析
        const calculateAllocationAnalysis = () => {
            const categories = {};
            const macroGroups = {
                '权益': { amount: 0, cost: 0, profit: 0, weighted_expected_return_sum: 0, total_weight: 0, details: new Set() },
                '固收': { amount: 0, cost: 0, profit: 0, weighted_expected_return_sum: 0, total_weight: 0, details: new Set() },
                '存款': { amount: 0, cost: 0, profit: 0, weighted_expected_return_sum: 0, total_weight: 0, details: new Set() }
            };
            let totalValue = 0;
            
            const defaultExpectedReturns = {
                'A股权益': 6.0,
                'A股ETF': 5.0,
                '港股ETF': 5.0,
                '债基': 2.5,
                'REITs': 4.5,
                '黄金': 4.0,
                '银行存款': 2.0,
                '证券现金': 0.0,
                '未分类': 3.0
            };

            const getMacroGroup = (cat) => {
                if (cat === '债基') return '固收';
                if (cat === '银行存款') return '存款';
                return '权益';
            };
            
            holdings.value.forEach(h => {
                const cat = h.category || '未分类';
                const value = h.quantity * h.last_price;
                const cost = h.quantity * h.avg_cost;
                const profit = value - cost + (h.total_dividend || 0);
                
                totalValue += value;
                
                if (!categories[cat]) {
                    categories[cat] = {
                        market_value: 0,
                        cost: 0,
                        profit: 0,
                        count: 0,
                        weighted_expected_return_sum: 0,
                        total_weight: 0
                    };
                }
                
                categories[cat].market_value += value;
                categories[cat].cost += cost;
                categories[cat].profit += profit;
                categories[cat].count += 1;
                
                const expectedReturn = h.expected_return || defaultExpectedReturns[cat] || defaultExpectedReturns['未分类'];
                categories[cat].weighted_expected_return_sum += expectedReturn * value;
                categories[cat].total_weight += value;

                const macro = macroGroups[getMacroGroup(cat)];
                macro.amount += value;
                macro.cost += cost;
                macro.profit += profit;
                macro.weighted_expected_return_sum += expectedReturn * value;
                macro.total_weight += value;
                macro.details.add(cat);
            });

            const addSyntheticCategory = (cat, value, expectedReturn, detailCount = 1) => {
                if (value <= 0) return;
                if (!categories[cat]) {
                    categories[cat] = { market_value: 0, cost: 0, profit: 0, count: 0, weighted_expected_return_sum: 0, total_weight: 0 };
                }
                categories[cat].market_value += value;
                categories[cat].cost += value;
                categories[cat].profit += 0;
                categories[cat].count += detailCount;
                categories[cat].weighted_expected_return_sum += expectedReturn * value;
                categories[cat].total_weight += value;
            };
            
            const bankBalance = Number(dashboard.value.bank_balance || 0);
            if (bankBalance > 0) {
                addSyntheticCategory('银行存款', bankBalance, defaultExpectedReturns['银行存款'], deposits.value.length || 1);
                macroGroups['存款'].amount += bankBalance;
                macroGroups['存款'].cost += bankBalance;
                macroGroups['存款'].weighted_expected_return_sum += defaultExpectedReturns['银行存款'] * bankBalance;
                macroGroups['存款'].total_weight += bankBalance;
                macroGroups['存款'].details.add('银行存款');
            }

            const securitiesCash = Number(dashboard.value.securities_cash || 0);
            if (securitiesCash > 0) {
                addSyntheticCategory('证券现金', securitiesCash, defaultExpectedReturns['证券现金'], 1);
                macroGroups['固收'].amount += securitiesCash;
                macroGroups['固收'].cost += securitiesCash;
                macroGroups['固收'].weighted_expected_return_sum += defaultExpectedReturns['证券现金'] * securitiesCash;
                macroGroups['固收'].total_weight += securitiesCash;
                macroGroups['固收'].details.add('证券现金');
            }

            const pendingPurchase = Number(dashboard.value.pending_purchase || 0);
            if (pendingPurchase > 0) {
                addSyntheticCategory('基金申购在途', pendingPurchase, defaultExpectedReturns['债基'], pendingTransactions.value.length || 1);
                macroGroups['固收'].amount += pendingPurchase;
                macroGroups['固收'].cost += pendingPurchase;
                macroGroups['固收'].weighted_expected_return_sum += defaultExpectedReturns['债基'] * pendingPurchase;
                macroGroups['固收'].total_weight += pendingPurchase;
                macroGroups['固收'].details.add('基金申购在途');
            }
            
            if (dashboard.value.total_assets) {
                totalValue = dashboard.value.total_assets;
            }
            
            allocationAnalysis.value = Object.keys(categories).map(cat => {
                const data = categories[cat];
                const expectedReturn = data.total_weight > 0
                    ? data.weighted_expected_return_sum / data.total_weight
                    : (defaultExpectedReturns[cat] || defaultExpectedReturns['未分类']);
                
                return {
                    category: cat,
                    market_value: data.market_value,
                    percentage: (data.market_value / totalValue) * 100,
                    profit: data.profit,
                    profit_rate: data.cost > 0 ? (data.profit / data.cost) * 100 : 0,
                    count: data.count,
                    expected_annual_return: expectedReturn
                };
            }).sort((a, b) => b.market_value - a.market_value);

            macroAllocationAnalysis.value = ['权益', '固收', '存款'].map(group => {
                const data = macroGroups[group];
                return {
                    group,
                    amount: data.amount,
                    percentage: totalValue > 0 ? (data.amount / totalValue) * 100 : 0,
                    profit: data.profit,
                    profit_rate: data.cost > 0 ? (data.profit / data.cost) * 100 : 0,
                    expected_return: data.total_weight > 0 ? data.weighted_expected_return_sum / data.total_weight : 0,
                    detail: Array.from(data.details).join('、') || '—'
                };
            });
            
            let weightedSum = 0;
            let totalWeight = 0;
            macroAllocationAnalysis.value.forEach(item => {
                weightedSum += item.expected_return * item.amount;
                totalWeight += item.amount;
            });
            portfolioExpectedReturn.value = totalWeight > 0 ? weightedSum / totalWeight : 0;
        };

        const renderAllocationCharts = () => renderAllocationChartsView(macroAllocationAnalysis.value, allocationAnalysis.value);


        // === 收益分析 ===
        const perfSummary = ref(null);
        const perfTimeline = ref([]);
        const perfContribution = ref([]);
        const perfFlows = ref([]);
        const perfLoading = ref(false);
        const perfContributionFilter = ref('all');
        const perfContributionSort = ref('contribution');
        const perfFlowForm = ref({
            date: new Date().toISOString().split('T')[0],
            flow_type: '投入',
            amount: 100000,
            source: '',
            remark: ''
        });

        const {
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
            if (val === 'allocation') nextTick(renderAllocationCharts);
            if (val === 'performance') fetchPerformance();
            if (val === 'snapshots') {
                fetchSnapshots().then(() => nextTick(renderSnapshotCharts));
            }
        });

        onMounted(() => {
            fetchData();
            queryTransactions();
            queryCashFlows();
            fetchSnapshots();
        });

        return {
            activeTab, dashboard, holdings, deposits, depositRows, depositSummary, depositBankBreakdown, depositMaturityBuckets, syncing, trailingSyncing, syncNotice,
            snapshots, snapshotRange, snapshotSummary, snapshotMetrics, snapshotChangeRows, snapshotInsights, snapshotLoading,
            transForm, feeSettings, feeAccounts, activeFeeAccount, newFeeAccountName, feeCategories, feeSettingRows, feeAutoHint, depositDialog, cashForm, cashFlows, cashFlowForm, cashFlowQuery, cashFlowSummary, cashFlowEditDialog, transDialog, allocationAnalysis, macroAllocationAnalysis,
            allocationSummary, allocationHealth, portfolioExpectedReturn, expectedReturnDialog, holdingCorrectionDialog, holdingCorrectionHistoryDialog,
            // 交易管理相关
            allTransactions, filteredTransactions, pendingTransactions, pendingPurchaseTotal, transQuery, transPage, transEditDialog,
            syncPrices, syncTrailingReturns, submitTrans, resetForm, fetchData, markFeeManual, saveFeeSettings, resetFeeSettings, addFeeAccount, removeFeeAccount, onActiveFeeAccountChange,
            downloadTransactionsTemplate, exportTransactions, importTransactions, downloadDepositsTemplate, exportDeposits, importDeposits,
            queryAssetByCode, queryAssetByName, selectTransAsset, autoMatchTransAsset,
            openDepositDialog, saveDeposit, deleteDeposit, updateCash, queryCashFlows, resetCashFlowQuery, addCashFlow, openCashFlowEditDialog, saveCashFlowEdit, deleteCashFlow, cashFlowTagType,
            createSnapshot, fetchSnapshots, exportSnapshots, compactSnapshots, showTransactions,
            queryTransactions, applyTransFilter, resetTransQuery, handleTransPageChange, handleTransPageSizeChange, goPendingTransactions, openTransEditDialog, saveTransactionEdit, deleteTransaction,
            openExpectedReturnDialog, saveExpectedReturn, openHoldingCorrectionDialog, saveHoldingCorrection, openHoldingCorrectionHistory, deleteHoldingCorrection, formatMoney, formatPercent, pct,
            perfSummary, perfTimeline, perfContribution, perfFlows, perfLoading, perfFlowForm, perfCards,
            displayedPerfContribution, perfContributionFilter, perfContributionSort, perfContributionHeadline, perfContributionMix,
            fetchPerformance, addPerfFlow, deletePerfFlow, contributionBarStyle
        };
    }
});
app.use(ElementPlus);
app.mount('#app');
