import api from '../api/index.js';
import { createAssetHelpers } from './assets.js';
import { ElMessage, ElMessageBox } from 'element-plus';
import { todayLocalIso, apiErrorDetail, formatMoney } from '../utils/index.js';

// 一句话记账（N1）草稿 → 表单字段。导出成纯函数便于单测：只做字段落位，
// 金额由「数量 × 单价」算（AI 不给金额）；日期只在原话明写时采用，否则补应用时区的"今天"
// —— 不能沿用表单里可能被改过的旧值，否则"昨天"会被记到上次填的日期上。
const applyEntryDraftFields = (form, draft) => {
    if (!form || !draft) return form;
    if (draft.code) form.code = String(draft.code);
    if (draft.name) form.name = String(draft.name);
    if (draft.direction) form.direction = String(draft.direction);
    form.date = draft.date ? String(draft.date).slice(0, 10) : todayLocalIso();
    const qty = Number(draft.quantity);
    if (Number.isFinite(qty) && qty > 0) form.quantity = qty;
    const price = Number(draft.price);
    if (Number.isFinite(price) && price > 0) form.price = price;
    const gross = Number(form.quantity || 0) * Number(form.price || 0);
    form.amount = Math.round(gross * 100) / 100;
    return form;
};

// 一句话记账：后端给的原因 → 人话。放在模块层（纯函数、可单测），视图只调用。
const NL_ENTRY_REASONS = {
    unknown_code: '原话里的标的不在持仓 / 关注 / 交易记录里。先手填一次，之后它就能被识别。',
    invalid_direction: '没听出买卖方向（只支持 买入 / 卖出 / 分红 / 分红再投资 / 申购待确认）。',
    direction_conflict: '买卖方向跟原话对不上，为避免记反请手动确认方向。',
    invalid_value: '数量或单价不合理，请手动填写。',
    untraceable_number: '数量或单价没能跟原话对上，为避免填错请手动输入。',
    unit_conflict: '数量和单价可能被搞混了，为避免记错请手动输入。',
    amount_mismatch: '数量×单价 与「花了…元」的总额对不上，请手动核对。',
    unparsable: '没能从这句话里读出交易，换个说法或手动填写。',
    timeout: 'AI 超时了，请重试或手动填写。',
    budget: '今天的 AI 调用额度用完了，请手动填写。',
    blocked: 'AI 暂时不可用，请手动填写。',
    not_configured: 'AI 还没配好（设置 → AI 的地址 / 密钥 / 模型），请手动填写。',
    assets_unavailable: '读持仓清单失败，暂时用不了，请手动填写。',
    empty_universe: '还没有持仓或交易记录，先手填第一笔吧。',
};

const nlEntryReasonText = (data) => {
    const mode = String((data && data.mode) || '');
    const reason = String((data && data.reason) || '');
    // mode=blocked 是兜底分类，它自己那句话最没用：先拿 reason 试一次，
    // 否则 assets_unavailable / payload_failed 这类具体原因永远显示不出来。
    const keys = mode === 'blocked' ? [reason, mode] : [mode, reason];
    for (const key of keys) {
        if (key && NL_ENTRY_REASONS[key]) return NL_ENTRY_REASONS[key];
    }
    return `没能解析成草稿（${reason || mode || '未知原因'}），请手动填写。`;
};

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
    // N1 一句话记账：把草稿填进录入表单。**不落库** —— 用户仍要点「提交记录」
    // 才走 POST /transactions，与「草稿确认后才入账」的既有立场一致。
    const applyEntryDraft = (draft) => {
        applyEntryDraftFields(transForm.value, draft);
        feeManuallyEdited.value = false;
        autoMatchTransAsset('code');
        // fee 不由模型猜：先按金额估一次，再按「买入 +费 / 卖出 −费」把总额对齐，
        // 否则提交前那条「数量×单价 vs 总额」反向校验会为几元手续费弹一次核对框。
        estimateFeeIfAuto();
        const fee = Number(transForm.value.fee || 0);
        const gross = Number(transForm.value.quantity || 0) * Number(transForm.value.price || 0);
        const dir = transForm.value.direction;
        if (gross > 0) {
            const withFee = (dir === '卖出' || dir === '分红') ? gross - fee : gross + fee;
            transForm.value.amount = Math.round(Math.max(withFee, 0) * 100) / 100;
            estimateFeeIfAuto();
        }
    };

    const parseNlEntry = async (utterance) => {
        const text = String(utterance || '').trim();
        if (!text) return { ok: false, mode: 'unparsable', reason: 'empty_utterance', draft: null, warnings: [], shadow: false };
        const res = await api.nlEntry(text);
        const data = res.data || {};
        // 影子模式与 A3 同语义：只记录、不生效 —— 草稿不填进表单。
        if (data.ok && data.draft && !data.shadow) applyEntryDraft(data.draft);
        return data;
    };

    return {
        submitTrans, resetForm, showTransactions, updatePendingTransactions, queryTransactions,
        applyTransFilter, resetTransQuery, handleTransPageChange, handleTransPageSizeChange,
        goPendingTransactions, openTransEditDialog, saveTransactionEdit, deleteTransaction,
        // asset query helpers now owned here
        queryAssetByCode, queryAssetByName, selectTransAsset, autoMatchTransAsset,
        applyEntryDraftFields, parseNlEntry,
    };
};

export { createTransactionsModule, nlEntryReasonText, applyEntryDraftFields };
export default createTransactionsModule;
