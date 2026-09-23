/**
 * 「收益与快照」合并页（原「收益分析」+「资产快照」）的回归测试。
 *
 * 分析组从 5 页收敛到 3 页时把「资产快照」并进了「收益分析」（改名「收益与快照」）：
 * 页面上「每日收益」区块之后多了一块「快照明细」（<SnapshotPanel />）。这条测试钉住
 * 四件事：
 *  1) 两块标题同时出现在同一页；
 *  2) 快照明细里确实有快照历史表与人工对账表单；
 *  3) 两个数据源都真的渲染出来（perfTimeline → 每日收益行、snapshots → 快照历史行）；
 *  4) 快照明细在 DOM 里排在「每日收益」之后。
 *
 * 注：生产构建里 el-* 由 unplugin-vue-components 自动注册，测试环境没有这层，
 * 所以下面用桩组件代替（只关心本页自己的结构、事件和插槽里的数据）。
 */
import { describe, it, expect, vi } from 'vitest';
import { createApp, h, provide, inject, computed, ref } from 'vue';
import PerformanceTab from '../src/views/PerformanceTab.vue';
import { APP_CTX_KEY } from '../src/composables/useAppCtx.js';

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

// 透传桩：渲染默认插槽、保留 attrs（@click 会挂成原生监听，组件 props 也留在属性上）
const passthrough = (name) => ({
  name,
  setup(_, { slots, attrs }) {
    return () => h('div', attrs, slots.default ? slots.default() : []);
  },
});

// el-table / el-table-column：列插槽依赖 row scope，用 provide/inject 把当前表的 data 传下去
const TABLE_ROWS = Symbol('table-rows');
const ElTableStub = {
  name: 'ElTable',
  props: { data: { type: Array, default: () => [] } },
  setup(props, { slots, attrs }) {
    provide(TABLE_ROWS, computed(() => props.data || []));
    return () => h('div', attrs, slots.default ? slots.default() : []);
  },
};
const ElTableColumnStub = {
  name: 'ElTableColumn',
  props: { label: { type: String, default: '' } },
  setup(props, { slots }) {
    const rows = inject(TABLE_ROWS, null);
    return () => h(
      'div',
      { class: 'stub-col', 'data-label': props.label },
      (rows ? rows.value : []).map((row, $index) => h(
        'div',
        { class: 'stub-cell' },
        slots.default ? slots.default({ row, $index }) : [],
      )),
    );
  },
};

const STUBS = {
  ElCard: passthrough('ElCard'),
  ElAlert: passthrough('ElAlert'),
  ElButton: passthrough('ElButton'),
  ElTag: passthrough('ElTag'),
  ElTooltip: passthrough('ElTooltip'),
  ElRadioGroup: passthrough('ElRadioGroup'),
  ElRadioButton: passthrough('ElRadioButton'),
  ElForm: passthrough('ElForm'),
  ElFormItem: passthrough('ElFormItem'),
  ElRow: passthrough('ElRow'),
  ElCol: passthrough('ElCol'),
  ElSelect: passthrough('ElSelect'),
  ElOption: passthrough('ElOption'),
  ElInput: passthrough('ElInput'),
  ElInputNumber: passthrough('ElInputNumber'),
  ElDatePicker: passthrough('ElDatePicker'),
  ElTable: ElTableStub,
  ElTableColumn: ElTableColumnStub,
};

const formatMoney = (v, d = 2, s = false) => (
  v == null ? '—' : `${s && Number(v) >= 0 ? '+' : ''}${Number(v).toFixed(d)}`
);

// 「每日收益」行由 perfDailyRows 渲染，价格新鲜度字段（price_stale / unpriced_count）来自 perfTimeline。
const TIMELINE_ROW = {
  date: '2026-03-06', total_assets: 101000, price_stale: 1, price_date: '2026-02-27', unpriced_count: 3,
};
const DAILY_ROW = {
  date: '2026-03-06', prevDate: '2026-03-05', change: -2000, pct: -1.94, assets: 101000, daysGap: 1, isGap: false,
};
// 「快照历史记录」行来自 snapshots
const SNAPSHOT_ROW = {
  date: '2026-03-05', total_assets: 987654.32, total_market_value: 654321, bank_balance: 200000,
  securities_cash: 30000, pending_purchase: 0, total_profit: 1234.5, lifetime_profit: 4321, holdings_count: 7,
};

