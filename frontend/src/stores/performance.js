import { defineStore } from 'pinia';
import { ref, nextTick } from 'vue';
import { createPerformanceModule } from '../modules/performance.js';
import { todayLocalIso } from '../utils/index.js';
import { usePortfolioStore } from './portfolio.js';

export const usePerformanceStore = defineStore('performance', () => {
  const portfolioStore = usePortfolioStore();

  const perfSummary = ref(null);
  const perfTimeline = ref([]);
  const perfContribution = ref([]);
  const perfFlows = ref([]);
  const perfStory = ref(null);
  const perfWindows = ref([]);
  const perfLoading = ref(false);
  const perfContributionFilter = ref('all');
  const perfContributionSort = ref('contribution');
  const perfTimelineRange = ref('all');
  const perfFlowForm = ref({
    date: todayLocalIso(),
    flow_type: '投入',
    amount: 100000,
    source: '',
    remark: '',
  });

  const performanceModule = createPerformanceModule({
    perfSummary,
    perfTimeline,
    perfContribution,
    perfFlows,
    perfStory,
    perfLoading,
    perfContributionFilter,
    perfContributionSort,
    perfTimelineRange,
    perfWindows,
    perfFlowForm,
    showSyncNotice: portfolioStore.showSyncNotice,
    nextTick,
  });

  return {
    perfSummary,
    perfTimeline,
    perfContribution,
    perfFlows,
    perfStory,
    perfWindows,
    perfLoading,
    perfContributionFilter,
    perfContributionSort,
    perfTimelineRange,
    perfFlowForm,
    ...performanceModule,
  };
});
