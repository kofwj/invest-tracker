import api from '../api/index.js';
import { ElLoading, ElMessage } from 'element-plus';
import { todayLocalIso } from '../utils/index.js';
import { computed } from 'vue';

/**
 * Core data fetching and sync helpers.
 * Extracted from main.js: fetchData + syncPrices + syncTrailingReturns + status computeds.
 */
const createDataSync = ({
    dashboard,
    holdings,
    deposits,
    cashForm,
    cashFlowForm,
    activeFeeAccount,
    syncing,
    trailingSyncing,
    syncNotice,
    maintenanceStatus,
    loadFeeSettingsToForm,
    calculateAllocationAnalysis,
    activeTab,
    showSyncNotice,
    renderAllocationCharts,
}) => {
    const fetchData = async () => {
        const [dashRes, holdRes, depRes, cashRes, feeRes] = await Promise.all([
            api.getDashboard(),
            api.getHoldings(),
            api.getDeposits(),
            api.getSecuritiesCash(),
            api.getFeeSettings()
        ]);
        dashboard.value = dashRes.data;
        holdings.value = holdRes.data;
        deposits.value = depRes.data;
        cashForm.value.amount = cashRes.data.amount;
        loadFeeSettingsToForm(feeRes.data || {});
        if (!cashFlowForm.value.account) cashFlowForm.value.account = activeFeeAccount.value || '华泰证券';
        calculateAllocationAnalysis();
        if (activeTab.value === 'allocation') renderAllocationCharts();
    };

    const syncPrices = async () => {
        syncing.value = true;
        showSyncNotice('正在同步最新价...', 'success');
        try {
            const priceRes = await api.syncPrices();
            const priceData = priceRes.data || {};
            const priceFailedCount = Array.isArray(priceData.failed) ? priceData.failed.length : 0;
            const msg = `最新价同步完成：检查 ${priceData.checked || 0} 个，价格变化 ${priceData.updated || 0} 个，无变化 ${priceData.unchanged || 0} 个，失败 ${priceFailedCount} 个`;
            const priceFailedText = priceFailedCount > 0
                ? priceData.failed.slice(0, 3).map(x => `${x.code} ${x.name || ''}: ${x.reason || '失败'}`).join('；')
                : '';

            syncing.value = false;
            if (priceFailedText) {
                showSyncNotice(msg + '。' + priceFailedText, 'warning');
            } else {
                showSyncNotice(msg, 'success');
            }

            fetchData().catch(refreshErr => {
                const refreshDetail = refreshErr?.response?.data?.detail || refreshErr?.message || '未知错误';
                showSyncNotice(msg + `。但刷新页面数据失败：${refreshDetail}`, 'warning');
            });
        } catch (e) {
            const detail = e?.response?.data?.detail || e?.message || '未知错误';
            showSyncNotice('最新价同步失败：' + detail, 'error');
        } finally {
            syncing.value = false;
        }
    };

    const syncTrailingReturns = async () => {
        trailingSyncing.value = true;
        const loading = ElLoading.service({ text: '正在同步近一年标的收益率...', background: 'rgba(255, 255, 255, 0.65)' });
        try {
            const res = await api.syncTrailingReturns();
            await fetchData();
            const data = res.data || {};
            const failedCount = Array.isArray(data.failed) ? data.failed.length : 0;
            const msg = `近一年收益率同步完成：检查 ${data.checked || 0} 个，成功 ${data.updated || 0} 个，失败 ${failedCount} 个`;
            if (failedCount > 0) {
                const failedText = data.failed.slice(0, 3).map(x => `${x.code} ${x.name || ''}: ${x.reason || '失败'}`).join('；');
                showSyncNotice(msg + '。' + failedText, 'warning');
                ElMessage.warning(msg + '。' + failedText);
            } else {
                showSyncNotice(msg, '');
            }
        } catch (e) {
            const detail = e?.response?.data?.detail || e?.message || '未知错误';
            showSyncNotice('近一年收益率同步失败：' + detail, 'error');
            ElMessage.error('近一年收益率同步失败：' + detail);
        } finally {
            loading.close();
            trailingSyncing.value = false;
        }
    };

    const todayIso = computed(() => todayLocalIso());
    const todaySnapshotDone = computed(() => dashboard.value.latest_snapshot_date === todayIso.value);
    const latestPriceStatusText = computed(() => {
        const raw = dashboard.value.latest_price_updated_at;
        if (!raw) return '暂无同步记录';
        const t = String(raw).replace('T', ' ').slice(0, 19);
        if (dashboard.value.price_stale) {
            const h = dashboard.value.price_age_hours;
            return h != null ? `${t}（已偏旧约 ${h} 小时）` : `${t}（已偏旧）`;
        }
        return t;
    });
    const latestBackupText = computed(() => maintenanceStatus.value.latest_backup_at ? String(maintenanceStatus.value.latest_backup_at).replace('T', ' ').slice(0, 19) : '暂无备份');

    return {
        fetchData,
        syncPrices,
        syncTrailingReturns,
        todayIso,
        todaySnapshotDone,
        latestPriceStatusText,
        latestBackupText,
    };
};

export { createDataSync };
export default createDataSync;
