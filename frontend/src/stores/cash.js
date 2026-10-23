import { defineStore } from 'pinia';
import { ref } from 'vue';
import { createCashModule } from '../modules/cash.js';
import { todayLocalIso } from '../utils/index.js';
import { usePortfolioStore } from './portfolio.js';

export const useCashStore = defineStore('cash', () => {
  const portfolioStore = usePortfolioStore();

  const cashForm = ref({ amount: 0 });
  const cashFlows = ref([]);
  const cashFlowForm = ref({
    date: todayLocalIso(),
    account: '华泰证券',
    flow_type: '银证转入',
    amount: 0,
    remark: '',
  });
  const cashFlowQuery = ref({ dateRange: [], account: '', flow_type: '' });
  const cashFlowEditDialog = ref({
    visible: false,
    editId: null,
    form: { date: '', account: '', flow_type: '', amount: 0, remark: '' },
  });
  const cashAudit = ref(null);
  const activeFeeAccount = ref('华泰证券');

  // Sync cash balance from portfolio fetchData
  portfolioStore.onAfterFetch(({ cashData }) => {
    if (cashData && typeof cashData.amount !== 'undefined') {
      cashForm.value.amount = cashData.amount;
    }
    if (!cashFlowForm.value.account) {
      cashFlowForm.value.account = activeFeeAccount.value || '华泰证券';
    }
  });

  const cashModule = createCashModule({
    dashboard: portfolioStore.dashboard,
    cashForm,
    cashFlows,
    cashFlowForm,
    cashFlowQuery,
    cashFlowEditDialog,
    cashAudit,
    activeFeeAccount,
    fetchData: portfolioStore.fetchData,
  });

  return {
    cashForm,
    cashFlows,
    cashFlowForm,
    cashFlowQuery,
    cashFlowEditDialog,
    cashAudit,
    activeFeeAccount,
    ...cashModule,
  };
});
