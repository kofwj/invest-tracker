import { computed, ref, watch } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import api from '../api/index.js';
import { formatMoney, inferCategoryByCode } from '../utils/index.js';

export function createFeeHelpers({
    feeSettings,
    feeAccounts,
    activeFeeAccount,
    newFeeAccountName,
    feeCategories,
    feeManuallyEdited,
    feeAutoHint,
    transForm,
}) {
    const defaultFeeRulePct = () => ({
        commission_rate_pct: 0,
        stamp_tax_rate_pct: 0,
        transfer_fee_rate_pct: 0,
        min_commission: 0,
    });

    const defaultFeeRulesPct = () => {
        const defaults = {
            'A股权益': { commission_rate_pct: 0.025, stamp_tax_rate_pct: 0.05, transfer_fee_rate_pct: 0.001, min_commission: 0 },
            'A股ETF': { commission_rate_pct: 0.025, stamp_tax_rate_pct: 0, transfer_fee_rate_pct: 0, min_commission: 0 },
            '港股ETF': { commission_rate_pct: 0.025, stamp_tax_rate_pct: 0, transfer_fee_rate_pct: 0, min_commission: 0 },
            'REITs': { commission_rate_pct: 0.025, stamp_tax_rate_pct: 0, transfer_fee_rate_pct: 0, min_commission: 0 },
            '黄金': { commission_rate_pct: 0.025, stamp_tax_rate_pct: 0, transfer_fee_rate_pct: 0, min_commission: 0 },
            '债基': { commission_rate_pct: 0, stamp_tax_rate_pct: 0, transfer_fee_rate_pct: 0, min_commission: 0 },
            '其他': { commission_rate_pct: 0.025, stamp_tax_rate_pct: 0, transfer_fee_rate_pct: 0, min_commission: 0 },
        };
        feeCategories.forEach(cat => { defaults[cat] = { ...defaultFeeRulePct(), ...(defaults[cat] || {}) }; });
        return defaults;
    };

    const rateToPctRule = (rule = {}) => ({
        commission_rate_pct: Number(rule.commission_rate || 0) * 100,
        stamp_tax_rate_pct: Number(rule.stamp_tax_rate || 0) * 100,
        transfer_fee_rate_pct: Number(rule.transfer_fee_rate || 0) * 100,
        min_commission: Number(rule.min_commission || 0),
    });

    const pctRuleToRate = (rule = {}) => ({
        commission_rate: Number(rule.commission_rate_pct || 0) / 100,
        stamp_tax_rate: Number(rule.stamp_tax_rate_pct || 0) / 100,
        transfer_fee_rate: Number(rule.transfer_fee_rate_pct || 0) / 100,
        min_commission: Number(rule.min_commission || 0),
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
        if (data.settings && !data.accounts && feeCategories.some(cat => data.settings[cat])) {
            return { accounts: ['华泰证券'], active_account: '华泰证券', settings: { '华泰证券': data.settings } };
        }
        return data;
    };

    const loadFeeSettingsToForm = (data) => {
        const normalized = normalizeFeeApiData(data || {});
        const accounts = (normalized.accounts || Object.keys(normalized.settings || {}) || ['华泰证券']).filter(Boolean);
        feeAccounts.value = accounts.length ? [...new Set(accounts)] : ['华泰证券'];
        activeFeeAccount.value = normalized.active_account && feeAccounts.value.includes(normalized.active_account)
            ? normalized.active_account
            : feeAccounts.value[0];
        const next = {};
        feeAccounts.value.forEach(acc => {
            next[acc] = {};
            const rules = (normalized.settings || {})[acc] || {};
            feeCategories.forEach(cat => {
                next[acc][cat] = rateToPctRule(rules[cat] || pctRuleToRate(defaultFeeRulesPct()[cat]));
            });
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
            await ElMessageBox.confirm(`确定删除账户「${acc}」的费率配置？交易记录不会删除。`, '确认删除', { type: 'warning' });
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
        feeAutoHint.value = transForm.value.amount
            ? `当前按 ${account} / ${category} / ${transForm.value.direction} 估算：${formatMoney(estimated)}${feeManuallyEdited.value ? '（已手动覆盖，不自动改写）' : ''}`
            : '';
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
                feeCategories.forEach(cat => {
                    payload[acc][cat] = pctRuleToRate(feeSettings.value[acc][cat] || {});
                });
            });
            const res = await api.updateFeeSettings({
                accounts: feeAccounts.value,
                active_account: activeFeeAccount.value,
                settings: payload,
            });
            loadFeeSettingsToForm(res.data || {
                accounts: feeAccounts.value,
                active_account: activeFeeAccount.value,
                settings: payload,
            });
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

    watch(
        () => [
            transForm.value.account,
            transForm.value.amount,
            transForm.value.direction,
            transForm.value.category,
            transForm.value.code,
            transForm.value.name,
        ],
        () => { estimateFeeIfAuto(); },
    );

    return {
        feeSettingRows,
        loadFeeSettingsToForm,
        ensureFeeAccount,
        estimateFeeIfAuto,
        markFeeManual,
        saveFeeSettings,
        resetFeeSettings,
        addFeeAccount,
        removeFeeAccount,
        onActiveFeeAccountChange,
        calculateEstimatedFee,
    };
}

export function createDividendHelpers({
    dividendDialog,
    dividendTableRef,
    dividendLoading,
    dividendConfirming,
    activeFeeAccount,
    fetchData,
    queryTransactions,
}) {
    const openDividendDraftDialog = () => {
        dividendDialog.value.visible = true;
        if (!dividendDialog.value.drafts.length) {
            scanDividendDrafts();
        }
    };

    const dividendStatusLabel = (status) => ({
        new: '待确认',
        already_recorded: '已有流水',
        zero_qty: '零持仓',
        zero_amount: '零金额',
    }[status] || status || '未知');

    const dividendStatusType = (status) => ({
        new: 'success',
        already_recorded: 'info',
        zero_qty: 'warning',
        zero_amount: 'warning',
    }[status] || 'info');

    const isDividendDraftSelectable = (row) => !!row?.selectable && Number(row?.amount || 0) > 0;

    const onDividendSelectionChange = (rows) => {
        dividendDialog.value.selected = rows || [];
    };

    const selectSelectableDividendDrafts = () => {
        const table = dividendTableRef.value;
        if (!table) return;
        table.clearSelection();
        (dividendDialog.value.drafts || []).forEach((row) => {
            if (isDividendDraftSelectable(row)) table.toggleRowSelection(row, true);
        });
    };

    const clearDividendDraftSelection = () => {
        const table = dividendTableRef.value;
        if (table) table.clearSelection();
        dividendDialog.value.selected = [];
    };

    const scanDividendDrafts = async () => {
        dividendLoading.value = true;
        try {
            const res = await api.scanDividends({ lookback_days: dividendDialog.value.lookbackDays || 400 });
            const data = res.data || {};
            dividendDialog.value.drafts = data.drafts || [];
            dividendDialog.value.summary = data.summary || null;
            dividendDialog.value.unsupported = data.unsupported || [];
            dividendDialog.value.failed = data.failed || [];
            dividendDialog.value.selected = [];
            const s = data.summary || {};
            ElMessage.success(`扫描完成：新草稿 ${s.new_count || 0}，已有流水 ${s.already_recorded_count || 0}，零持仓 ${s.zero_qty_count || 0}`);
        } catch (e) {
            ElMessage.error('扫描分红失败：' + (e?.response?.data?.detail || e?.message || '未知错误'));
        } finally {
            dividendLoading.value = false;
        }
    };

    const confirmSelectedDividends = async () => {
        const selected = (dividendDialog.value.selected || []).filter(isDividendDraftSelectable);
        if (!selected.length) {
            return ElMessage.warning('请先勾选可确认的分红草稿');
        }
        try {
            await ElMessageBox.confirm(
                `确认将 ${selected.length} 条分红草稿写入交易流水？系统会再次去重，已存在相近分红不会重复入账。`,
                '确认分红入账',
                { type: 'warning' },
            );
        } catch (e) {
            return;
        }
        dividendConfirming.value = true;
        try {
            const payload = {
                backup: true,
                drafts: selected.map((d) => ({
                    code: d.code,
                    name: d.name,
                    category: d.category,
                    account: d.account || activeFeeAccount.value || '华泰证券',
                    event_date: d.event_date,
                    amount: Number(d.amount || 0),
                    fee: Number(d.fee || 0),
                    remark: d.remark,
                    plan_profile: d.plan_profile,
                    direction: '分红',
                    draft_key: d.draft_key,
                })),
            };
            const res = await api.confirmDividends(payload);
            const data = res.data || {};
            ElMessage.success(`入账完成：新建 ${data.created_count || 0}，跳过 ${data.skipped_count || 0}，失败 ${data.error_count || 0}`);
            await Promise.all([fetchData(), queryTransactions(), scanDividendDrafts()]);
        } catch (e) {
            if (e === 'cancel') return;
            ElMessage.error('确认分红失败：' + (e?.response?.data?.detail || e?.message || '未知错误'));
        } finally {
            dividendConfirming.value = false;
        }
    };

    return {
        openDividendDraftDialog,
        dividendStatusLabel,
        dividendStatusType,
        isDividendDraftSelectable,
        onDividendSelectionChange,
        selectSelectableDividendDrafts,
        clearDividendDraftSelection,
        scanDividendDrafts,
        confirmSelectedDividends,
    };
}

export function createMaintenanceHelpers({
    maintenanceStatus,
    backups,
    maintenanceLoading,
    fetchData,
    fetchSnapshots,
    queryTransactions,
    API,
}) {
    const fetchMaintenance = async () => {
        try {
            const [statusRes, backupsRes] = await Promise.all([api.maintenanceStatus(), api.listBackups()]);
            maintenanceStatus.value = statusRes.data || {};
            backups.value = backupsRes.data || [];
        } catch (e) {
            console.error('获取维护状态失败', e);
        }
    };

    const createDbBackup = async () => {
        maintenanceLoading.value = true;
        try {
            const res = await api.createBackup();
            ElMessage.success(`备份已创建：${res.data?.filename || ''}`);
            await fetchMaintenance();
        } catch (e) {
            ElMessage.error('创建备份失败：' + (e?.response?.data?.detail || e?.message || '未知错误'));
        } finally {
            maintenanceLoading.value = false;
        }
    };

    const downloadBackup = (row) => {
        if (!row?.filename) return;
        window.location.href = `${API}/maintenance/backups/${encodeURIComponent(row.filename)}/download`;
    };

    const restoreBackup = async (row) => {
        if (!row?.filename) return;
        try {
            await ElMessageBox.confirm(`确定恢复备份 ${row.filename}？系统会先自动备份当前数据库。`, '恢复数据库', { type: 'warning' });
            maintenanceLoading.value = true;
            const res = await api.restoreBackup(row.filename);
            ElMessage.success(`恢复完成，恢复前备份：${res.data?.pre_restore_backup || ''}`);
            await Promise.all([fetchData(), fetchSnapshots(), queryTransactions(), fetchMaintenance()]);
        } catch (e) {
            if (e === 'cancel') return;
            ElMessage.error('恢复备份失败：' + (e?.response?.data?.detail || e?.message || '未知错误'));
        } finally {
            maintenanceLoading.value = false;
        }
    };

    const deleteBackup = async (row) => {
        if (!row?.filename) return;
        try {
            await ElMessageBox.confirm(`确定删除备份 ${row.filename}？删除后无法从系统内恢复。`, '删除备份', { type: 'warning' });
            maintenanceLoading.value = true;
            await api.deleteBackup(row.filename);
            ElMessage.success(`备份已删除：${row.filename}`);
            await fetchMaintenance();
        } catch (e) {
            if (e === 'cancel') return;
            ElMessage.error('删除备份失败：' + (e?.response?.data?.detail || e?.message || '未知错误'));
        } finally {
            maintenanceLoading.value = false;
        }
    };

    const restoreUploadedBackup = async (file) => {
        const raw = file?.raw || file;
        if (!raw) return;
        try {
            await ElMessageBox.confirm(`确定上传并恢复备份 ${raw.name}？系统会先自动备份当前数据库。`, '上传备份并恢复', { type: 'warning' });
            maintenanceLoading.value = true;
            const fd = new FormData();
            fd.append('file', raw);
            const res = await api.restoreUploadedBackup(fd);
            ElMessage.success(`恢复完成，恢复前备份：${res.data?.pre_restore_backup || ''}`);
            await Promise.all([fetchData(), fetchSnapshots(), queryTransactions(), fetchMaintenance()]);
        } catch (e) {
            if (e === 'cancel') return;
            ElMessage.error('上传恢复失败：' + (e?.response?.data?.detail || e?.message || '未知错误'));
        } finally {
            maintenanceLoading.value = false;
        }
    };

    return {
        fetchMaintenance,
        createDbBackup,
        downloadBackup,
        restoreBackup,
        deleteBackup,
        restoreUploadedBackup,
    };
}

export function createImportExportHelpers({ todayLocalIso, queryTransactions, fetchData, transQuery }) {
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
    const buildTransactionExportParams = () => {
        const q = transQuery.value || {};
        const params = { code: q.code || '', name: q.name || '', direction: q.direction || '' };
        if (q.dateRange && q.dateRange.length === 2) {
            params.start_date = q.dateRange[0];
            params.end_date = q.dateRange[1];
        }
        return params;
    };

    const exportTransactions = async () => {
        try {
            const res = await api.exportTransactions(buildTransactionExportParams());
            const blobUrl = window.URL.createObjectURL(new Blob([res.data], { type: 'text/csv;charset=utf-8;' }));
            const link = document.createElement('a');
            link.href = blobUrl;
            link.download = `transactions_${todayLocalIso()}.csv`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            window.URL.revokeObjectURL(blobUrl);
        } catch (e) {
            ElMessage.error('导出交易失败：' + (e?.response?.data?.detail || e?.message || '未知错误'));
        }
    };

    const downloadDepositsTemplate = () => downloadFile('/deposits/template', 'deposits_template.csv');
    const exportDeposits = () => downloadFile('/deposits/export', `deposits_${todayLocalIso()}.csv`);

    const uploadCsv = async (url, file, label, afterSuccess) => {
        const raw = file?.raw || file;
        if (!raw) return;
        if (!String(raw.name || '').toLowerCase().endsWith('.csv')) {
            return ElMessage.warning('请上传 CSV 文件');
        }
        try {
            await ElMessageBox.confirm(`确认导入 ${raw.name}？导入前系统会自动备份数据库，成功行会写入真实数据。`, `导入${label}`, { type: 'warning' });
            const fd = new FormData();
            fd.append('file', raw);
            const res = await api.uploadCsv(url, fd);
            const data = res.data || {};
            const errorText = data.failed
                ? `，失败 ${data.failed} 行：${(data.errors || []).slice(0, 3).map(e => `第${e.row}行 ${e.error}`).join('；')}`
                : '';
            ElMessage.success(`${label}导入完成：成功 ${data.imported || 0} 行${errorText}`);
            if (afterSuccess) await afterSuccess();
        } catch (e) {
            if (e === 'cancel') return;
            const detail = e?.response?.data?.detail || e?.message || '未知错误';
            ElMessage.error(`${label}导入失败：${detail}`);
        }
    };

    const importTransactions = (file) => uploadCsv('/transactions/import', file, '交易记录', async () => {
        await queryTransactions();
        await fetchData();
    });
    const importDeposits = (file) => uploadCsv('/deposits/import', file, '银行存款', async () => {
        await fetchData();
    });

    return {
        downloadTransactionsTemplate,
        exportTransactions,
        importTransactions,
        downloadDepositsTemplate,
        exportDeposits,
        importDeposits,
    };
}

export function createAllocationAnalysis({
    holdings,
    deposits,
    dashboard,
    pendingTransactions,
    allocationAnalysis,
    macroAllocationAnalysis,
    portfolioExpectedReturn,
}) {
    const calculateAllocationAnalysis = () => {
        const categories = {};
        const macroGroups = {
            '权益': { amount: 0, cost: 0, profit: 0, lifetime_profit: 0, weighted_expected_return_sum: 0, total_weight: 0, details: new Set() },
            '固收': { amount: 0, cost: 0, profit: 0, lifetime_profit: 0, weighted_expected_return_sum: 0, total_weight: 0, details: new Set() },
            '存款': { amount: 0, cost: 0, profit: 0, lifetime_profit: 0, weighted_expected_return_sum: 0, total_weight: 0, details: new Set() },
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
            '未分类': 3.0,
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
            const diluted = (h.diluted_cost != null && h.diluted_cost !== '') ? Number(h.diluted_cost) : Number(h.avg_cost || 0);
            const lifetime = (Number(h.last_price || 0) - diluted) * Number(h.quantity || 0);

            totalValue += value;

            if (!categories[cat]) {
                categories[cat] = {
                    market_value: 0,
                    cost: 0,
                    profit: 0,
                    lifetime_profit: 0,
                    count: 0,
                    weighted_expected_return_sum: 0,
                    total_weight: 0,
                };
            }

            categories[cat].market_value += value;
            categories[cat].cost += cost;
            categories[cat].profit += profit;
            categories[cat].lifetime_profit += lifetime;
            categories[cat].count += 1;

            const expectedReturn = (h.expected_return != null && h.expected_return !== '')
                ? Number(h.expected_return)
                : (defaultExpectedReturns[cat] || defaultExpectedReturns['未分类']);
            categories[cat].weighted_expected_return_sum += expectedReturn * value;
            categories[cat].total_weight += value;

            const macro = macroGroups[getMacroGroup(cat)];
            macro.amount += value;
            macro.cost += cost;
            macro.profit += profit;
            macro.lifetime_profit += lifetime;
            macro.weighted_expected_return_sum += expectedReturn * value;
            macro.total_weight += value;
            macro.details.add(cat);
        });

        const addSyntheticCategory = (cat, value, expectedReturn, detailCount = 1) => {
            if (value <= 0) return;
            if (!categories[cat]) {
                categories[cat] = { market_value: 0, cost: 0, profit: 0, lifetime_profit: 0, count: 0, weighted_expected_return_sum: 0, total_weight: 0 };
            }
            categories[cat].market_value += value;
            categories[cat].cost += value;
            categories[cat].profit += 0;
            categories[cat].lifetime_profit = (categories[cat].lifetime_profit || 0) + 0;
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
                lifetime_profit: data.lifetime_profit || 0,
                profit_rate: data.cost > 0 ? (data.profit / data.cost) * 100 : 0,
                count: data.count,
                expected_annual_return: expectedReturn,
            };
        }).sort((a, b) => b.market_value - a.market_value);

        macroAllocationAnalysis.value = ['权益', '固收', '存款'].map(group => {
            const data = macroGroups[group];
            return {
                group,
                amount: data.amount,
                percentage: totalValue > 0 ? (data.amount / totalValue) * 100 : 0,
                profit: data.profit,
                lifetime_profit: data.lifetime_profit || 0,
                profit_rate: data.cost > 0 ? (data.profit / data.cost) * 100 : 0,
                expected_return: data.total_weight > 0 ? data.weighted_expected_return_sum / data.total_weight : 0,
                detail: Array.from(data.details).join('、') || '—',
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

    return { calculateAllocationAnalysis };
}
