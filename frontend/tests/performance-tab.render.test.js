/**
 * 「每日收益」区块的渲染回归测试。
 *
 * 这页以前只靠 main.js 里 watch(activeTab) 触发加载，直接打开 /performance 会一直
 * 空着；新加的每日收益卡片还依赖 perfDailyRows 才会挂出图表节点。这里用 jsdom 真
 * 挂一次组件，保证卡片、图表容器、空状态和"基准过期"提示都在。
 *
 * 注：生产构建里 el-* 由 unplugin-vue-components 自动注册，测试环境没有这层，
 * 所以下面用桩组件代替（只关心本页自己的结构，不测 Element Plus 行为）。
 */
import { describe, it, expect, vi } from 'vitest';
import { createApp, h, provide, inject, computed, ref } from 'vue';
import PerformanceTab from '../src/views/PerformanceTab.vue';
import { APP_CTX_KEY } from '../src/composables/useAppCtx.js';

const chartCalls = [];
vi.mock('../src/charts/index.js', () => ({
  renderDailyPnlChartView: (rows) => { chartCalls.push(rows); return true; },
  waitForChartDom: async () => true,
  renderAllocationChartsView: () => true,
  renderSnapshotChartsView: () => true,
  renderOverviewWeekChartView: () => true,
  renderKlineChartView: () => {},
  analyzeKlineTrend: () => ({ points: [] }),
  resizeAllCharts: () => {},
  readTheme: () => ({}),
}));

// 透传桩：渲染默认插槽，保留 class，让本页自己的 DOM 结构可断言
const passthrough = (name) => ({
  name,
  setup(_, { slots, attrs }) {
    return () => h('div', attrs, slots.default ? slots.default() : []);
  },
});
// el-table-column 的插槽依赖 el-table 提供的 row scope，测试里不渲染以免噪音
// el-table / el-table-column：列插槽依赖行作用域，用 provide/inject 把当前表的 data 传下去，
// 否则单元格内容根本不会渲染，断言「实时 / 未收盘」这类文案就没意义。
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
  ElCollapse: passthrough('ElCollapse'),
  ElCollapseItem: passthrough('ElCollapseItem'),
  ElSelect: passthrough('ElSelect'),
  ElOption: passthrough('ElOption'),
  ElInput: passthrough('ElInput'),
  ElInputNumber: passthrough('ElInputNumber'),
  ElDatePicker: passthrough('ElDatePicker'),
  ElTable: ElTableStub,
  ElTableColumn: ElTableColumnStub,
};

const timeline = [
  { date: '2026-03-02', total_assets: 100000, daily_change: null, daily_pct: null, prev_date: null, days_gap: null },
  { date: '2026-03-03', total_assets: 103000, daily_change: 3000, daily_pct: 3, prev_date: '2026-03-02', days_gap: 1 },
  { date: '2026-03-06', total_assets: 101000, daily_change: -2000, daily_pct: -1.94, prev_date: '2026-03-03', days_gap: 3 },
];

function mountTab({ dailyRows = [], summaryLoaded = true, todayRow = null } = {}) {
  const ctx = {
    formatMoney: (v, d = 2, s = false) => (v == null ? '—' : `${s && Number(v) >= 0 ? '+' : ''}${Number(v).toFixed(d)}`),
    pct: (v) => `${v}`,
    perfSummary: ref(summaryLoaded ? { total_assets: 101000, total_gain: 1000, flow_count: 2, xirr_status: 'ok' } : null),
    perfTimeline: ref(dailyRows.length ? timeline : []),
    perfContribution: ref([]),
    perfFlows: ref([{ id: 1, date: '2026-03-01', flow_type: '投入', amount: 100000 }]),
    perfStory: ref({ headline: '测试', tone: 'neutral', category_contrib: [] }),
    perfLoading: ref(false),
    perfFlowForm: ref({ date: '', flow_type: '投入', amount: 0, source: '', remark: '' }),
    hasPerfFlows: ref(true),
    perfStoryToneType: ref('info'),
    perfPrimaryCards: ref([]),
    perfSecondaryCards: ref([]),
    fetchPerformance: vi.fn(async () => ({ failed: 0 })),
    addPerfFlow: vi.fn(), updatePerfFlow: vi.fn(), deletePerfFlow: vi.fn(),
    loadPerfFlowSuggestions: vi.fn(async () => ({ drafts: [] })),
    applyPerfFlowSuggestion: vi.fn(),
    showTransactions: vi.fn(), goTab: vi.fn(),
    perfRiskMetrics: ref(null),
    perfContributionSummary: ref({ topWinners: [], topLosers: [], byCategory: [] }),
    perfWindowCards: ref([
      { key: 'today', label: '今天', gain: 0, gainPct: 0, active: true, tone: 'neutral', disabled: false, staleDays: 52, stale: true, baseDate: '2026-08-02' },
    ]),
    selectPerfWindow: vi.fn(),
    perfDailyRows: ref(dailyRows),
    perfTodayRow: ref(todayRow),
    perfDailyStats: ref({
      count: 2, total: 1000, upDays: 1, downDays: 1,
      best: { date: '2026-03-03', change: 3000 }, worst: { date: '2026-03-06', change: -2000 },
    }),
    perfLatestSnapshotDate: ref('2026-03-06'),
    todaySnapshotDone: ref(false),
    createSnapshot: vi.fn(async () => ({})),
  };
  const host = document.createElement('div');
  const App = { setup() { provide(APP_CTX_KEY, ctx); return () => h(PerformanceTab); } };
  const app = createApp(App);
  for (const [name, comp] of Object.entries(STUBS)) app.component(name, comp);
  app.mount(host);
  return { host, app, ctx };
}

