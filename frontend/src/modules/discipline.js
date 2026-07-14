import api from '../api/index.js';
import { ElMessage, ElMessageBox } from 'element-plus';

const createDisciplineModule = ({
    disciplineReport,
    disciplineDrafts,
    disciplinePolicy,
    disciplineLoading,
    disciplineDraftLoading,
    disciplinePolicyDialog,
    computed,
}) => {
    const fetchDisciplineReport = async () => {
        disciplineLoading.value = true;
        try {
            const res = await api.getDisciplineReport();
            disciplineReport.value = res.data || {};
            if (res.data?.policy) disciplinePolicy.value = { ...(res.data.policy || {}) };
        } catch (e) {
            ElMessage.error(e?.response?.data?.detail || '加载纪律报告失败');
        } finally {
            disciplineLoading.value = false;
        }
    };

    const fetchDisciplineDrafts = async () => {
        disciplineDraftLoading.value = true;
        try {
            const res = await api.listDisciplineDrafts({ status: 'draft' });
            disciplineDrafts.value = res.data || [];
        } catch (e) {
            ElMessage.error(e?.response?.data?.detail || '加载草稿失败');
        } finally {
            disciplineDraftLoading.value = false;
        }
    };

    const refreshDiscipline = async () => {
        await Promise.all([fetchDisciplineReport(), fetchDisciplineDrafts()]);
    };

    const openPolicyDialog = async () => {
        try {
            const res = await api.getDisciplinePolicy();
            disciplinePolicy.value = res.data || {};
        } catch (_) {
            /* keep existing */
        }
        disciplinePolicyDialog.value = true;
    };

    const savePolicy = async () => {
        try {
            const p = disciplinePolicy.value || {};
            const payload = {
                equity_min_pct: Number(p.equity_min_pct),
                equity_max_pct: Number(p.equity_max_pct),
                defensive_min_pct: Number(p.defensive_min_pct),
                single_holding_max_pct: Number(p.single_holding_max_pct),
                rebalance_band_pct: Number(p.rebalance_band_pct),
                preferred_buy_code: String(p.preferred_buy_code || '').trim(),
                preferred_buy_name: String(p.preferred_buy_name || '').trim(),
                preferred_buy_category: String(p.preferred_buy_category || '').trim(),
                preferred_buy_account: String(p.preferred_buy_account || '').trim(),
                targets: {
                    equity_pct: Number(p.targets?.equity_pct),
                    fixed_income_pct: Number(p.targets?.fixed_income_pct),
                    deposit_pct: Number(p.targets?.deposit_pct),
                },
                named_limits: Array.isArray(p.named_limits) ? p.named_limits : undefined,
                no_new_codes: Array.isArray(p.no_new_codes) ? p.no_new_codes : undefined,
            };
            await api.saveDisciplinePolicy(payload);
            ElMessage.success('纪律参数已保存');
            disciplinePolicyDialog.value = false;
            await refreshDiscipline();
        } catch (e) {
            ElMessage.error(e?.response?.data?.detail || '保存失败');
        }
    };

    const createDraftsFromReport = async () => {
        try {
            const actions = disciplineReport.value?.actions || [];
            if (!actions.length) {
                ElMessage.info('当前没有可生成的建议');
                return;
            }
            await ElMessageBox.confirm(
                `将把 ${actions.length} 条建议写入「纪律草稿」（不会立刻改真账）。确认？`,
                '生成草稿',
                { type: 'info' },
            );
            const res = await api.createDisciplineDrafts({});
            ElMessage.success(`已生成 ${res.data?.count || 0} 条草稿`);
            await fetchDisciplineDrafts();
            await fetchDisciplineReport();
        } catch (e) {
            if (e === 'cancel' || e === 'close') return;
            ElMessage.error(e?.response?.data?.detail || '生成草稿失败');
        }
    };

    const deleteDraft = async (row) => {
        try {
            await ElMessageBox.confirm(`删除草稿 ${row.name || row.code}？`, '确认', { type: 'warning' });
            await api.deleteDisciplineDraft(row.id);
            ElMessage.success('已删除');
            await fetchDisciplineDrafts();
        } catch (e) {
            if (e === 'cancel' || e === 'close') return;
            ElMessage.error(e?.response?.data?.detail || '删除失败');
        }
    };

    const confirmDraft = async (row) => {
        try {
            await ElMessageBox.confirm(
                `确认后会写入真实交易记录（${row.side === 'sell' ? '卖出' : '买入/申购待确认'} ${row.name || row.code} 约 ${row.amount} 元）。确定？`,
                '确认入账',
                { type: 'warning' },
            );
            await api.confirmDisciplineDraft(row.id);
            ElMessage.success('已写入真实交易');
            await refreshDiscipline();
        } catch (e) {
            if (e === 'cancel' || e === 'close') return;
            ElMessage.error(e?.response?.data?.detail || '确认失败');
        }
    };

    const breaches = computed(() => disciplineReport.value?.breaches || []);
    const actions = computed(() => disciplineReport.value?.actions || []);
    const snapshot = computed(() => disciplineReport.value?.snapshot || {});
    const targets = computed(() => disciplineReport.value?.targets || {});
    const summaryText = computed(() => disciplineReport.value?.summary || '');

    return {
        fetchDisciplineReport,
        fetchDisciplineDrafts,
        refreshDiscipline,
        openPolicyDialog,
        savePolicy,
        createDraftsFromReport,
        deleteDraft,
        confirmDraft,
        breaches,
        actions,
        snapshot,
        targets,
        summaryText,
    };
};

export { createDisciplineModule };
export default createDisciplineModule;
