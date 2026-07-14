import api from '../api/index.js';
import { ElMessage, ElMessageBox } from 'element-plus';

const createMarketModule = ({
    marketSummary,
    alertRules,
    alertEvents,
    marketLoading,
    alertChecking,
    alertEventsLoading,
    alertForm,
    alertEditDialog,
    triggeredAlerts,
    alertEventCodeFilter,
    computed,
}) => {
    const defaultAlertForm = () => ({
        target_type: 'holding',
        code: '',
        name: '',
        condition: 'above',
        threshold: 0,
        enabled: true,
    });

    const fetchMarketSummary = async () => {
        marketLoading.value = true;
        try {
            const res = await api.getMarketSummary();
            marketSummary.value = res.data || {};
        } catch (e) {
            const detail = e?.response?.data?.detail || e?.message || '加载市场摘要失败';
            ElMessage.error(detail);
        } finally {
            marketLoading.value = false;
        }
    };

    const fetchAlertRules = async () => {
        try {
            const res = await api.listAlertRules();
            alertRules.value = res.data || [];
        } catch (e) {
            ElMessage.error(e?.response?.data?.detail || '加载预警规则失败');
        }
    };

    const fetchAlertEvents = async () => {
        if (!alertEvents) return;
        alertEventsLoading.value = true;
        try {
            const code = (alertEventCodeFilter?.value || '').trim();
            const res = await api.listAlertEvents({ limit: 50, code: code || undefined });
            alertEvents.value = res.data || [];
        } catch (e) {
            ElMessage.error(e?.response?.data?.detail || '加载预警历史失败');
        } finally {
            alertEventsLoading.value = false;
        }
    };

    const refreshMarket = async () => {
        await Promise.all([fetchMarketSummary(), fetchAlertRules(), fetchAlertEvents()]);
    };

    const resetAlertForm = () => {
        alertForm.value = defaultAlertForm();
    };

    const saveAlertRule = async () => {
        const f = alertForm.value || {};
        if (!f.code) {
            ElMessage.warning('请填写代码');
            return;
        }
        if (f.threshold === null || f.threshold === undefined || f.threshold === '') {
            ElMessage.warning('请填写阈值');
            return;
        }
        try {
            const payload = {
                target_type: f.target_type || 'holding',
                code: String(f.code).trim(),
                name: (f.name || '').trim(),
                condition: f.condition || 'above',
                threshold: Number(f.threshold),
                enabled: f.enabled !== false,
            };
            if (f.id) {
                await api.updateAlertRule(f.id, payload);
                ElMessage.success('规则已更新');
            } else {
                await api.createAlertRule(payload);
                ElMessage.success('规则已添加');
            }
            alertEditDialog.value = false;
            resetAlertForm();
            await fetchAlertRules();
        } catch (e) {
            ElMessage.error(e?.response?.data?.detail || '保存失败');
        }
    };

    const openAlertCreate = () => {
        alertForm.value = defaultAlertForm();
        alertEditDialog.value = true;
    };

    const openAlertEdit = (row) => {
        alertForm.value = {
            id: row.id,
            target_type: row.target_type || 'holding',
            code: row.code,
            name: row.name || '',
            condition: row.condition || 'above',
            threshold: Number(row.threshold || 0),
            enabled: Number(row.enabled) === 1 || row.enabled === true,
        };
        alertEditDialog.value = true;
    };

    const toggleAlertEnabled = async (row) => {
        try {
            const enabled = !(Number(row.enabled) === 1 || row.enabled === true);
            await api.updateAlertRule(row.id, { enabled });
            await fetchAlertRules();
        } catch (e) {
            ElMessage.error(e?.response?.data?.detail || '更新失败');
        }
    };

    const deleteAlertRule = async (row) => {
        try {
            await ElMessageBox.confirm(
                `确定删除规则 ${row.name || row.code}（${row.condition} ${row.threshold}）？`,
                '确认删除',
                { type: 'warning' },
            );
            await api.deleteAlertRule(row.id);
            ElMessage.success('已删除');
            await fetchAlertRules();
        } catch (e) {
            if (e === 'cancel' || e === 'close') return;
            ElMessage.error(e?.response?.data?.detail || '删除失败');
        }
    };

    const checkAlerts = async (notify = false) => {
        alertChecking.value = true;
        try {
            const res = await api.checkAlerts({ notify: !!notify });
            const data = res.data || {};
            triggeredAlerts.value = data.triggered || [];
            const n = data.trigger_count || 0;
            if (n > 0) {
                ElMessage.warning(`触发 ${n} 条预警（已检查 ${data.checked_count || 0} 条规则）`);
            } else {
                ElMessage.success(`未触发预警（已检查 ${data.checked_count || 0} 条规则）`);
            }
            await fetchAlertEvents();
        } catch (e) {
            ElMessage.error(e?.response?.data?.detail || '检查失败');
        } finally {
            alertChecking.value = false;
        }
    };

    const indexRows = computed(() => marketSummary.value?.indices || []);
    const holdingsDayRows = computed(() => marketSummary.value?.holdings_day || []);
    const marketSignals = computed(() => marketSummary.value?.signals || {});
    const marketUpdatedAt = computed(() => marketSummary.value?.last_updated || '');
    const quoteCacheSeconds = computed(() => marketSummary.value?.quote_cache_seconds);

    return {
        fetchMarketSummary,
        fetchAlertRules,
        fetchAlertEvents,
        refreshMarket,
        resetAlertForm,
        saveAlertRule,
        openAlertCreate,
        openAlertEdit,
        toggleAlertEnabled,
        deleteAlertRule,
        checkAlerts,
        indexRows,
        holdingsDayRows,
        marketSignals,
        marketUpdatedAt,
        quoteCacheSeconds,
    };
};

export { createMarketModule };
export default createMarketModule;
