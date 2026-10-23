import { defineStore, storeToRefs } from 'pinia';
import { ref } from 'vue';
import { createDividendHelpers } from '../modules/dividends.js';
import { createImportExportHelpers } from '../composables/importExportHelpers.js';
import { todayLocalIso } from '../utils/index.js';
import { usePortfolioStore } from './portfolio.js';
import { useTransactionsStore } from './transactions.js';

export const useDividendStore = defineStore('dividends', () => {
  const portfolioStore = usePortfolioStore();
  const transactionsStore = useTransactionsStore();

  const dividendLoading = ref(false);
  const dividendConfirming = ref(false);
  const dividendTableRef = ref(null);
  const dividendDialog = ref({
    visible: false,
    lookbackDays: 400,
    drafts: [],
    selected: [],
    summary: null,
    unsupported: [],
    failed: [],
  });

  const { activeFeeAccount, transQuery } = storeToRefs(transactionsStore);

  const dividendHelpers = createDividendHelpers({
    dividendDialog,
    dividendTableRef,
    dividendLoading,
    dividendConfirming,
    activeFeeAccount,
    fetchData: () => portfolioStore.fetchData(),
    queryTransactions: () => transactionsStore.queryTransactions(),
  });

  const importExportHelpers = createImportExportHelpers({
    todayLocalIso,
    queryTransactions: () => transactionsStore.queryTransactions(),
    fetchData: () => portfolioStore.fetchData(),
    transQuery,
  });

  return {
    dividendLoading,
    dividendConfirming,
    dividendTableRef,
    dividendDialog,
    openDividendDraftDialog: dividendHelpers.openDividendDraftDialog,
    dividendStatusLabel: dividendHelpers.dividendStatusLabel,
    dividendStatusType: dividendHelpers.dividendStatusType,
    isDividendDraftSelectable: dividendHelpers.isDividendDraftSelectable,
    onDividendSelectionChange: dividendHelpers.onDividendSelectionChange,
    selectSelectableDividendDrafts: dividendHelpers.selectSelectableDividendDrafts,
    clearDividendDraftSelection: dividendHelpers.clearDividendDraftSelection,
    scanDividendDrafts: dividendHelpers.scanDividendDrafts,
    confirmSelectedDividends: dividendHelpers.confirmSelectedDividends,
    downloadDividendTemplate: importExportHelpers.downloadDividendTemplate,
    importDividends: importExportHelpers.importDividends,
  };
});
