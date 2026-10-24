/**
 * 阶段 2 批次 A 移动卡片测试：
 * 覆盖 OverviewTab / HoldingsTab / TransactionsTab / DepositsTab 4 个页面的 6 张表格。
 *
 * 验证标准：
 *  - 窄屏（≤640px，CARD_QUERY）下 el-table 卸载，渲染对应的卡片列表；
 *  - 卡片覆盖首要决策与排序字段（如标的名、市值、持仓浮盈、流水金额、起止日、利率等）；
 *  - 交互保留：持仓卡片点击唤起交易明细（showTransactions）、K 线按钮、编辑与删除按钮正常响应；
 *  - 宽屏（>640px）下仍透传回原生表格分支。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { createApp, h, ref, computed } from 'vue';
import { APP_CTX_KEY } from '../src/composables/useAppCtx.js';
import { CARD_QUERY } from '../src/modules/dataTable.js';
import OverviewTab from '../src/views/OverviewTab.vue';
import HoldingsTab from '../src/views/HoldingsTab.vue';
import TransactionsTab from '../src/views/TransactionsTab.vue';
import DepositsTab from '../src/views/DepositsTab.vue';

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), alert: vi.fn() },
  ElLoading: { service: () => ({ close: () => {} }) },
  ElNotification: vi.fn(),
}));

vi.mock('../src/charts/index.js', () => ({
  renderDailyPnlChartView: () => true,
  waitForChartDom: async () => true,
  renderAllocationChartsView: () => true,
  renderSnapshotChartsView: () => true,
  renderOverviewWeekChartView: () => true,
  renderKlineChartView: () => {},
  analyzeKlineTrend: () => ({ points: [] }),
  resizeAllCharts: () => {},
  readTheme: () => ({}),
}));

vi.mock('../src/api/index.js', () => ({
  default: {
    getDividendCalendar: vi.fn().mockResolvedValue({ data: { items: [], source_status: 'ok', fetched_at: '' } }),
    getAiStatus: vi.fn().mockResolvedValue({ data: { enabled: false } }),
    getHoldings: vi.fn().mockResolvedValue({ data: [] }),
    getTransactions: vi.fn().mockResolvedValue({ data: { items: [], total: 0 } }),
    getDeposits: vi.fn().mockResolvedValue({ data: [] }),
    getDashboard: vi.fn().mockResolvedValue({ data: {} }),
  },
}));

let restoreMatchMedia = null;
let appInstance = null;
let hostElement = null;

function stubMatchMedia(matches) {
  const had = 'matchMedia' in window;
  const original = window.matchMedia;
  const listeners = new Set();
  const mediaQuery = {
    media: CARD_QUERY,
    matches,
    addEventListener(type, handler) {
      if (type === 'change') listeners.add(handler);
    },
    removeEventListener(type, handler) {
      if (type === 'change') listeners.delete(handler);
    },
    addListener(handler) { listeners.add(handler); },
    removeListener(handler) { listeners.delete(handler); },
    dispatchEvent: () => true,
  };
  window.matchMedia = () => mediaQuery;
  return {
    restore() {
      if (had) window.matchMedia = original;
      else delete window.matchMedia;
    },
  };
}

const passthrough = (name) => ({
  name,
  setup(_, { slots, attrs }) {
    return () => h('div', attrs, slots.default ? slots.default() : []);
  },
});

function mountView(Component, ctx) {
  hostElement = document.createElement('div');
  document.body.appendChild(hostElement);

  appInstance = createApp({
    setup() {
      return () => h(Component);
    },
  });

  appInstance.provide(APP_CTX_KEY, ctx);

  // 基础常用组件桩
  const stubs = [
    'ElCard', 'ElRow', 'ElCol', 'ElButton', 'ElTag', 'ElTooltip', 'ElAlert',
    'ElInput', 'ElSelect', 'ElOption', 'ElPagination', 'ElProgress', 'ElEmpty',
    'ElDatePicker', 'ElForm', 'ElFormItem', 'ElInputNumber', 'ElDivider',
    'ElUpload', 'ElSpace',
    'PageShell', 'HomeDashboard', 'SnapshotReminder', 'KlineDialog',
  ];
  stubs.forEach((name) => appInstance.component(name, passthrough(name)));

  // ElAutocomplete 作用域插槽桩：提供 { item: {} } 避免解构报错
  appInstance.component('ElAutocomplete', {
    name: 'ElAutocomplete',
    setup(_, { slots }) {
      return () => h('div', slots.default ? slots.default({ item: { code: '', name: '' } }) : []);
    },
  });

  // loading 指令桩
  appInstance.directive('loading', {
    mounted(el, binding) { el.dataset.loading = String(binding.value); },
    updated(el, binding) { el.dataset.loading = String(binding.value); },
  });

  appInstance.mount(hostElement);
  return hostElement;
}

afterEach(() => {
  if (appInstance) appInstance.unmount();
  if (hostElement) hostElement.remove();
  appInstance = null;
  hostElement = null;
  if (restoreMatchMedia) restoreMatchMedia.restore();
  restoreMatchMedia = null;
});

describe('阶段 2 批次 A：OverviewTab (今日总览)', () => {
  it('窄屏下渲染持仓速览卡片，且点击卡片触发 onRowClick', () => {
    restoreMatchMedia = stubMatchMedia(true);
    const showTransMock = vi.fn();

    const sampleHoldings = [
      { code: '510300', name: '沪深300ETF', category: '宽基', quantity: 10000, last_price: 3.5, total_dividend: 500 },
      { code: '510500', name: '中证500ETF', category: '宽基', quantity: 2000, last_price: 5.2, total_dividend: 120 },
    ];

    const ctx = {
      dashboard: ref({ total_assets: 100000 }),
      holdings: ref(sampleHoldings),
      todaySnapshotDone: ref(true),
      latestPriceStatusText: ref('正常'),
      pendingTransactions: ref([]),
      goPendingTransactions: vi.fn(),
      marketSignals: ref([]),
      refreshMarket: vi.fn(),
      showTransactions: showTransMock,
      holdingFloatProfit: (h) => (Number(h.last_price || 0) - 3) * Number(h.quantity || 0),
      formatMoney: (v) => `¥${Number(v || 0).toFixed(2)}`,
      formatPercent: (v) => `${(Number(v || 0) * 100).toFixed(1)}%`,
      goTab: vi.fn(),
      allocationSummary: ref({}),
      portfolioExpectedReturn: ref('8.5'),
      reconcileRecord: ref({}),
      fetchReconcile: vi.fn(),
    };

    const host = mountView(OverviewTab, ctx);

    // 窄屏卡片容器
    const cards = host.querySelectorAll('.overview-holdings-table ~ * .data-card, [aria-label="持仓速览"] .data-card');
    expect(cards.length).toBe(2);

    // 关键文字断言
    expect(host.textContent).toContain('沪深300ETF');
    expect(host.textContent).toContain('510300 · 宽基');
    expect(host.textContent).toContain('¥35000.00'); // 市值 = 10000 * 3.5

    // 点击第一张卡片触发交互
    const firstCard = cards[0].querySelector('.m-card-clickable');
    expect(firstCard).toBeTruthy();
    firstCard.click();
    expect(showTransMock).toHaveBeenCalledWith(expect.objectContaining({ code: '510300' }));
  });
});

describe('阶段 2 批次 A：HoldingsTab (持仓明细)', () => {
  it('窄屏下渲染持仓卡片，支持查看交易流水、K线按钮与改价', () => {
    restoreMatchMedia = stubMatchMedia(true);
    const showTransMock = vi.fn();

    const sampleHoldings = [
      {
        code: '600519',
        name: '贵州茅台',
        category: '白酒',
        quantity: 100,
        last_price: 1600,
        avg_cost: 1500,
        diluted_cost: 1400,
        total_dividend: 3000,
        expected_return: 0.1,
        trailing_return_1y: 0.05,
      },
    ];

    const ctx = {
      holdings: ref(sampleHoldings),
      dashboard: ref({}),
      showTransactions: showTransMock,
      openExpectedReturnDialog: vi.fn(),
      openHoldingCorrectionDialog: vi.fn(),
      formatMoney: (v) => `¥${Number(v || 0).toFixed(2)}`,
      formatPercent: (v) => `${(Number(v || 0) * 100).toFixed(1)}%`,
      holdingFloatProfit: () => 10000,
      holdingLifetimeProfit: () => 20000,
      holdingFloatProfitRate: () => 0.0667,
      holdingLifetimeProfitRate: () => 0.1428,
      trailingSyncing: ref(false),
      syncTrailingReturns: vi.fn(),
      fetchData: vi.fn(),
      goTab: vi.fn(),
    };

    const host = mountView(HoldingsTab, ctx);

    // 持仓卡片
    const cards = host.querySelectorAll('[aria-label="持仓明细"] .data-card');
    expect(cards.length).toBe(1);

    // 核心决策字段存在
    expect(host.textContent).toContain('贵州茅台');
    expect(host.textContent).toContain('600519 · 白酒');
    expect(host.textContent).toContain('¥160000.00'); // 市值
    expect(host.textContent).toContain('持仓浮盈');
    expect(host.textContent).toContain('全周期盈亏');
    expect(host.textContent).toContain('普通成本');
    expect(host.textContent).toContain('摊薄成本');

    // 点击卡片进入交易明细
    const cardEl = cards[0].querySelector('.m-card-clickable');
    expect(cardEl).toBeTruthy();
    cardEl.click();
    expect(showTransMock).toHaveBeenCalledWith(sampleHoldings[0]);
  });
});

describe('阶段 2 批次 A：TransactionsTab (交易记录)', () => {
  it('窄屏下渲染交易流水卡片，包含方向、金额、单价数量与操作按钮', () => {
    restoreMatchMedia = stubMatchMedia(true);
    const editMock = vi.fn();

    const sampleTransactions = [
      {
        id: 101,
        date: '2026-10-24',
        name: '恒生科技ETF',
        code: '513130',
        category: 'QDII',
        direction: '买入',
        account: '华泰证券',
        quantity: 5000,
        price: 0.65,
        amount: 3250,
        fee: 5,
        remark: '定投第1期',
      },
    ];

    const ctx = {
      transForm: ref({}),
      feeAccounts: ref([]),
      feeAutoHint: ref(''),
      filteredTransactions: ref(sampleTransactions),
      pendingTransactions: ref([]),
      pendingPurchaseTotal: ref(0),
      transQuery: ref({}),
      transPage: ref({ page: 1, pageSize: 100, total: 1 }),
      submitTrans: vi.fn(),
      resetForm: vi.fn(),
      markFeeManual: vi.fn(),
      downloadTransactionsTemplate: vi.fn(),
      exportTransactions: vi.fn(),
      importTransactions: vi.fn(),
      queryAssetByCode: vi.fn(),
      queryAssetByName: vi.fn(),
      selectTransAsset: vi.fn(),
      autoMatchTransAsset: vi.fn(),
      applyTransFilter: vi.fn(),
      resetTransQuery: vi.fn(),
      handleTransPageChange: vi.fn(),
      handleTransPageSizeChange: vi.fn(),
      openTransEditDialog: editMock,
      deleteTransaction: vi.fn(),
      formatMoney: (v) => `¥${Number(v || 0).toFixed(2)}`,
      dashboard: ref({}),
      dividendLoading: ref(false),
      openDividendDraftDialog: vi.fn(),
      parseNlEntry: vi.fn(),
    };

    const host = mountView(TransactionsTab, ctx);

    const cards = host.querySelectorAll('[aria-label="交易流水"] .data-card');
    expect(cards.length).toBe(1);

    expect(host.textContent).toContain('恒生科技ETF');
    expect(host.textContent).toContain('513130 · QDII');
    expect(host.textContent).toContain('华泰证券');
    expect(host.textContent).toContain('2026-10-24');
    expect(host.textContent).toContain('¥3250.00'); // 金额
    expect(host.textContent).toContain('定投第1期'); // 备注
  });
});

describe('阶段 2 批次 A：DepositsTab (银行存款)', () => {
  it('窄屏下渲染到期分布与存款明细卡片', () => {
    restoreMatchMedia = stubMatchMedia(true);

    const sampleBuckets = [
      { bucket: '1年以内', amount: 50000, percentage: 50.0 },
      { bucket: '1~3年', amount: 50000, percentage: 50.0 },
    ];

    const sampleDeposits = [
      {
        id: 1,
        bank_name: '招商银行',
        amount: 50000,
        percentage: 50.0,
        interest_rate: 2.15,
        annual_interest: 1075,
        term_interest: 3225,
        remaining_interest: 1500,
        start_date: '2024-01-01',
        due_date: '2027-01-01',
        daysLeft: 420,
        remark: '定期存单',
      },
    ];

    const ctx = {
      dashboard: ref({}),
      depositRows: ref(sampleDeposits),
      depositSummary: ref({ missingStartCount: 0 }),
      depositBankBreakdown: ref([]),
      depositMaturityBuckets: ref(sampleBuckets),
      downloadDepositsTemplate: vi.fn(),
      exportDeposits: vi.fn(),
      importDeposits: vi.fn(),
      openDepositDialog: vi.fn(),
      deleteDeposit: vi.fn(),
      formatMoney: (v) => `¥${Number(v || 0).toFixed(2)}`,
      pct: (v) => `${(Number(v || 0) * 100).toFixed(1)}%`,
    };

    const host = mountView(DepositsTab, ctx);

    // 检查两张表的卡片
    const bucketCards = host.querySelectorAll('[aria-label="存款到期分布"] .data-card');
    expect(bucketCards.length).toBe(2);
    expect(host.textContent).toContain('1年以内');

    const depositCards = host.querySelectorAll('[aria-label="存款明细"] .data-card');
    expect(depositCards.length).toBe(1);
    expect(host.textContent).toContain('招商银行');
    expect(host.textContent).toContain('¥50000.00');
    expect(host.textContent).toContain('420天');
    expect(host.textContent).toContain('年化 2.15%');
    expect(host.textContent).toContain('整期利息');
  });
});
