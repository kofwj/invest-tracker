import api from '../api/index.js';
import { ElMessage, ElMessageBox } from 'element-plus';

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
    transPage,
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
            ElMessage.success('录入成功');
            await fetchData();
            resetForm();
        } catch (e) { ElMessage.error('录入失败'); }
    };

    const showTransactions = async (row) => {
        try {
            const res = await api.listTransactionsByCode(row.code);
            transDialog.value = { visible: true, title: `${row.name} (${row.code}) 交易记录`, transactions: res.data };
        } catch (e) { ElMessage.error('获取交易记录失败'); }
    };

    const updatePendingTransactions = () => {
        pendingTransactions.value = allTransactions.value.filter(t => t.direction === '申购待确认' || t.direction === '待确认申购');
        pendingPurchaseTotal.value = pendingTransactions.value.reduce((sum, t) => sum + Number(t.amount || 0) + Number(t.fee || 0), 0);
    };

    const buildTransQueryParams = () => {
        const q = transQuery.value || {};
        const params = {
            page: transPage.value.page,
            page_size: transPage.value.pageSize,
            code: q.code || '',
            name: q.name || '',
            direction: q.direction || '',
        };
        if (q.dateRange && q.dateRange.length === 2) {
            params.start_date = q.dateRange[0];
            params.end_date = q.dateRange[1];
        }
        return params;
    };

    const applyTransFilter = async () => {
        transPage.value.page = 1;
        await queryTransactions();
    };

    const queryTransactions = async () => {
        try {
            const res = await api.listTransactions(buildTransQueryParams());
            const data = res.data || {};
            const items = Array.isArray(data) ? data : (data.items || []);
            allTransactions.value = items;
            filteredTransactions.value = items;
            transPage.value.total = Array.isArray(data) ? items.length : Number(data.total || 0);
            updatePendingTransactions();
        } catch (e) { ElMessage.error('获取交易记录失败'); }
    };

    const resetTransQuery = async () => {
        transQuery.value = { dateRange: [], code: '', name: '', direction: '' };
        transPage.value.page = 1;
        await queryTransactions();
    };

    const handleTransPageChange = async (page) => {
        transPage.value.page = page;
        await queryTransactions();
    };

    const handleTransPageSizeChange = async (size) => {
        transPage.value.pageSize = size;
        transPage.value.page = 1;
        await queryTransactions();
    };

    const goPendingTransactions = async () => {
        activeTab.value = 'transactions';
        // backend treats 申购待确认 / 待确认申购 / pending as the same pending set
        transQuery.value.direction = 'pending';
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
            ElMessage.success('更新成功');
            transEditDialog.value.visible = false;
            await queryTransactions();
            await fetchData();
        } catch (e) { ElMessage.error('更新失败'); }
    };

    const deleteTransaction = async (row) => {
        try {
            await ElMessageBox.confirm(`确定删除 ${row.date} ${row.name} ${row.direction} ${row.quantity}股的记录？`, '确认删除', { type: 'warning' });
            await api.deleteTransaction(row.id);
            ElMessage.success('已删除');
            await queryTransactions();
            await fetchData();
        } catch (e) { /* 用户取消 */ }
    };

    return { submitTrans, resetForm, showTransactions, updatePendingTransactions, queryTransactions, applyTransFilter, resetTransQuery, handleTransPageChange, handleTransPageSizeChange, goPendingTransactions, openTransEditDialog, saveTransactionEdit, deleteTransaction };
};

export { createTransactionsModule };
export default createTransactionsModule;
