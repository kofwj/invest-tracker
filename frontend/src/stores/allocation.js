import { defineStore, storeToRefs } from 'pinia';
import { ref } from 'vue';
import { createAllocationModule } from '../modules/allocation.js';
import { createHoldingCorrectionHelpers } from '../modules/holdingCorrections.js';
import { todayLocalIso } from '../utils/index.js';
import { usePortfolioStore } from './portfolio.js';
import { useTransactionsStore } from './transactions.js';

export const useAllocationStore = defineStore('allocation', () => {
  const portfolioStore = usePortfolioStore();
  const transactionsStore = useTransactionsStore();

  const { holdings, deposits, dashboard } = storeToRefs(portfolioStore);
  const { pendingTransactions } = storeToRefs(transactionsStore);

  const allocationAnalysis = ref([]);
  const macroAllocationAnalysis = ref([]);
  const portfolioExpectedReturn = ref(0);
  const allocationStory = ref(null);
  const allocationStoryLoading = ref(false);

  const expectedReturnDialog = ref({
    visible: false,
    form: { code: '', name: '', expected_return: 0 },
  });
  const holdingCorrectionDialog = ref({
    visible: false,
    current: {},
    form: {
      date: todayLocalIso(),
      code: '',
      name: '',
      category: '',
      actual_quantity: 0,
      actual_avg_cost: 0,
      actual_total_dividend: 0,
      remark: '',
    },
  });
  const holdingCorrectionHistoryDialog = ref({
    visible: false,
    title: '持仓校正记录',
    records: [],
  });

  const allocationModule = createAllocationModule({
    holdings,
    deposits,
    dashboard,
    pendingTransactions,
    allocationAnalysis,
    macroAllocationAnalysis,
    portfolioExpectedReturn,
    allocationStory,
    allocationStoryLoading,
  });

  const holdingCorrections = createHoldingCorrectionHelpers({
    expectedReturnDialog,
    holdingCorrectionDialog,
    holdingCorrectionHistoryDialog,
    fetchData: () => portfolioStore.fetchData(),
    todayLocalIso,
  });

  // Automatically recalculate allocation analysis on portfolio data change
  portfolioStore.onAfterFetch(() => {
    allocationModule.calculateAllocationAnalysis();
  });

  return {
    allocationAnalysis,
    macroAllocationAnalysis,
    portfolioExpectedReturn,
    allocationStory,
    allocationStoryLoading,
    expectedReturnDialog,
    holdingCorrectionDialog,
    holdingCorrectionHistoryDialog,
    ...allocationModule,
    ...holdingCorrections,
  };
});
