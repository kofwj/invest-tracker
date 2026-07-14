import api from '../api/index.js';
import { ElMessage, ElMessageBox } from 'element-plus';

const numOr = (v, fallback) => {
    const n = Number(v);
    return Number.isFinite(n) ? n : fallback;
};

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
            if (res.data?.policy) {
                const p = res.data.policy || {};
                if (!p.targets) p.targets = { equity_pct: 45, fixed_income_pct: 30, deposit_pct: 25 };
                disciplinePolicy.value = { ...(disciplinePolicy.value || {}), ...p, targets: { ...(disciplinePolicy.value?.targets || {}), ...(p.targets || {}) } };
            }
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
            const p = res.data || {};
            if (!p.targets) p.targets = { equity_pct: 45, fixed_income_pct: 30, deposit_pct: 25 };
            disciplinePolicy.value = p;
        } catch (_) {
            /* keep existing */
        }
        if (disciplinePolicy.value && !disciplinePolicy.value.targets) {
            disciplinePolicy.value.targets = { equity_pct: 45, fixed_income_pct: 30, deposit_pct: 25 };
        }
        disciplinePolicyDialog.value = true;
    };

    const savePolicy = async () => {
        try {
            const p = disciplinePolicy.value || {};
            const equity_min_pct = numOr(p.equity_min_pct, 35);
            const equity_max_pct = numOr(p.equity_max_pct, 55);
            const defensive_min_pct = numOr(p.defensive_min_pct, 40);
            const single_holding_max_pct = numOr(p.single_holding_max_pct, 20);
            const rebalance_band_pct = numOr(p.rebalance_band_pct, 3);
            const targets = {
                equity_pct: numOr(p.targets?.equity_pct, 45),
                fixed_income_pct: numOr(p.targets?.fixed_income_pct, 30),
                deposit_pct: numOr(p.targets?.deposit_pct, 25),
            };
            if (equity_min_pct > equity_max_pct) {
                ElMessage.error('权益下限不能高于上限');
                return;
            }
            const tSum = targets.equity_pct + targets.fixed_income_pct + targets.deposit_pct;
            if (Math.abs(tSum - 100) > 0.5) {
                ElMessage.error(`目标三项合计应约 100%（当前 ${tSum.toFixed(1)}%）`);
                return;
            }
            const preferred_buy_code = String(p.preferred_buy_code || '').trim();
            if (!preferred_buy_code) {
                ElMessage.error('优先加仓代码不能为空');
                return;
            }
            const payload = {
                equity_min_pct,
                equity_max_pct,
                defensive_min_pct,
                single_holding_max_pct,
                rebalance_band_pct,
                preferred_buy_code,
                preferred_buy_name: String(p.preferred_buy_name || '').trim(),
                preferred_buy_category: String(p.preferred_buy_category || '').trim(),
                preferred_buy_account: String(p.preferred_buy_account || '').trim(),
                targets,
                named_limits: Array.isArray(p.named_limits) ? p.named_limits : undefined,
                no_new_codes: Array.isArray(p.no_new_codes) ? p.no_new_codes : undefined,
                fixed_income_categories: Array.isArray(p.fixed_income_categories) ? p.fixed_income_categories : undefined,
                defensive_extra_categories: Array.isArray(p.defensive_extra_categories)
                    ? p.defensive_extra_categories
                    : undefined,
            };
            await api.saveDisciplinePolicy(payload);
            ElMessage.success('纪律参数已保存');
            disciplinePolicyDialog.value = false;
            await refreshDiscipline();
        } catch (e) {
            const detail = e?.response?.data?.detail;
            ElMessage.error(typeof detail === 'string' ? detail : (detail?.[0]?.msg || '保存失败'));
        }
    };

    const createDraftsFromReport = async () => {
        try {
            // 以服务端当前报告为准，避免前端条数和服务端不一致
            const reportRes = await api.getDisciplineReport();
            const actions = reportRes.data?.actions || [];
            disciplineReport.value = reportRes.data || disciplineReport.value;
            if (!actions.length) {
                ElMessage.info('当前没有可生成的建议');
                return;
            }
            await ElMessageBox.confirm(
                `将把当前 ${actions.length} 条建议写入「纪律草稿」（同代码同方向会更新已有草稿，不会立刻改真账）。确认？`,
                '生成草稿',
                { type: 'info' },
            );
            const res = await api.createDisciplineDrafts({});
            const created = res.data?.created_count ?? 0;
            const updated = res.data?.updated_count ?? 0;
            const total = res.data?.count ?? (created + updated);
            ElMessage.success(`草稿已同步：新增 ${created}，更新 ${updated}（共 ${total}）`);
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
            if (row.side === 'sell' && !(Number(row.quantity) > 0) && !(Number(row.price) > 0)) {
                ElMessage.warning('该卖出草稿无数量/现价，请先同步最新价或删掉后重生成');
                return;
            }
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