function mountMerged({ timeline = [TIMELINE_ROW], dailyRows = [DAILY_ROW], snapshotRows = [SNAPSHOT_ROW] } = {}) {
  const ctx = {
    formatMoney,
    pct: (a, b) => (b ? `${(Number(a || 0) / Number(b) * 100).toFixed(1)}%` : '—'),
    // ---------------- PerformanceTab（收益与快照） ----------------
    perfSummary: ref({ total_assets: 101000, total_gain: 1000, flow_count: 1, xirr_status: 'ok' }),
    perfTimeline: ref(timeline),
    perfContribution: ref([]),
    perfFlows: ref([]),
    perfStory: ref(null),
    perfLoading: ref(false),
    perfFlowForm: ref({ date: '', flow_type: '投入', amount: 0, source: '', remark: '' }),
    hasPerfFlows: ref(true),
    perfStoryToneType: ref('info'),
    perfPrimaryCards: ref([]),
    perfSecondaryCards: ref([]),
    fetchPerformance: vi.fn(async () => ({ failed: 0 })),
    addPerfFlow: vi.fn(async () => {}),
    updatePerfFlow: vi.fn(async () => {}),
    deletePerfFlow: vi.fn(async () => {}),
    loadPerfFlowSuggestions: vi.fn(async () => ({ drafts: [] })),
    applyPerfFlowSuggestion: vi.fn(),
    showTransactions: vi.fn(),
    goTab: vi.fn(),
    perfRiskMetrics: ref(null),
    perfContributionSummary: ref({ topWinners: [], topLosers: [], byCategory: [] }),
    perfWindowCards: ref([]),
    selectPerfWindow: vi.fn(),
    perfDailyRows: ref(dailyRows),
    perfTodayRow: ref(null),
    perfDailyStats: ref({
      count: 1, total: -2000, upDays: 0, downDays: 1,
      best: null, worst: { date: '2026-03-06', change: -2000 },
    }),
    perfLatestSnapshotDate: ref('2026-03-06'),
    todaySnapshotDone: ref(true), // 让收盘提示不出现，避免干扰文本断言
    createSnapshot: vi.fn(async () => ({})),
    // ---------------- SnapshotPanel（原资产快照页） ----------------
    snapshots: ref(snapshotRows),
    snapshotRange: ref([]),
    snapshotMetrics: ref([{ key: 'latest', label: '最新总资产', value: '987654.32' }]),
    snapshotChangeRows: ref([]),
    snapshotInsights: ref([]),
    snapshotSummary: ref(null),
    snapshotLoading: ref(false),
    reconcileData: ref(null),
    reconcileForm: ref({ date: '', amount: 0, note: '' }),
    reconcileSaving: ref(false),
    fetchSnapshots: vi.fn(async () => {}),
    exportSnapshots: vi.fn(async () => {}),
    compactSnapshots: vi.fn(async () => {}),
    saveReconcile: vi.fn(async () => {}),
  };
  const host = document.createElement('div');
  const App = { setup() { provide(APP_CTX_KEY, ctx); return () => h(PerformanceTab); } };
  const app = createApp(App);
  for (const [name, comp] of Object.entries(STUBS)) app.component(name, comp);
  app.directive('loading', {});
  app.mount(host);
  return { host, app, ctx };
}

const flush = () => new Promise((r) => setTimeout(r, 20));

/** 页面里所有区块标题（含「快照明细」那一行） */
const sectionTitles = (host) => [...host.querySelectorAll('.perf-section-title')]
  .filter((el) => el.children.length === 0)
  .map((el) => el.textContent.trim());
const sectionTitleEl = (host, label) => [...host.querySelectorAll('.perf-section-title')]
  .find((el) => el.textContent.trim() === label);

