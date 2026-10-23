import { defineStore } from 'pinia';
import { ref, watch } from 'vue';
import { createMaintenanceHelpers } from '../composables/domainHelpers.js';
import { API } from '../api/index.js';
import { usePortfolioStore } from './portfolio.js';
import { useSnapshotsStore } from './snapshots.js';
import { useTransactionsStore } from './transactions.js';

export const useMaintenanceStore = defineStore('maintenance', () => {
  const portfolioStore = usePortfolioStore();
  const snapshotsStore = useSnapshotsStore();
  const transactionsStore = useTransactionsStore();

  const maintenanceStatus = ref({});
  const backups = ref([]);
  const maintenanceLoading = ref(false);

  // Keep portfolioStore.maintenanceStatus in sync so latestBackupText computes correctly
  watch(
    maintenanceStatus,
    (val) => {
      portfolioStore.maintenanceStatus = val || {};
    },
    { immediate: true },
  );

  const helpers = createMaintenanceHelpers({
    maintenanceStatus,
    backups,
    maintenanceLoading,
    fetchData: () => portfolioStore.fetchData(),
    fetchSnapshots: () => snapshotsStore.fetchSnapshots(),
    queryTransactions: () => transactionsStore.queryTransactions(),
    API,
  });

  return {
    maintenanceStatus,
    backups,
    maintenanceLoading,
    fetchMaintenance: helpers.fetchMaintenance,
    createDbBackup: helpers.createDbBackup,
    downloadBackup: helpers.downloadBackup,
    restoreBackup: helpers.restoreBackup,
    deleteBackup: helpers.deleteBackup,
    restoreUploadedBackup: helpers.restoreUploadedBackup,
  };
});
