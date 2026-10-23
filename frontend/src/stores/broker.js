import { defineStore } from 'pinia';
import { ref } from 'vue';
import { todayLocalIso } from '../utils/index.js';
import { createBrokerReconcileModule } from '../modules/brokerReconcile.js';
import { usePortfolioStore } from './portfolio.js';
import { useNotifyStore } from './notify.js';

export const useBrokerStore = defineStore('broker', () => {
  const portfolioStore = usePortfolioStore();
  const notifyStore = useNotifyStore();

  const brokerResult = ref(null);
  const brokerLoading = ref(false);
  const brokerSelected = ref([]);
  const brokerAsOfDate = ref(todayLocalIso());
  const brokerCashInput = ref('');
  const brokerHistory = ref([]);

  const brokerModule = createBrokerReconcileModule({
    brokerResult,
    brokerLoading,
    brokerSelected,
    brokerAsOfDate,
    brokerCashInput,
    brokerHistory,
    fetchData: () => portfolioStore.fetchData(),
    showSyncNotice: (msg, type) => notifyStore.showSyncNotice?.(msg, type),
  });

  return {
    brokerResult,
    brokerLoading,
    brokerSelected,
    brokerAsOfDate,
    brokerCashInput,
    brokerHistory,
    statusLabel: brokerModule.statusLabel,
    statusType: brokerModule.statusType,
    onBrokerFileChange: brokerModule.onBrokerFileChange,
    onBrokerSelectionChange: brokerModule.onBrokerSelectionChange,
    selectAllSuggestions: brokerModule.selectAllSuggestions,
    clearBrokerSelection: brokerModule.clearBrokerSelection,
    applySelectedCorrections: brokerModule.applySelectedCorrections,
    fetchBrokerHistory: brokerModule.fetchBrokerHistory,
  };
});
