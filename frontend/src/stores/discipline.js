import { defineStore } from 'pinia';
import { ref } from 'vue';
import { createDisciplineModule } from '../modules/discipline.js';
import { todayLocalIso } from '../utils/index.js';
import { usePortfolioStore } from './portfolio.js';
import { useTransactionsStore } from './transactions.js';

export const useDisciplineStore = defineStore('discipline', () => {
  const portfolioStore = usePortfolioStore();
  const transactionsStore = useTransactionsStore();

  const disciplineReport = ref({});
  const disciplineDrafts = ref([]);
  const disciplinePolicy = ref({
    equity_min_pct: 35,
    equity_max_pct: 55,
    defensive_min_pct: 40,
    single_holding_max_pct: 20,
    rebalance_band_pct: 3,
    preferred_buy_code: '',
    preferred_buy_name: '',
    preferred_buy_category: 'A股ETF',
    preferred_buy_account: '',
    targets: { equity_pct: 45, fixed_income_pct: 30, deposit_pct: 25 },
    plans: {},
    batch_buy_plans: {},
    named_limits: {},
    targets_active: false,
  });
  const disciplineLoading = ref(false);
  const disciplineDraftLoading = ref(false);
  const disciplinePolicyDialog = ref(false);
  const disciplineDraftEditDialog = ref(false);
  const disciplineDraftEditForm = ref({
    id: null,
    date: todayLocalIso(),
    code: '',
    name: '',
    category: 'A股ETF',
    account: '',
    direction: '买入',
    quantity: 0,
    price: 0,
    amount: 0,
    reason: '',
  });
  const disciplineSelectedDraftIds = ref([]);
  const disciplinePresets = ref([]);
  const disciplinePresetActiveId = ref(null);
  const disciplinePresetLoading = ref(false);

  const disciplineModule = createDisciplineModule({
    disciplineReport,
    disciplineDrafts,
    disciplinePolicy,
    disciplineLoading,
    disciplineDraftLoading,
    disciplinePolicyDialog,
    disciplineDraftEditDialog,
    disciplineDraftEditForm,
    disciplineSelectedDraftIds,
    fetchData: portfolioStore.fetchData,
    queryTransactions: transactionsStore.queryTransactions,
    disciplinePresets,
    disciplinePresetActiveId,
    disciplinePresetLoading,
  });

  return {
    disciplineReport,
    disciplineDrafts,
    disciplinePolicy,
    disciplineLoading,
    disciplineDraftLoading,
    disciplinePolicyDialog,
    disciplineDraftEditDialog,
    disciplineDraftEditForm,
    disciplineSelectedDraftIds,
    disciplinePresets,
    disciplinePresetActiveId,
    disciplinePresetLoading,
    ...disciplineModule,
  };
});
