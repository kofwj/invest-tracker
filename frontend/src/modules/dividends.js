import { ElMessage, ElMessageBox } from 'element-plus';
import { api } from '../api/index.js';

/**
 * Dividend draft helpers (extracted from domainHelpers + main for better modularity).
 * Handles scanning market dividend drafts and confirming them as "分红" transactions.
 */
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
            const tips = [];
            if ((s.unsupported_holdings || 0) > 0) {
                tips.push(`有 ${s.unsupported_holdings} 只不支持自动扫（多为开放式债基），请使用分红模板手工补录`);
            }
            if ((data.failed || []).length) {
                tips.push(`${data.failed.length} 只扫描失败，可稍后再扫或手工录`);
            }
            ElMessage.success(
                `扫描完成：新草稿 ${s.new_count || 0}，已有流水 ${s.already_recorded_count || 0}，零持仓 ${s.zero_qty_count || 0}`
                + (tips.length ? `。${tips.join('；')}` : ''),
            );
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
