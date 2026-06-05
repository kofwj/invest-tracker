const createTransactionsModule = ({
    activeTab,
    allTransactions,
    filteredTransactions,
    pendingTransactions,
    pendingPurchaseTotal,
    transDialog,
    transEditDialog,
    transForm,
    transQuery,
    activeFeeAccount,
    feeAccounts,
    feeManuallyEdited,
    feeAutoHint,
    autoMatchTransAsset,
    estimateFeeIfAuto,
    fetchData,
}) => {
    const resetForm = () => {
        transForm.value = {
            date: new Date().toISOString().split('T')[0],
            code: '', name: '', category: '', account: activeFeeAccount.value || feeAccounts.value[0] || '华泰证券', direction: '买入',
            quantity: 0, price: 0, amount: 0, fee: 0,
        };
        feeManuallyEdited.value = false;
        feeAutoHint.value = '';
    };

    const submitTrans = async () => {
        autoMatchTransAsset(transForm.value.code ? 'code' : 'name');
        estimateFeeIfAuto();
        try {
            const payload = { ...transForm.value };
            await api.addTransaction(payload);
            ElementPlus.ElMessage.success('录入成功');
            await fetchData();
            resetForm();
        } catch (e) { ElementPlus.ElMessage.error('录入失败'); }
    };

    const showTransactions = async (row) => {
        try {
            const res = await api.listTransactionsByCode(row.code);
            transDialog.value = { visible: true, title: `${row.name} (${row.code}) 交易记录`, transactions: res.data };
        } catch (e) { ElementPlus.ElMessage.error('获取交易记录失败'); }
    };

    const updatePendingTransactions = () => {
        pendingTransactions.value = allTransactions.value.filter(t => t.direction === '申购待确认' || t.direction === '待确认申购');
        pendingPurchaseTotal.value = pendingTransactions.value.reduce((sum, t) => sum + Number(t.amount || 0) + Number(t.fee || 0), 0);
    };

    const applyTransFilter = () => {
        let result = [...allTransactions.value];
        const q = transQuery.value;
        if (q.dateRange && q.dateRange.length === 2) result = result.filter(t => t.date >= q.dateRange[0] && t.date <= q.dateRange[1]);
        if (q.code) result = result.filter(t => t.code.includes(q.code));
        if (q.name) result = result.filter(t => t.name.includes(q.name));
        if (q.direction) result = result.filter(t => t.direction === q.direction);
        filteredTransactions.value = result;
    };

    const queryTransactions = async () => {
        try {
            const res = await api.listTransactions();
            allTransactions.value = res.data;
            updatePendingTransactions();
            applyTransFilter();
        } catch (e) { ElementPlus.ElMessage.error('获取交易记录失败'); }
    };

    const resetTransQuery = () => {
        transQuery.value = { dateRange: [], code: '', name: '', direction: '' };
        filteredTransactions.value = [...allTransactions.value];
    };

    const goPendingTransactions = async () => {
        activeTab.value = 'transactions';
        transQuery.value.direction = '申购待确认';
        await queryTransactions();
    };

    const openTransEditDialog = (row) => {
        transEditDialog.value = {
            visible: true,
            editId: row.id,
            form: {
                date: row.date,
                code: row.code,
                name: row.name,
                category: row.category || '',
                account: row.account || activeFeeAccount.value || feeAccounts.value[0] || '华泰证券',
                direction: row.direction,
                quantity: row.quantity,
                price: row.price,
                amount: row.amount,
                fee: row.fee || 0,
                remark: row.remark || '',
            },
        };
    };

    const saveTransactionEdit = async () => {
        try {
            await api.updateTransaction(transEditDialog.value.editId, transEditDialog.value.form);
            ElementPlus.ElMessage.success('更新成功');
            transEditDialog.value.visible = false;
            await queryTransactions();
            await fetchData();
        } catch (e) { ElementPlus.ElMessage.error('更新失败'); }
    };

    const deleteTransaction = async (row) => {
        try {
            await ElementPlus.ElMessageBox.confirm(`确定删除 ${row.date} ${row.name} ${row.direction} ${row.quantity}股的记录？`, '确认删除', { type: 'warning' });
            await api.deleteTransaction(row.id);
            ElementPlus.ElMessage.success('已删除');
            await queryTransactions();
            await fetchData();
        } catch (e) { /* 用户取消 */ }
    };

    return { submitTrans, resetForm, showTransactions, updatePendingTransactions, queryTransactions, applyTransFilter, resetTransQuery, goPendingTransactions, openTransEditDialog, saveTransactionEdit, deleteTransaction };
};

window.createTransactionsModule = createTransactionsModule;
