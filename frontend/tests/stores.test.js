import { describe, it, expect, vi, beforeEach } from 'vitest';
import { setActivePinia, createPinia } from 'pinia';
import { usePortfolioStore } from '../src/stores/portfolio.js';
import { useCashStore } from '../src/stores/cash.js';
import { useAllocationStore } from '../src/stores/allocation.js';
import { useTransactionsStore } from '../src/stores/transactions.js';
import api from '../src/api/index.js';

vi.mock('../src/api/index.js', () => ({
  default: {
    updateSecuritiesCash: vi.fn().mockResolvedValue({ data: { ok: true } }),
    fetchData: vi.fn().mockResolvedValue({ data: {} }),
    queryTransactions: vi.fn().mockResolvedValue({ data: { items: [], total: 0 } }),
  },
  API: '/api',
}));

vi.mock('element-plus', () => ({
  ElLoading: { service: () => ({ close: () => {} }) },
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: vi.fn().mockResolvedValue('confirm') },
}));

describe('Pinia Stores Cross-Store Reactivity', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  it('cashStore correctly accesses portfolioStore.dashboard as a Ref (no TypeError on .value)', async () => {
    const portfolioStore = usePortfolioStore();
    const cashStore = useCashStore();

    portfolioStore.dashboard = { securities_cash: 68000, total_asset: 200000 };
    cashStore.cashForm.amount = 75000;

    await cashStore.updateCash();

    expect(api.updateSecuritiesCash).toHaveBeenCalledWith(75000);
  });

  it('allocationStore correctly calculates allocation analysis using portfolioStore holdings/deposits/dashboard Refs', () => {
    const portfolioStore = usePortfolioStore();
    const allocationStore = useAllocationStore();

    portfolioStore.holdings = [
      { code: '510300', name: '沪深300ETF', category: 'A股ETF', current_value: 120000, cost_amount: 100000 },
      { code: '511010', name: '国债ETF', category: '债券ETF', current_value: 80000, cost_amount: 80000 },
    ];
    portfolioStore.deposits = [
      { id: 1, bank_name: '招商银行', amount: 50000, interest_rate: 2.5 },
    ];
    portfolioStore.dashboard = {
      total_asset: 250000,
      securities_cash: 0,
      bank_balance: 50000,
    };

    expect(() => allocationStore.calculateAllocationAnalysis()).not.toThrow();
    expect(allocationStore.allocationAnalysis.length).toBeGreaterThan(0);
  });

  it('transactionsStore correctly finds assets from portfolioStore.holdings via queryAssetByCode / queryAssetByName', () => {
    const portfolioStore = usePortfolioStore();
    const transactionsStore = useTransactionsStore();

    portfolioStore.holdings = [
      { code: '510300', name: '沪深300ETF', category: 'A股ETF', quantity: 5000, current_price: 3.5 },
      { code: '159915', name: '创业板ETF', category: 'A股ETF', quantity: 3000, current_price: 1.8 },
    ];

    let matchCode = [];
    transactionsStore.queryAssetByCode('510300', (res) => {
      matchCode = res;
    });
    expect(matchCode.length).toBe(1);
    expect(matchCode[0].name).toBe('沪深300ETF');

    let matchName = [];
    transactionsStore.queryAssetByName('创业板', (res) => {
      matchName = res;
    });
    expect(matchName.length).toBe(1);
    expect(matchName[0].code).toBe('159915');
  });

  it('cashStore and transactionsStore sync account without hardcoded 华泰证券', () => {
    const portfolioStore = usePortfolioStore();
    const transactionsStore = useTransactionsStore();
    const cashStore = useCashStore();

    expect(cashStore.cashFlowForm.account).toBe('');
    expect(transactionsStore.transForm.account).toBe('');

    // Simulate backend fee settings response
    transactionsStore.loadFeeSettingsToForm({
      accounts: ['银河证券', '中信证券'],
      active_account: '银河证券',
      settings: {},
    });

    expect(transactionsStore.activeFeeAccount).toBe('银河证券');
    expect(transactionsStore.transForm.account).toBe('银河证券');
  });
});
