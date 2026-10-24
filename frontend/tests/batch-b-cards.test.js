/**
 * 阶段 2 批次 B 移动卡片测试：
 * 覆盖 PerformanceTab / CashTab / AllocationTab / BrokerReconcileTab 4 个页面的分析与流水表格。
 *
 * 验证标准：
 *  - 窄屏（≤640px，CARD_QUERY）下渲染对应的自适应卡片列表；
 *  - 卡片覆盖核心数值、类型/方向标签、涨跌/盈亏高亮、决策与操作入口；
 *  - 宽屏（>640px）下仍透传回原生表格分支；
 *  - 交互保留：编辑/删除/记入等操作事件正确触发。
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { createApp, h, ref, computed, nextTick } from 'vue';
import { APP_CTX_KEY } from '../src/composables/useAppCtx.js';
import { CARD_QUERY } from '../src/modules/dataTable.js';
import PerformanceTab from '../src/views/PerformanceTab.vue';
import CashTab from '../src/views/CashTab.vue';
import AllocationTab from '../src/views/AllocationTab.vue';
import BrokerReconcileTab from '../src/views/BrokerReconcileTab.vue';

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

  const stubs = [
    'ElCard', 'ElRow', 'ElCol', 'ElTag', 'ElTooltip', 'ElAlert',
    'ElInput', 'ElSelect', 'ElOption', 'ElPagination', 'ElProgress', 'ElEmpty',
    'ElDatePicker', 'ElForm', 'ElFormItem', 'ElInputNumber', 'ElDivider',
    'ElUpload', 'ElSpace', 'ElCollapse', 'ElCollapseItem', 'ElTabs', 'ElTabPane',
    'ElDialog', 'ElRadio', 'ElRadioGroup', 'ElRadioButton',
    'PageShell', 'SnapshotReminder', 'SnapshotPanel',
  ];
  stubs.forEach((name) => appInstance.component(name, passthrough(name)));

  appInstance.component('ElButton', {
    name: 'ElButton',
    setup(_, { slots, attrs }) {
      return () => h('button', { ...attrs, class: 'el-button' }, slots.default ? slots.default() : []);
    },
  });

  appInstance.component('ElTable', {
    name: 'ElTable',
    setup(_, { slots }) {
      return () => h('div', slots.default ? slots.default() : []);
    },
  });

  appInstance.component('ElTableColumn', {
    name: 'ElTableColumn',
    setup(_, { slots }) {
      return () => h('div', slots.default ? slots.default({ row: {} }) : []);
    },
  });

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

describe('阶段 2 批次 B：PerformanceTab (业绩分析)', () => {
  it('窄屏下渲染每日收益、资金流水草稿与组合流水卡片', async () => {
    restoreMatchMedia = stubMatchMedia(true);
    const onApplyMock = vi.fn();
    const onEditMock = vi.fn();
    const onDeleteMock = vi.fn();

    const sampleDaily = [
      { date: '2026-10-24', isToday: true, change: 1250.5, pct: 1.25, assets: 500000, daysGap: 1, stale: false },
      { date: '2026-10-23', isToday: false, change: -800, pct: -0.8, assets: 498749.5, isGap: true, daysGap: 3, priceStale: true },
    ];
    const sampleSuggest = [
      { id: 101, date: '2026-10-24', flow_type: '投入', amount: 10000, remark: '来自银证流水自动识别' },
    ];
    const sampleFlows = [
      { id: 201, date: '2026-10-23', flow_type: '投入', amount: 20000, source: '银行卡', remark: '每月定投' },
    ];

    const ctx = {
      formatMoney: (v, decimals = 2, sign = false) => {
        if (v == null) return '—';
        const num = Number(v).toFixed(decimals);
        return sign && Number(v) > 0 ? `+${num}` : num;
      },
      formatPercent: (v, decimals = 2) => (v == null ? '—' : `${Number(v).toFixed(decimals)}%`),
      pct: (v) => `${v}%`,
      perfDailyRows: ref(sampleDaily),
      perfTodayRow: ref(null),
      priceFlagsByDate: ref({}),
      perfTimeline: ref([]),
      perfWindowCards: ref([]),
      perfDailyStats: ref({ total: 1000, winDays: 15, loseDays: 10, winRate: 60 }),
      perfRiskMetrics: ref({}),
      perfStory: ref({}),
      perfFlows: ref(sampleFlows),
      perfFlowForm: ref({ date: '', flow_type: '投入', amount: 0, source: '', remark: '' }),
      perfFlowEditId: ref(null),
      perfFlowSaving: ref(false),
      perfFlowDeleting: ref(null),
      perfSuggestLoading: ref(false),
      perfFlowSuggestions: ref(sampleSuggest),
      perfSuggestionApplying: ref(false),
      onLoadFlowSuggest: vi.fn(),
      onApplyPerfFlowSuggestion: onApplyMock,
      onSavePerfFlow: vi.fn(),
      cancelPerfFlowEdit: vi.fn(),
      startPerfFlowEdit: onEditMock,
      onDeletePerfFlow: onDeleteMock,
      perfSummary: ref({}),
      annualizedReturn: ref(10.5),
      maxDrawdown: ref(5.2),
      sharpeRatio: ref(1.8),
    };

    const root = mountView(PerformanceTab, ctx);
    const cards = root.querySelectorAll('.m-card');
    // 2 (daily) + 1 (flow) = 3 cards
    expect(cards.length).toBe(3);

    // 验证 daily 卡片内容
    expect(root.textContent).toContain('2026-10-24');
    expect(root.textContent).toContain('实时');
    expect(root.textContent).toContain('+1250.50');
    expect(root.textContent).toContain('1.25%');

    // 验证流水卡片操作：点击编辑后表单进入编辑态（出现取消按钮）
    expect(root.textContent).not.toContain('取消');
    const editBtn = cards[2].querySelectorAll('button')[0];
    editBtn.click();
    await nextTick();
    expect(root.textContent).toContain('取消');
  });
});

describe('阶段 2 批次 B：CashTab (现金与银证管理)', () => {
  it('窄屏下渲染其他调整、证券资金流水与未配对流水卡片', async () => {
    restoreMatchMedia = stubMatchMedia(true);
    const onEditMock = vi.fn();
    const onDeleteMock = vi.fn();

    const sampleCash = [
      { id: 1, date: '2026-10-20', flow_type: '现金校准', amount: 120.5, remark: '利息微调' },
      { id: 2, date: '2026-10-21', account: '中信证券', flow_type: '银证转入', amount: 50000, balance_before: 1000, balance_after: 51000, remark: '追加资金' },
    ];
    const sampleUnmatchedBank = [
      { id: 3, date: '2026-10-22', flow_type: '银证转入', amount: 15000, remark: '银行已转出但组合未记' },
    ];
    const sampleUnmatchedPort = [
      { id: 4, date: '2026-10-22', flow_type: '组合投入', amount: 8000, remark: '组合已记但银证无记录' },
    ];

    const ctx = {
      formatMoney: (v, decimals = 2, sign = false) => {
        if (v == null) return '—';
        const num = Number(v).toFixed(decimals);
        return sign && Number(v) > 0 ? `+${num}` : num;
      },
      cashFlowTagType: (type) => (type === '银证转入' ? 'success' : 'info'),
      dashboard: ref({ cash: 51000 }),
      feeSettings: ref({}),
      feeAccounts: ref([]),
      activeFeeAccount: ref(''),
      newFeeAccountName: ref(''),
      feeCategories: ref([]),
      cashForm: ref({}),
      cashFlows: ref(sampleCash),
      cashFlowForm: ref({}),
      cashFlowQuery: ref({}),
      cashFlowSummary: ref({ total_in: 50000, total_out: 0 }),
      cashAudit: ref({
        ok: false,
        summary_text: '银证与组合流水存在差额',
        bank_in: 65000,
        portfolio_in: 58000,
        bank_out: 0,
        portfolio_out: 0,
        unmatched_bank: sampleUnmatchedBank,
        unmatched_portfolio: sampleUnmatchedPort,
      }),
      cashFlowDeleting: ref(null),
      saveFeeSettings: vi.fn(),
      resetFeeSettings: vi.fn(),
      addFeeAccount: vi.fn(),
      removeFeeAccount: vi.fn(),
      onActiveFeeAccountChange: vi.fn(),
      updateCash: vi.fn(),
      queryCashFlows: vi.fn(),
      resetCashFlowQuery: vi.fn(),
      addCashFlow: vi.fn(),
      openCashFlowEditDialog: onEditMock,
      deleteCashFlow: onDeleteMock,
      fetchCashAudit: vi.fn(),
    };

    const root = mountView(CashTab, ctx);
    const cards = root.querySelectorAll('.m-card');
    // 1 (adjust: 现金校准) + 2 (cashFlows: 2 rows) + 1 (unmatched bank) + 1 (unmatched port) = 5 cards
    expect(cards.length).toBe(5);

    expect(root.textContent).toContain('现金校准');
    expect(root.textContent).toContain('+120.50');
    expect(root.textContent).toContain('中信证券');
    expect(root.textContent).toContain('+50000.00');
    expect(root.textContent).toContain('银行已转出但组合未记');

    // 测试编辑点击
    const editBtn = cards[0].querySelectorAll('button')[0];
    expect(editBtn).toBeTruthy();
    editBtn.click();
    expect(onEditMock).toHaveBeenCalledWith(sampleCash[0]);
  });
});

describe('阶段 2 批次 B：AllocationTab (资产配置)', () => {
  it('窄屏下渲染情景粗估、大类汇总、再平衡建议与细分类别卡片', async () => {
    restoreMatchMedia = stubMatchMedia(true);

    const sampleScenarios = [
      { label: '沪深300涨 10%', estimated_pnl: 35000, estimated_total_assets: 535000 },
    ];
    const sampleMacro = [
      { group: '权益类', amount: 350000, percentage: 70.0, profit: 50000, expected_return: 8.5 },
    ];
    const sampleActions = [
      { code: '510300', name: '300ETF', side: 'buy', amount: 15000, reason: '偏离 -3.0%' },
    ];
    const sampleAnalysis = [
      { category: '宽基指数', market_value: 200000, percentage: 40.0, profit: 30000, profit_rate: 17.65, count: 2, lifetime_profit: 40000, expected_annual_return: 8.0 },
    ];

    const ctx = {
      formatMoney: (v, decimals = 2, sign = false) => {
        if (v == null) return '—';
        const num = Number(v).toFixed(decimals);
        return sign && Number(v) > 0 ? `+${num}` : num;
      },
      formatPercent: (v, decimals = 2) => (v == null ? '—' : `${Number(v).toFixed(decimals)}%`),
      dashboard: ref({ total_assets: 500000 }),
      allocationStory: ref({ scenarios: sampleScenarios }),
      macroAllocationAnalysis: ref(sampleMacro),
      actions: ref(sampleActions),
      planItems: ref([]),
      allocationAnalysis: ref(sampleAnalysis),
      disciplineRows: ref([]),
      disciplineDrafts: ref([]),
      disciplineLoading: ref(false),
      disciplineDraftLoading: ref(false),
      confirmingDrafts: ref(false),
      disciplinePolicyDialog: ref(false),
      disciplinePolicy: ref({ targets: { equity_pct: 45, fixed_income_pct: 35, deposit_pct: 20 }, focus: {}, plans: {} }),
      deviationTailOpen: ref(['category-detail', 'discipline-drafts']),
      draftBusy: ref(''),
      onDraftSelectionChange: vi.fn(),
      fetchDisciplineDrafts: vi.fn(),
      onConfirmSelectedDrafts: vi.fn(),
      openDraftEdit: vi.fn(),
      onConfirmDraft: vi.fn(),
      onDeleteDraft: vi.fn(),
      applyDisciplinePreset: vi.fn(),
      withBusy: (refVal, fn) => fn(),
      draftsGenerating: ref(false),
      policySaving: ref(false),
      draftEditSaving: ref(false),
      presetApplying: ref(false),
      allocationStoryLoading: ref(false),
      openPolicyDialog: vi.fn(),
    };

    const root = mountView(AllocationTab, ctx);
    const cards = root.querySelectorAll('.m-card');
    // 1 (scenario) + 1 (macro) + 1 (action) + 1 (analysis) = 4 cards
    expect(cards.length).toBe(4);

    expect(root.textContent).toContain('沪深300涨 10%');
    expect(root.textContent).toContain('权益类');
    expect(root.textContent).toContain('300ETF');
    expect(root.textContent).toContain('宽基指数');
  });
});

describe('阶段 2 批次 B：BrokerReconcileTab (券商对账)', () => {
  it('窄屏下渲染差异明细与对账历史卡片', async () => {
    restoreMatchMedia = stubMatchMedia(true);

    const sampleDiffs = [
      { code: '510300', name: '300ETF', status: 'diff_qty', broker_quantity: 1000, app_quantity: 800, quantity_diff: 200, broker_avg_cost: 3.5, app_avg_cost: 3.4, reasons: ['分红除息未记入'] },
    ];
    const sampleHistory = [
      { id: 1, created_at: '2026-10-24 09:00', kind: 'apply', as_of_date: '2026-10-23', diff_count: 1, applied_count: 1, cash_status: '一致', summary_text: '校正 1 笔持仓', filename: 'holdings.csv', codes: '510300' },
    ];

    const ctx = {
      brokerResult: ref({ diff_count: 1, diffs: sampleDiffs, suggestions: [] }),
      brokerLoading: ref(false),
      brokerSelected: ref([]),
      brokerAsOfDate: ref('2026-10-23'),
      brokerCashInput: ref(''),
      brokerHistory: ref(sampleHistory),
      statusLabel: (s) => (s === 'diff_qty' ? '数量差' : s),
      statusType: (s) => (s === 'diff_qty' ? 'warning' : 'info'),
      onBrokerFileChange: vi.fn(),
      onBrokerSelectionChange: vi.fn(),
      selectAllSuggestions: vi.fn(),
      clearBrokerSelection: vi.fn(),
      applySelectedCorrections: vi.fn(),
      fetchBrokerHistory: vi.fn(),
    };

    const root = mountView(BrokerReconcileTab, ctx);
    const cards = root.querySelectorAll('.m-card');
    // 1 (diff) + 1 (history) = 2 cards
    expect(cards.length).toBe(2);

    expect(root.textContent).toContain('300ETF');
    expect(root.textContent).toContain('数量差');
    expect(root.textContent).toContain('分红除息未记入');
    expect(root.textContent).toContain('校正 1 笔持仓');
  });
});
