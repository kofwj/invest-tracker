import { defineStore } from 'pinia';
import { ref, nextTick } from 'vue';
import { createSnapshotsModule } from '../modules/snapshots.js';
import { todayLocalIso } from '../utils/index.js';
import { usePortfolioStore } from './portfolio.js';

export const useSnapshotsStore = defineStore('snapshots', () => {
  const portfolioStore = usePortfolioStore();

  const snapshots = ref([]);
  const snapshotRange = ref([]);
  const snapshotSummary = ref(null);
  const snapshotMetrics = ref([]);
  const snapshotChangeRows = ref([]);
  const snapshotLoading = ref(false);
  const reconcileData = ref(null);
  const reconcileForm = ref({ date: todayLocalIso(), amount: 0, note: '' });
  const reconcileSaving = ref(false);
  const activeTab = ref('snapshots');

  const snapshotsModule = createSnapshotsModule({
    activeTab,
    snapshots,
    snapshotRange,
    snapshotSummary,
    snapshotMetrics,
    snapshotChangeRows,
    snapshotLoading,
    reconcileData,
    reconcileForm,
    reconcileSaving,
    fetchData: portfolioStore.fetchData,
    nextTick,
  });

  return {
    snapshots,
    snapshotRange,
    snapshotSummary,
    snapshotMetrics,
    snapshotChangeRows,
    snapshotLoading,
    reconcileData,
    reconcileForm,
    reconcileSaving,
    ...snapshotsModule,
  };
});
