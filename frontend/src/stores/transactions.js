import { defineStore } from 'pinia';
import { ref } from 'vue';
import { createTransactionsModule } from '../modules/transactions.js';
import { createFeeHelpers } from '../composables/feeHelpers.js';
import { createImportExportHelpers } from '../composables/importExportHelpers.js';
import { todayLocalIso } from '../utils/index.js';
import { usePortfolioStore } from './portfolio.js';

export const useTransactionsStore = defineStore('transactions', () => {
  const portfolioStore = usePortfolioStore();

  const allTransactions = ref([]);
  const filteredTransactions = ref([]);
  const pendingTransactions = ref([]);
  const pendingPurchaseTotal = ref(0);
  const transPage = ref({ page: 1, pageSize: 100, total: 0 });
  const transQuery = ref({
    dateRange: [],
    code: '',
    name: '',
    direction: '',
  });
  const transEditDialog = ref({
    visible: false,
    editId: null,
    form: {
      date: '',
      code: '',
      name: '',
      category: '',
      account: '',
      direction: '',
      quantity: 0,
      price: 0,
      amount: 0,
      fee: 0,
      remark: '',
    },
  });
  const transDialog = ref({
    visible: false,
    title: '',
    transactions: [],
  });
  const transForm = ref({
    date: todayLocalIso(),
    code: '',
    name: '',
    category: '',
    account: '华泰证券',
    direction: '买入',
    quantity: 0,
    price: 0,
    amount: 0,
    fee: 0,
  });

  const feeManuallyEdited = ref(false);
  const feeSettings = ref({});
  const feeAccounts = ref(['华泰证券']);
  const activeFeeAccount = ref('华泰证券');
  const newFeeAccountName = ref('');
  const feeCategories = ['A股权益', 'A股ETF', '港股ETF', 'REITs', '黄金', '债基', '其他'];
  const feeAutoHint = ref('');

  const feeHelpers = createFeeHelpers({
    feeSettings,
    feeAccounts,
    activeFeeAccount,
    newFeeAccountName,
    feeCategories,
    feeManuallyEdited,
    feeAutoHint,
    transForm,
  });

  // When portfolio fetches data, sync fee settings
  portfolioStore.onAfterFetch(({ feeData }) => {
    if (feeData) {
      feeHelpers.loadFeeSettingsToForm(feeData);
    }
  });

  const activeTab = ref('transactions');

  const transactionsModule = createTransactionsModule({
    activeTab,
    allTransactions,
    filteredTransactions,
    pendingTransactions,
    pendingPurchaseTotal,
    transDialog,
    transEditDialog,
    transForm,
    transQuery,
    transPage,
    activeFeeAccount,
    feeAccounts,
    feeManuallyEdited,
    feeAutoHint,
    holdings: portfolioStore.holdings,
    estimateFeeIfAuto: feeHelpers.estimateFeeIfAuto,
    fetchData: portfolioStore.fetchData,
  });

  const importExport = createImportExportHelpers({
    todayLocalIso,
    queryTransactions: transactionsModule.queryTransactions,
    fetchData: portfolioStore.fetchData,
    transQuery,
  });

  return {
    allTransactions,
    filteredTransactions,
    pendingTransactions,
    pendingPurchaseTotal,
    transPage,
    transQuery,
    transEditDialog,
    transDialog,
    transForm,
    feeManuallyEdited,
    feeSettings,
    feeAccounts,
    activeFeeAccount,
    newFeeAccountName,
    feeCategories,
    feeAutoHint,
    ...feeHelpers,
    ...transactionsModule,
    downloadTransactionsTemplate: importExport.downloadTransactionsTemplate,
    exportTransactions: importExport.exportTransactions,
    importTransactions: importExport.importTransactions,
  };
});
