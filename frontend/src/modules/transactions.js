import api from '../api/index.js';
import { createAssetHelpers } from './assets.js';
import { ElMessage, ElMessageBox } from 'element-plus';
import { todayLocalIso, apiErrorDetail, formatMoney } from '../utils/index.js';

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
    holdings,
    estimateFeeIfAuto,
    fetchData,
}) => {
    let transSubmitting = false;
    // Asset query helpers (queryAssetBy*, selectTransAsset, autoMatchTransAsset)
    // merged into transactions module for form autocomplete ownership
    const {
        queryAssetByCode,
        queryAssetByName,
        selectTransAsset,
        autoMatchTransAsset,
    } = createAssetHelpers({ holdings, transForm });

    const resetForm = () => {
        transForm.value = {
            date: todayLocalIso(),
            code: '', name: '', category: '', account: activeFeeAccount.value || feeAccounts.value[0] || '华泰证券', direction: '买入',
            quantity: 0, price: 0, amount: 0, fee: 0,
        };
        feeManuallyEdited.value = false;
        feeAutoHint.value = '';
    };

    const submitTrans = async () => {
        if (transSubmitting) return;
        autoMatchTransAsset(transForm.value.code ? 'code' : 'name');
        estimateFeeIfAuto();
        transSubmitting = true;
        try {
            const payload = { ...transForm.value };

            // ---- 反向校验：数量×单价 vs 总金额 ----
            const { quantity, price, amount, fee, direction } = payload;
            const q = Number(quantity || 0);
            const p = Number(price || 0);
            const a = Number(amount || 0);
            const f = Number(fee || 0);
            let crossWarn = null;
            if (direction !== '申购待确认' && q > 0 && p > 0) {
                const gross = q * p;
                // 买入/分红再投资：总额≈数量×单价+费；卖出：≈数量×单价-费
                const expected = (direction === '卖出' || direction === '分红') ? gross - f : gross + f;
                const tol = Math.max(0.5, gross * 0.002);
                if (Math.abs(a - expected) > tol) {
                    const sensible = direction === '卖出' || direction === '分红' ? gross - f : gross + f;
                    crossWarn = `「数量×单价${(direction === '卖出' || direction === '分红') ? '−' : '+'}手续费」≈ ${formatMoney(sensible)}，与填写的总额 ${formatMoney(a)} 差 ${formatMoney(Math.abs(a - sensible), 2, true)}。可能是总金额或单价填错，请核对。`;
                }
            }

            // ---- 关键交易二次确认：大额 / 大比例卖出 ----
            let criticalWarn = null;
            const sellRatio = Number(holdings.value?.find(h => String(h.code).replace(/^f/i, '') === String(payload.code || '').replace(/^f/i, ''))?.quantity || 0);
            if (direction === '卖出' && q > 0) {
                const bigAmount = a >= 50000;
                const bigPct = sellRatio > 0 && (q / sellRatio) >= 0.5;
                if (bigAmount || bigPct) {
                    const heldPct = sellRatio > 0 ? `（占当前持仓 ${((q / sellRatio) * 100).toFixed(0)}%）` : '';
                    criticalWarn = `这是笔关键卖出：金额 ${formatMoney(a)}${heldPct}。确认无误？`;
                }
            }

            if (crossWarn || criticalWarn) {
                const lines = [crossWarn, criticalWarn].filter(Boolean).join('\n\n');
                try {
                    await ElMessageBox.confirm(lines, '提交前核对', {
                        type: 'warning',
                        confirmButtonText: '确认无误，提交',
                        cancelButtonText: '返回修改',
                        confirmButtonClass: 'el-button--danger',
                        title: '提交前核对',
                        message: lines,
                    });
                } catch (boxErr) {
                    transSubmitting = false;
                    return; // 用户返回修改
                }
            }

            await api.addTransaction(payload);
            ElMessage.success('录入成功');
            resetForm();
            try {
                await fetchData();
            } catch (refreshError) {
                ElMessage.warning('交易已入账，但页面刷新失败：' + apiErrorDetail(refreshError));
            }
        } catch (e) {
            ElMessage.error('录入失败：' + apiErrorDetail(e));
        } finally {
            transSubmitting = false;
        }
    };

    const showTransactions = async (row) => {
        try {
            const res = await api.listTransactionsByCode(row.code);
            transDialog.value = { visible: true, title: `${row.name} (${row.code}) 交易记录`, transactions: res.data };
        } catch (e) { ElMessage.error('获取交易记录失败：' + apiErrorDetail(e)); }
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
        } catch (e) { ElMessage.error('获取交易记录失败：' + apiErrorDetail(e)); }
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
        } catch (e) { ElMessage.error('更新失败：' + apiErrorDetail(e)); }
    };

    const deleteTransaction = async (row) => {
        try {
            await ElMessageBox.confirm(`确定删除 ${row.date} ${row.name} ${row.direction} ${row.quantity}股的记录？`, '确认删除', { type: 'warning' });
            await api.deleteTransaction(row.id);
            ElMessage.success('已删除');
            await queryTransactions();
            await fetchData();
        } catch (e) {
            if (e === 'cancel' || e === 'close') return;
            ElMessage.error('删除失败：' + apiErrorDetail(e));
        }
    };

    return {
        submitTrans, resetForm, showTransactions, updatePendingTransactions, queryTransactions,
        applyTransFilter, resetTransQuery, handleTransPageChange, handleTransPageSizeChange,
        goPendingTransactions, openTransEditDialog, saveTransactionEdit, deleteTransaction,
        // asset query helpers now owned here
        queryAssetByCode, queryAssetByName, selectTransAsset, autoMatchTransAsset,
    };
};

export { createTransactionsModule };
export default createTransactionsModule;
