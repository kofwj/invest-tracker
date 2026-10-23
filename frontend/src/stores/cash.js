import { defineStore, storeToRefs } from 'pinia';
import { ref } from 'vue';
import { createCashModule } from '../modules/cash.js';
import { todayLocalIso } from '../utils/index.js';
import { usePortfolioStore } from './portfolio.js';
import { useTransactionsStore } from './transactions.js';

export const useCashStore = defineStore('cash', () => {
  const portfolioStore = usePortfolioStore();
  const transactionsStore = useTransactionsStore();

  const { dashboard } = storeToRefs(portfolioStore);
  const { activeFeeAccount, feeAccounts } = storeToRefs(transactionsStore);

  const cashForm = ref({ amount: 0 });
  const cashFlows = ref([]);
  const cashFlowForm = ref({
    date: todayLocalIso(),
    account: '',
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

  // Sync cash balance from portfolio fetchData
  portfolioStore.onAfterFetch(({ cashData }) => {
    if (cashData && typeof cashData.amount !== 'undefined') {
      cashForm.value.amount = cashData.amount;
    }
    if (!cashFlowForm.value.account) {
      cashFlowForm.value.account = activeFeeAccount.value || (feeAccounts.value && feeAccounts.value[0]) || '';
    }
  });

  const cashModule = createCashModule({
    dashboard,
    cashForm,
    cashFlows,
    cashFlowForm,
    cashFlowQuery,
    cashFlowEditDialog,
    cashAudit,
    activeFeeAccount,
    fetchData: () => portfolioStore.fetchData(),
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