const flush = () => new Promise((r) => setTimeout(r, 20));

describe('PerformanceTab 每日收益区块', () => {
  it('renders the card, the chart container and the summary cards', async () => {
    chartCalls.length = 0;
    const { host, app } = mountTab({ dailyRows: [{ date: '2026-03-06', change: -2000, pct: -1.94, assets: 101000, daysGap: 3, isGap: true }] });
    await flush();

    expect(host.querySelector('.perf-daily-card')).toBeTruthy();
    expect(host.querySelector('#dailyPnlChart')).toBeTruthy();
    expect(host.querySelector('[aria-label="每日收益"]')).toBeTruthy();
    expect(host.textContent).toContain('近 30 日累计');
    expect(host.textContent).toContain('涨 / 跌 天数');
    expect(host.textContent).toContain('1 / 1');
    // 图表被真正调用，拿到的是升序数据（柱状图从左到右）
    expect(chartCalls.length).toBeGreaterThan(0);
    expect(chartCalls[chartCalls.length - 1].map((r) => r.date)).toEqual(['2026-03-06']);
    app.unmount();
  });

  it('shows an empty state instead of a broken chart when there are no two snapshots yet', async () => {
    chartCalls.length = 0;
    const { host, app } = mountTab({ dailyRows: [] });
    await flush();

    // el-alert 的 title 是 prop（桩组件渲染成属性），所以查 innerHTML
    expect(host.querySelector('.perf-daily-card').innerHTML).toContain('还没有可比较的两天快照');
    expect(host.querySelector('#dailyPnlChart')).toBeNull();
    // 今天还没快照 → 给出「记录今日快照」入口
    expect(host.textContent).toContain('记录今日快照');
    app.unmount();
  });

  it('marks a stale "今天" window with its base date instead of pretending it is today', async () => {
    const { host, app } = mountTab({ dailyRows: [{ date: '2026-03-06', change: -2000, pct: -1.94, assets: 101000, daysGap: 3, isGap: true }] });
    await flush();

    // 陈旧基准写在收益尺副行里（「今天 · +0.00% · 基准 08-02（52 天前）」），不能假装是今天
    const sub = host.querySelector('.perf-seg-sub');
    expect(sub).toBeTruthy();
    expect(sub.textContent).toContain('08-02');
    expect(sub.textContent).toContain('52');
    app.unmount();
  });

  it('loads performance data on mount so a direct /performance visit is not blank', async () => {
    const { app, ctx } = mountTab({ dailyRows: [], summaryLoaded: false });
    await flush();
    expect(ctx.fetchPerformance).toHaveBeenCalled();
    app.unmount();
  });
});


describe('PerformanceTab 每日收益里的「今日（未收盘）」行', () => {
  const todayRow = {
    date: '2026-03-07',
    prevDate: '2026-03-06',
    change: 1234.5,
    pct: 1.23,
    assets: 102234.5,
    daysGap: 1,
    isGap: false,
    isToday: true,
    baseDate: '2026-03-06',
    stale: false,
  };
  const snapshotRow = { date: '2026-03-06', change: -2000, pct: -1.94, assets: 101000, daysGap: 3, isGap: true };

  it('把今日行放在最前面，并标明「实时 / 未收盘」', async () => {
    chartCalls.length = 0;
    const { host, app } = mountTab({ dailyRows: [snapshotRow], todayRow });
    await flush();

    const text = host.textContent;
    expect(text).toContain('2026-03-07');
    expect(text).toContain('实时');
    expect(text).toContain('未收盘');
    expect(text).toContain('2026-03-06'); // 昨天的快照行仍在

    // 图表按日期升序：今天必须在最后一根
    const last = chartCalls[chartCalls.length - 1];
    expect(last[last.length - 1].date).toBe('2026-03-07');
    expect(last[last.length - 1].isToday).toBe(true);
    expect(last[0].date).toBe('2026-03-06');
    app.unmount();
  });

  it('基准快照不是上一交易日时，用警告色提示实际跨度', async () => {
    const { host, app } = mountTab({
      dailyRows: [snapshotRow],
      todayRow: { ...todayRow, stale: true, baseDate: '2026-08-02', daysGap: 52 },
    });
    await flush();
    const tooltips = host.querySelectorAll('[content]');
    const hasCrossDayHint = [...tooltips].some((n) => (n.getAttribute('content') || '').includes('跨了 52 天'));
    expect(hasCrossDayHint).toBe(true);
    app.unmount();
  });

  it('拿不到今天窗口时不伪造今日行', async () => {
    const { host, app } = mountTab({ dailyRows: [snapshotRow], todayRow: null });
    await flush();
    expect(host.textContent).not.toContain('实时');
    expect(host.textContent).not.toContain('未收盘');
    app.unmount();
  });
});
