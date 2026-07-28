import api from '../api/index.js';
import { ElMessage, ElMessageBox } from 'element-plus';
import { computed, ref } from 'vue';

const numOr = (v, fallback) => {
    const n = Number(v);
    return Number.isFinite(n) ? n : fallback;
};

const clonePolicy = (value) => JSON.parse(JSON.stringify(value || {}));

const createDisciplineModule = ({
    disciplineReport,
    disciplineDrafts,
    disciplinePolicy,
    disciplineLoading,
    disciplineDraftLoading,
    disciplinePolicyDialog,
    disciplineDraftEditDialog,
    disciplineDraftEditForm,
    disciplineSelectedDraftIds,
    fetchData,
    queryTransactions,
    afterDisciplineChange,
    disciplinePresets,
    disciplinePresetActiveId,
    disciplinePresetLoading,
}) => {
    const localPresets = disciplinePresets || ref([]);
    const localActiveId = disciplinePresetActiveId || ref(null);
    const localPresetLoading = disciplinePresetLoading || ref(false);
    let policyBeforeEdit = null;
    const runAfterDisciplineChange = async () => {
        if (typeof afterDisciplineChange === 'function') {
            try {
                await afterDisciplineChange();
            } catch (_) {
                /* best effort */
            }
        }
    };

    const refreshAfterLedgerChange = async () => {
        await refreshDiscipline();
        const tasks = [];
        if (typeof fetchData === 'function') tasks.push(fetchData());
        if (typeof queryTransactions === 'function') tasks.push(queryTransactions());
        if (tasks.length) {
            try {
                await Promise.all(tasks);
            } catch (_) {
                /* best effort */
            }
        }
        await runAfterDisciplineChange();
    };

    const fetchDisciplineReport = async () => {
        disciplineLoading.value = true;
        try {
            const res = await api.getDisciplineReport();
            disciplineReport.value = res.data || {};
            if (res.data?.policy) {
                const p = res.data.policy || {};
                if (!p.targets) p.targets = { equity_pct: 45, fixed_income_pct: 30, deposit_pct: 25 };
                if (!p.plans) p.plans = {};
                disciplinePolicy.value = {
                    ...(disciplinePolicy.value || {}),
                    ...p,
                    targets: { ...(disciplinePolicy.value?.targets || {}), ...(p.targets || {}) },
                    plans: { ...(disciplinePolicy.value?.plans || {}), ...(p.plans || {}) },
                };
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
            if (disciplineSelectedDraftIds) {
                const live = new Set((disciplineDrafts.value || []).map((d) => d.id));
                disciplineSelectedDraftIds.value = (disciplineSelectedDraftIds.value || []).filter((id) => live.has(id));
            }
        } catch (e) {
            ElMessage.error(e?.response?.data?.detail || '加载草稿失败');
        } finally {
            disciplineDraftLoading.value = false;
        }
    };

    const fetchDisciplinePresets = async () => {
        localPresetLoading.value = true;
        try {
            const res = await api.listDisciplinePresets();
            const data = res.data || {};
            localPresets.value = Array.isArray(data.presets) ? data.presets : [];
            localActiveId.value = data.active_id || null;
        } catch (e) {
            console.warn('discipline presets failed', e);
        } finally {
            localPresetLoading.value = false;
        }
    };

    const applyDisciplinePreset = async (presetId) => {
        const id = String(presetId || '').trim();
        if (!id) return;
        const meta = (localPresets.value || []).find((p) => p.id === id);
        const label = meta?.label || id;
        const summary = meta?.summary || '';
        try {
            await ElMessageBox.confirm(
                `将套用「${label}」目标尺子${summary ? `：${summary}` : ''}。\n只改权益/固收/存款目标和安全带，不改优先加仓代码、禁开名单和格力上限。确认？`,
                '一键套用预设',
                { type: 'info', confirmButtonText: '套用', cancelButtonText: '取消' },
            );
        } catch (e) {
            if (e === 'cancel' || e === 'close') return;
            throw e;
        }
        localPresetLoading.value = true;
        try {
            const res = await api.applyDisciplinePreset(id);
            const policy = res.data?.policy;
            if (policy) disciplinePolicy.value = policy;
            ElMessage.success(`已套用「${res.data?.label || label}」`);
            await refreshDiscipline();
            await fetchDisciplinePresets();
            await runAfterDisciplineChange();
        } catch (e) {
            if (e === 'cancel' || e === 'close') return;
            ElMessage.error(e?.response?.data?.detail || '套用失败');
        } finally {
            localPresetLoading.value = false;
        }
    };

    const refreshDiscipline = async () => {
        await Promise.all([fetchDisciplineReport(), fetchDisciplineDrafts(), fetchDisciplinePresets()]);
    };

    const openPolicyDialog = async () => {
        try {
            const res = await api.getDisciplinePolicy();
            const p = res.data || {};
            if (!p.targets) p.targets = { equity_pct: 45, fixed_income_pct: 30, deposit_pct: 25 };
            if (!p.plans) p.plans = { a500_batch_target_amount: 200000, gree_soft_max_pct: 15 };
            policyBeforeEdit = clonePolicy(disciplinePolicy.value);
            disciplinePolicy.value = clonePolicy(p);
        } catch (e) {
            ElMessage.error(e?.response?.data?.detail || '加载纪律参数失败，暂不能编辑');
            return;
        }
        if (disciplinePolicy.value && !disciplinePolicy.value.targets) {
            disciplinePolicy.value.targets = { equity_pct: 45, fixed_income_pct: 30, deposit_pct: 25 };
        }
        if (disciplinePolicy.value && !disciplinePolicy.value.plans) {
            disciplinePolicy.value.plans = { a500_batch_target_amount: 200000, gree_soft_max_pct: 15 };
        }
        disciplinePolicyDialog.value = true;
    };

    const cancelPolicy = () => {
        if (policyBeforeEdit) disciplinePolicy.value = clonePolicy(policyBeforeEdit);
        policyBeforeEdit = null;
        disciplinePolicyDialog.value = false;
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
            const plans = {
                a500_batch_target_amount: numOr(p.plans?.a500_batch_target_amount, 200000),
                a500_batch_code: String(p.plans?.a500_batch_code || preferred_buy_code).trim(),
                a500_batch_name: String(p.plans?.a500_batch_name || p.preferred_buy_name || '').trim(),
                gree_code: String(p.plans?.gree_code || '000651').trim(),
                gree_name: String(p.plans?.gree_name || '格力电器').trim(),
                gree_soft_max_pct: numOr(p.plans?.gree_soft_max_pct, 15),
            };
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
                plans,
                named_limits: Array.isArray(p.named_limits) ? p.named_limits : undefined,
                no_new_codes: Array.isArray(p.no_new_codes) ? p.no_new_codes : undefined,
                fixed_income_categories: Array.isArray(p.fixed_income_categories) ? p.fixed_income_categories : undefined,
                defensive_extra_categories: Array.isArray(p.defensive_extra_categories)
                    ? p.defensive_extra_categories
                    : undefined,
            };
            await api.saveDisciplinePolicy(payload);
            ElMessage.success('纪律参数已保存');
            policyBeforeEdit = null;
            disciplinePolicyDialog.value = false;
            await refreshDiscipline();
            await runAfterDisciplineChange();
        } catch (e) {
            const detail = e?.response?.data?.detail;
            ElMessage.error(typeof detail === 'string' ? detail : (detail?.[0]?.msg || '保存失败'));
        }
    };

    const createDraftsFromReport = async () => {
        try {
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

    const openDraftEdit = (row) => {
        if (!disciplineDraftEditDialog || !disciplineDraftEditForm) return;
        disciplineDraftEditForm.value = {
            id: row.id,
            side: row.side,
            code: row.code,
            name: row.name,
            quantity: Number(row.quantity || 0),
            price: Number(row.price || 0),
            amount: Number(row.amount || 0),
            reason: row.reason || '',
            account: row.account || '华泰证券',
        };
        disciplineDraftEditDialog.value = true;
    };

    const saveDraftEdit = async () => {
        const f = disciplineDraftEditForm?.value || {};
        if (!f.id) return;
        try {
            if (!(Number(f.amount) > 0)) {
                ElMessage.error('金额必须大于 0');
                return;
            }
            await api.updateDisciplineDraft(f.id, {
                quantity: Number(f.quantity || 0),
                price: Number(f.price || 0),
                amount: Number(f.amount || 0),
                reason: f.reason || '',
                account: f.account || '华泰证券',
            });
            ElMessage.success('草稿已更新');
            disciplineDraftEditDialog.value = false;
            await fetchDisciplineDrafts();
        } catch (e) {
            ElMessage.error(e?.response?.data?.detail || '更新草稿失败');
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
                ElMessage.warning('该卖出草稿无数量/现价，请先编辑补数量，或同步最新价后重生成');
                return;
            }
            await ElMessageBox.confirm(
                `确认后会写入真实交易记录（${row.side === 'sell' ? '卖出' : '买入/申购待确认'} ${row.name || row.code} 约 ${row.amount} 元）。确定？`,
                '确认入账',
                { type: 'warning' },
            );
            await api.confirmDisciplineDraft(row.id);
            ElMessage.success('已写入真实交易');
            await refreshAfterLedgerChange();
        } catch (e) {
            if (e === 'cancel' || e === 'close') return;
            ElMessage.error(e?.response?.data?.detail || '确认失败');
        }
    };

    const onDraftSelectionChange = (rows) => {
        if (!disciplineSelectedDraftIds) return;
        disciplineSelectedDraftIds.value = (rows || []).map((r) => r.id);
    };

    const confirmSelectedDrafts = async () => {
        const ids = disciplineSelectedDraftIds?.value || [];
        if (!ids.length) {
            ElMessage.info('请先勾选要确认的草稿');
            return;
        }
        try {
            await ElMessageBox.confirm(
                `将批量确认 ${ids.length} 条草稿写入真实交易。确定？`,
                '批量确认入账',
                { type: 'warning' },
            );
            const res = await api.confirmDisciplineDrafts({ draft_ids: ids });
            const ok = res.data?.count || 0;
            const errors = res.data?.errors || [];
            const errN = errors.length;
            if (errN > 0) {
                ElMessage.warning(`批量完成：成功 ${ok}，失败 ${errN}。失败项已保留勾选`);
                const failedIds = new Set(errors.map((item) => item.draft_id).filter(Boolean));
                if (disciplineSelectedDraftIds) {
                    disciplineSelectedDraftIds.value = ids.filter((id) => failedIds.has(id));
                }
            } else {
                ElMessage.success(`批量完成：成功 ${ok}`);
                if (disciplineSelectedDraftIds) disciplineSelectedDraftIds.value = [];
            }
            await refreshAfterLedgerChange();
        } catch (e) {
            if (e === 'cancel' || e === 'close') return;
            ElMessage.error(e?.response?.data?.detail || '批量确认失败');
        }
    };

    const breaches = computed(() => disciplineReport.value?.breaches || []);
    const actions = computed(() => disciplineReport.value?.actions || []);
    const planItems = computed(() => disciplineReport.value?.plans || []);
    const helpNotes = computed(() => disciplineReport.value?.help_notes || []);
    const snapshot = computed(() => disciplineReport.value?.snapshot || {});
    const targets = computed(() => disciplineReport.value?.targets || {});
    const summaryText = computed(() => disciplineReport.value?.summary || '');

    return {
        fetchDisciplineReport,
        fetchDisciplineDrafts,
        fetchDisciplinePresets,
        applyDisciplinePreset,
        refreshDiscipline,
        openPolicyDialog,
        cancelPolicy,
        savePolicy,
        createDraftsFromReport,
        openDraftEdit,
        saveDraftEdit,
        deleteDraft,
        confirmDraft,
        onDraftSelectionChange,
        confirmSelectedDrafts,
        breaches,
        actions,
        planItems,
        helpNotes,
        snapshot,
        targets,
        summaryText,
    };
};

export { createDisciplineModule };
export default createDisciplineModule;