describe('「收益与快照」合并页：每日收益 + 快照明细', () => {
  it('「每日收益」与「快照明细」两块标题同时出现在同一页', async () => {
    const { host, app } = mountMerged();
    await flush();

    const titles = sectionTitles(host);
    expect(titles).toContain('每日收益');
    expect(titles).toContain('快照明细');

    // 每日收益仍在原来的卡片里，快照明细是新增的区块（内含 SnapshotPanel）
    expect(host.querySelector('.perf-daily-card')).toBeTruthy();
    expect(sectionTitleEl(host, '每日收益')).toBeTruthy();
    expect(host.querySelector('.snapshot-panel')).toBeTruthy();
    app.unmount();
  });

  it('快照明细里带着快照历史表与人工对账表单', async () => {
    const { host, app } = mountMerged();
    await flush();

    const panel = host.querySelector('.snapshot-panel');
    expect(panel).toBeTruthy();
    // 快照历史表（11 列，带 aria-label）
    expect(panel.querySelector('[aria-label="快照历史记录"]')).toBeTruthy();
    expect(panel.innerHTML).toContain('快照历史记录');
    // 人工对账表单
    expect(panel.innerHTML).toContain('人工对账（实盘核对）');
    expect(panel.textContent).toContain('保存实盘对账');
    // 区间变化明细与资产结构饼图容器也还在
    expect(panel.querySelector('[aria-label="区间变化明细"]')).toBeTruthy();
    expect(panel.querySelector('#snapshotStructureChart')).toBeTruthy();
    // 决策 D4：总资产趋势图已删，不残留容器
    expect(panel.querySelector('#snapshotTrendChart')).toBeNull();
    app.unmount();
  });

  it('两个数据源都渲染：perfTimeline 的每日收益行 + snapshots 的快照历史行', async () => {
    const { host, app } = mountMerged();
    await flush();

    // 每日收益：行来自 perfDailyRows，价格新鲜度字段（价格未更新 / 缺价 N 只）只有 perfTimeline 里有
    const dailyCard = host.querySelector('.perf-daily-card');
    expect(dailyCard.textContent).toContain('2026-03-06');
    expect(dailyCard.textContent).toContain(formatMoney(DAILY_ROW.change, 2, true));
    expect(dailyCard.textContent).toContain('价格未更新');
    expect(dailyCard.textContent).toContain('缺价 3 只');
    expect(dailyCard.querySelector('[aria-label="每日收益"] [data-label="当日盈亏"]').querySelectorAll('.stub-cell').length).toBe(1);

    // 快照历史：行来自 snapshots；「总资产」列已去掉（与每日收益的「期末总资产」同一个数，
    // 一页里不重复展示），所以这里断言它**不存在**，同时该行的其它金额仍然渲染
    const panel = host.querySelector('.snapshot-panel');
    expect(panel.querySelector('[aria-label="快照历史记录"] [data-label="总资产"]')).toBeNull();
    const mvCol = panel.querySelector('[aria-label="快照历史记录"] [data-label="投资市值"]');
    expect(mvCol.querySelectorAll('.stub-cell').length).toBe(1);
    expect(mvCol.textContent).toContain(formatMoney(SNAPSHOT_ROW.total_market_value));
    expect(panel.textContent).toContain(formatMoney(SNAPSHOT_ROW.bank_balance));
    expect(panel.textContent).toContain(formatMoney(SNAPSHOT_ROW.securities_cash));
    // 那天的总资产仍然能在同一页看到（每日收益表的「期末总资产」）
    expect(dailyCard.textContent).toContain(formatMoney(DAILY_ROW.assets));
    app.unmount();
  });

  it('快照明细排在「每日收益」之后（DOM 顺序）', async () => {
    const { host, app } = mountMerged();
    await flush();

    const dailyTitle = sectionTitleEl(host, '每日收益');
    const snapshotTitle = sectionTitleEl(host, '快照明细');
    const titles = sectionTitles(host);
    expect(titles.indexOf('每日收益')).toBeLessThan(titles.indexOf('快照明细'));
    // 「每日收益」标题在「快照明细」之前
    expect(dailyTitle.compareDocumentPosition(snapshotTitle) & Node.DOCUMENT_POSITION_FOLLOWING)
      .toBeTruthy();
    expect(dailyTitle.compareDocumentPosition(snapshotTitle) & Node.DOCUMENT_POSITION_PRECEDING)
      .toBeFalsy();
    app.unmount();
  });
});

/**
 * 区块顺序：结论在前、明细在后。快照明细是逐日明细表，要排在结论类区块之后。
 */
describe('「收益与快照」区块顺序：结论在前、明细在后', () => {
  const steps = (host) => [
    { label: '核心指标', el: host.querySelector('.ledger-metrics') },
    { label: '收益尺', el: host.querySelector('.perf-window-strip') },
    { label: '最近 7 个交易日', el: host.querySelector('.perf-month-card') },
    { label: '每日收益', el: host.querySelector('.perf-daily-card') },
    { label: '快照明细', el: host.querySelector('.snapshot-panel') },
    {
      label: '风险一览',
      el: [...host.querySelectorAll('.perf-contrib-title')].find((e) => e.textContent.includes('风险一览')),
    },
    { label: '组合资金流水', el: host.querySelector('#perf-flow-section') },
  ];

  it('核心指标 → 收益尺 → 最近 7 日 → 每日收益 → 快照明细 → 风险 → 流水', async () => {
    const { host, app } = mountMerged();
    await flush();

    const list = steps(host);
    expect(list.filter((s) => !s.el).map((s) => s.label), '这些区块没渲染出来').toEqual([]);
    for (let i = 1; i < list.length; i += 1) {
      const prev = list[i - 1];
      const cur = list[i];
      const pos = prev.el.compareDocumentPosition(cur.el);
      expect(
        Boolean(pos & Node.DOCUMENT_POSITION_FOLLOWING),
        `「${prev.label}」应排在「${cur.label}」之前`,
      ).toBe(true);
    }
    app.unmount();
  });
});
