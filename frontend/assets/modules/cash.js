const createCashModule = ({ dashboard, cashForm, cashFlows, cashFlowForm, cashFlowQuery, cashFlowEditDialog, activeFeeAccount, fetchData, computed }) => {
    const queryCashFlows = async () => {
        try {
            const params = [];
            const q = cashFlowQuery.value;
            if (q.dateRange && q.dateRange.length === 2) {
                params.push(`start_date=${q.dateRange[0]}`);
                params.push(`end_date=${q.dateRange[1]}`);
            }
            if (q.account) params.push(`account=${encodeURIComponent(q.account)}`);
            if (q.flow_type) params.push(`flow_type=${encodeURIComponent(q.flow_type)}`);
            const res = await api.listCashFlows(params);
            cashFlows.value = res.data || [];
        } catch (e) { ElementPlus.ElMessage.error('获取资金流水失败'); }
    };

    const updateCash = async () => {
        try {
            const before = Number(dashboard.value.securities_cash || 0);
            const after = Number(cashForm.value.amount || 0);
            await api.updateSecuritiesCash(after);
            ElementPlus.ElMessage.success(`证券现金已校准，差额 ${formatMoney(after - before, 2, true)} 已写入资金流水`);
            await fetchData();
            await queryCashFlows();
        } catch (e) { ElementPlus.ElMessage.error('更新失败'); }
    };

    const resetCashFlowQuery = async () => {
        cashFlowQuery.value = { dateRange: [], account: '', flow_type: '' };
        await queryCashFlows();
    };

    const cashFlowSummary = computed(() => {
        const inflow = cashFlows.value.filter(x => Number(x.amount || 0) > 0).reduce((s, x) => s + Number(x.amount || 0), 0);
        const outflow = cashFlows.value.filter(x => Number(x.amount || 0) < 0).reduce((s, x) => s + Number(x.amount || 0), 0);
        return { inflow, outflow, outflowAbs: Math.abs(outflow), net: inflow + outflow };
    });

    const cashFlowTagType = (type) => {
        if (type === '银证转入') return 'success';
        if (type === '银证转出') return 'warning';
        if (type === '现金校准') return 'info';
        return '';
    };

    const addCashFlow = async () => {
        try {
            if (!cashFlowForm.value.date) return ElementPlus.ElMessage.warning('请选择日期');
            if (!cashFlowForm.value.amount) return ElementPlus.ElMessage.warning('请输入金额');
            await api.addCashFlow(cashFlowForm.value);
            ElementPlus.ElMessage.success('资金流水已新增');
            cashFlowForm.value = { date: new Date().toISOString().split('T')[0], account: cashFlowForm.value.account || activeFeeAccount.value || '华泰证券', flow_type: '银证转入', amount: 0, remark: '' };
            await fetchData();
            await queryCashFlows();
        } catch (e) { ElementPlus.ElMessage.error('新增资金流水失败'); }
    };

    const openCashFlowEditDialog = (row) => {
        cashFlowEditDialog.value = { visible: true, editId: row.id, form: { date: row.date, account: row.account || '华泰证券', flow_type: row.flow_type, amount: row.amount, remark: row.remark || '' } };
    };

    const saveCashFlowEdit = async () => {
        try {
            await api.updateCashFlow(cashFlowEditDialog.value.editId, cashFlowEditDialog.value.form);
            ElementPlus.ElMessage.success('资金流水已更新');
            cashFlowEditDialog.value.visible = false;
            await fetchData();
            await queryCashFlows();
        } catch (e) { ElementPlus.ElMessage.error('更新资金流水失败'); }
    };

    const deleteCashFlow = async (row) => {
        try {
            await ElementPlus.ElMessageBox.confirm(`确定删除 ${row.date} ${row.flow_type} ${formatMoney(row.amount, 2, true)}？`, '确认删除', { type: 'warning' });
            await api.deleteCashFlow(row.id);
            ElementPlus.ElMessage.success('资金流水已删除');
            await fetchData();
            await queryCashFlows();
        } catch (e) {}
    };

    return { updateCash, queryCashFlows, resetCashFlowQuery, cashFlowSummary, cashFlowTagType, addCashFlow, openCashFlowEditDialog, saveCashFlowEdit, deleteCashFlow };
};
