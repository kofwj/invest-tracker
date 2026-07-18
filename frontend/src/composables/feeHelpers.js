import { computed, watch } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import api from '../api/index.js';
import { formatMoney, inferCategoryByCode, apiErrorDetail } from '../utils/index.js';

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
        } catch (e) { ElMessage.error('费率保存失败：' + apiErrorDetail(e)); }
    };

    const resetFeeSettings = async () => {
        try {
            const res = await api.resetFeeSettings();
            loadFeeSettingsToForm(res.data || {});
            feeManuallyEdited.value = false;
            estimateFeeIfAuto();
            ElMessage.success('已恢复默认费率');
        } catch (e) { ElMessage.error('恢复默认失败：' + apiErrorDetail(e)); }
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
