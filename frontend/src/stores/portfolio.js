import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { ElLoading, ElMessage } from 'element-plus';
import api from '../api/index.js';
import { todayLocalIso } from '../utils/index.js';
import { createDepositsModule } from '../modules/deposits.js';

export const usePortfolioStore = defineStore('portfolio', () => {
  const dashboard = ref({});
  const holdings = ref([]);
  const deposits = ref([]);
  const syncing = ref(false);
  const trailingSyncing = ref(false);
  const syncNotice = ref({ text: '', type: '' });
  let syncNoticeTimer = null;

  const showSyncNotice = (text, type = '') => {
    syncNotice.value.text = text;
    syncNotice.value.type = type;
    if (syncNoticeTimer) clearTimeout(syncNoticeTimer);
    syncNoticeTimer = setTimeout(() => {
      syncNotice.value.text = '';
      syncNotice.value.type = '';
    }, 12000);
  };

  const depositDialog = ref({
    visible: false,
    isEdit: false,
    editId: null,
    form: { bank_name: '', amount: 0, interest_rate: 0, start_date: '', due_date: '', remark: '' },
  });

  const todayIso = ref(todayLocalIso());
  const refreshTodayIso = () => {
    todayIso.value = todayLocalIso();
  };

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

  const maintenanceStatus = ref({});
  const latestBackupText = computed(() =>
    maintenanceStatus.value?.latest_backup_at
      ? String(maintenanceStatus.value.latest_backup_at).replace('T', ' ').slice(0, 19)
      : '暂无备份'
  );

  // Hook for other modules to react after fetchData runs
  const afterFetchCallbacks = new Set();
  const onAfterFetch = (fn) => {
    afterFetchCallbacks.add(fn);
    return () => afterFetchCallbacks.delete(fn);
  };

  const fetchData = async () => {
    const results = await Promise.allSettled([
      api.getDashboard(),
      api.getHoldings(),
      api.getDeposits(),
      api.getSecuritiesCash(),
      api.getFeeSettings(),
    ]);
    const [dashRes, holdRes, depRes, cashRes, feeRes] = results;
    if (dashRes.status === 'fulfilled') dashboard.value = dashRes.value.data || {};
    if (holdRes.status === 'fulfilled') holdings.value = holdRes.value.data || [];
    if (depRes.status === 'fulfilled') deposits.value = depRes.value.data || [];

    const failed = results.filter((result) => result.status === 'rejected');
    if (failed.length) {
      const detail = failed[0].reason?.response?.data?.detail || failed[0].reason?.message || '未知错误';
      ElMessage.warning(`部分数据刷新失败：${detail}`);
    }

    for (const cb of afterFetchCallbacks) {
      try {
        await cb({
          dashboard: dashboard.value,
          holdings: holdings.value,
          deposits: deposits.value,
          cashData: cashRes.status === 'fulfilled' ? cashRes.value.data : null,
          feeData: feeRes.status === 'fulfilled' ? feeRes.value.data : null,
        });
      } catch (err) {
        console.error('onAfterFetch callback failed', err);
      }
    }

    return { failed: failed.length };
  };

  const syncPrices = async () => {
    syncing.value = true;
    showSyncNotice('正在同步最新价...', 'success');
    try {
      const priceRes = await api.syncPrices();
      const priceData = priceRes.data || {};
      const priceFailedCount = Array.isArray(priceData.failed) ? priceData.failed.length : 0;
      const msg = `最新价同步完成：检查 ${priceData.checked || 0} 个，价格变化 ${priceData.updated || 0} 个，无变化 ${priceData.unchanged || 0} 个，失败 ${priceFailedCount} 个`;
      const priceFailedText =
        priceFailedCount > 0
          ? priceData.failed.slice(0, 3).map((x) => `${x.code} ${x.name || ''}: ${x.reason || '失败'}`).join('；')
          : '';

      syncing.value = false;
      if (priceFailedText) {
        showSyncNotice(msg + '。' + priceFailedText, 'warning');
      } else {
        showSyncNotice(msg, 'success');
      }

      await fetchData();
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
        const failedText = data.failed.slice(0, 3).map((x) => `${x.code} ${x.name || ''}: ${x.reason || '失败'}`).join('；');
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

  // Deposits module integration
  const depositsModule = createDepositsModule({
    depositDialog,
    deposits,
    fetchData,
  });

  return {
    dashboard,
    holdings,
    deposits,
    syncing,
    trailingSyncing,
    syncNotice,
    showSyncNotice,
    todayIso,
    refreshTodayIso,
    todaySnapshotDone,
    latestPriceStatusText,
    latestBackupText,
    maintenanceStatus,
    depositDialog,
    fetchData,
    syncPrices,
    syncTrailingReturns,
    onAfterFetch,
    ...depositsModule,
  };
});
