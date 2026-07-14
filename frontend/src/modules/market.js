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
    alertEventStartDate,
    alertEventEndDate,
    watchlistDraft,
    watchlistSaving,
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
            // sync watchlist draft from server summary
            const wl = (marketSummary.value.watchlist || []).map((x) => ({
                code: x.code,
                name: x.name || x.code,
                secid: x.secid || '',
            }));
            if (watchlistDraft) watchlistDraft.value = wl;
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
            const start_date = (alertEventStartDate?.value || '').trim() || undefined;
            const end_date = (alertEventEndDate?.value || '').trim() || undefined;
            const res = await api.listAlertEvents({
                limit: 100,
                code: code || undefined,
                start_date,
                end_date,
            });
            alertEvents.value = res.data || [];
        } catch (e) {
            ElMessage.error(e?.response?.data?.detail || '加载预警历史失败');
        } finally {
            alertEventsLoading.value = false;
        }
    };

    const exportAlertEvents = async () => {
        try {
            const code = (alertEventCodeFilter?.value || '').trim();
            const start_date = (alertEventStartDate?.value || '').trim() || undefined;
            const end_date = (alertEventEndDate?.value || '').trim() || undefined;
            const res = await api.exportAlertEvents({
                limit: 500,
                code: code || undefined,
                start_date,
                end_date,
            });
            const blob = new Blob([res.data], { type: 'text/csv;charset=utf-8;' });
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'alert_events.csv';
            a.click();
            window.URL.revokeObjectURL(url);
            ElMessage.success('已导出预警历史');
        } catch (e) {
            ElMessage.error(e?.response?.data?.detail || '导出失败');
        }
    };

    const clearAlertEvents = async () => {
        try {
            const code = (alertEventCodeFilter?.value || '').trim();
            const start_date = (alertEventStartDate?.value || '').trim() || undefined;
            const end_date = (alertEventEndDate?.value || '').trim() || undefined;
            const hasFilter = !!(code || start_date || end_date);
            await ElMessageBox.confirm(
                hasFilter
                    ? '确定删除当前筛选条件下的预警历史？'
                    : '未设置筛选，将清空全部预警历史。确定？',
                '清空预警历史',
                { type: 'warning' },
            );
            const payload = hasFilter
                ? { code: code || undefined, start_date, end_date, clear_all: false }
                : { clear_all: true };
            const res = await api.clearAlertEvents(payload);
            ElMessage.success(`已删除 ${res.data?.deleted ?? 0} 条`);
            await fetchAlertEvents();
        } catch (e) {
            if (e === 'cancel' || e === 'close') return;
            ElMessage.error(e?.response?.data?.detail || '清空失败');
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
            const res = await api.checkAlerts({ notify: !!notify, respect_cooldown: true });
            const data = res.data || {};
            triggeredAlerts.value = data.triggered || [];
            const n = data.trigger_count || 0;
            const skipped = (data.skipped_cooldown || []).length;
            if (n > 0) {
                ElMessage.warning(
                    `触发 ${n} 条预警（已检查 ${data.checked_count || 0} 条规则` +
                    (skipped ? `，冷却跳过 ${skipped}` : '') +
                    `）`,
                );
            } else {
                ElMessage.success(
                    `未触发预警（已检查 ${data.checked_count || 0} 条规则` +
                    (skipped ? `，冷却跳过 ${skipped}` : '') +
                    `）`,
                );
            }
            await fetchAlertEvents();
        } catch (e) {
            ElMessage.error(e?.response?.data?.detail || '检查失败');
        } finally {
            alertChecking.value = false;
        }
    };

    const addWatchlistRow = () => {
        if (!watchlistDraft) return;
        watchlistDraft.value = [...(watchlistDraft.value || []), { code: '', name: '', secid: '' }];
    };

    const removeWatchlistRow = (idx) => {
        if (!watchlistDraft) return;
        const next = [...(watchlistDraft.value || [])];
        next.splice(idx, 1);
        watchlistDraft.value = next;
    };

    const saveWatchlist = async () => {
        if (!watchlistDraft) return;
        watchlistSaving.value = true;
        try {
            const items = (watchlistDraft.value || [])
                .map((x) => ({
                    code: String(x.code || '').trim(),
                    name: String(x.name || '').trim(),
                    secid: String(x.secid || '').trim(),
                }))
                .filter((x) => x.code);
            await api.saveWatchlist({ items });
            ElMessage.success('自选已保存');
            await fetchMarketSummary();
        } catch (e) {
            ElMessage.error(e?.response?.data?.detail || '保存自选失败');
        } finally {
            watchlistSaving.value = false;
        }
    };

    const indexRows = computed(() => marketSummary.value?.indices || []);
    const watchlistRows = computed(() => marketSummary.value?.watchlist || []);
    const holdingsDayRows = computed(() => marketSummary.value?.holdings_day || []);
    const marketSignals = computed(() => marketSummary.value?.signals || {});
    const marketHighlights = computed(() => marketSignals.value?.today_highlights || []);
    const marketComparisons = computed(() => marketSignals.value?.comparisons || []);
    const marketUpdatedAt = computed(() => marketSummary.value?.last_updated || '');
    const quoteCacheSeconds = computed(() => marketSummary.value?.quote_cache_seconds);
    const alertCooldownMinutes = computed(() => marketSummary.value?.alert_cooldown_minutes);

    return {
        fetchMarketSummary,
        fetchAlertRules,
        fetchAlertEvents,
        exportAlertEvents,
        clearAlertEvents,
        refreshMarket,
        resetAlertForm,
        saveAlertRule,
        openAlertCreate,
        openAlertEdit,
        toggleAlertEnabled,
        deleteAlertRule,
        checkAlerts,
        addWatchlistRow,
        removeWatchlistRow,
        saveWatchlist,
        indexRows,
        watchlistRows,
        holdingsDayRows,
        marketSignals,
        marketHighlights,
        marketComparisons,
        marketUpdatedAt,
        quoteCacheSeconds,
        alertCooldownMinutes,
    };
};

export { createMarketModule };
export default createMarketModule;
