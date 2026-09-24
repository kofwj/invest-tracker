/**
 * 「收益与快照」页里「近 7 个交易日」简报的取数与文案回归测试。
 *
 * 这张简报住在走势卡的 `.perf-brief` 第一行（第二行是近 30 日），取数只有一处：
 * perfDailyRows 的前 7 行 + summarizeDailyPnl，不新增接口。
 * 它只包含有快照的日子，所以标签写「近 7 个交易日」而不是「最近 7 天」。
 * 「本月 / 今年」只在收益尺（分段控件）显示，这张简报不重复。
 *
 * 注：生产构建里 el-* 由 unplugin-vue-components 自动注册，测试环境没有这层，
 * 所以用桩组件代替（只关心本页自己的结构、事件）。
 */
import { describe, it, expect, vi } from 'vitest';
import { createApp, h, provide, inject, computed, ref } from 'vue';
import { APP_CTX_KEY } from '../src/composables/useAppCtx.js';
import PerformanceTab from '../src/views/PerformanceTab.vue';
import { summarizeDailyPnl } from '../src/utils/index.js';

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

const passthrough = (name) => ({
  name,
  setup(_, { slots, attrs }) {
    return () => h('div', attrs, slots.default ? slots.default() : []);
  },
});

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
  ElSelect: passthrough('ElSelect'),
  ElOption: passthrough('ElOption'),
  ElInput: passthrough('ElInput'),
  ElInputNumber: passthrough('ElInputNumber'),
  ElDatePicker: passthrough('ElDatePicker'),
  ElTable: ElTableStub,
  ElTableColumn: ElTableColumnStub,
};

const flush = () => new Promise((r) => setTimeout(r, 20));

const formatMoney = (v, d = 2, s = false) => (
  v == null ? '—' : `${s && Number(v) >= 0 ? '+' : ''}${Number(v).toFixed(d)}`
);

/** 新 → 旧；最后一条（2026-02-25）是第 8 个交易日，不该进「最近 7 个交易日」 */
const DAILY_ROWS = [
  { date: '2026-03-06', prevDate: '2026-03-05', change: -2000, pct: -1.94, assets: 101000, daysGap: 1, isGap: false },
  { date: '2026-03-05', prevDate: '2026-03-04', change: 800, pct: 0.8, assets: 103000, daysGap: 1, isGap: false },
  { date: '2026-03-04', prevDate: '2026-03-03', change: 120, pct: 0.12, assets: 102200, daysGap: 1, isGap: false },
  { date: '2026-03-03', prevDate: '2026-03-02', change: -50, pct: -0.05, assets: 102080, daysGap: 1, isGap: false },
  { date: '2026-03-02', prevDate: '2026-02-27', change: 430, pct: 0.42, assets: 102130, daysGap: 3, isGap: true },
  { date: '2026-02-27', prevDate: '2026-02-26', change: -310, pct: -0.3, assets: 101700, daysGap: 1, isGap: false },
  { date: '2026-02-26', prevDate: '2026-02-25', change: 90, pct: 0.09, assets: 102010, daysGap: 1, isGap: false },
  { date: '2026-02-25', prevDate: '2026-02-24', change: 99999, pct: 99, assets: 101920, daysGap: 1, isGap: false },
];

const MONTH_CARD = {
  key: 'month', label: '本月', gain: 3456.78, gainPct: 3.2,
  active: false, tone: 'up', disabled: false, staleDays: null, stale: false, baseDate: '2026-03-02',
};

function mountTab({ dailyRows = [], windowCards = [] } = {}) {
  const ctx = {
    formatMoney,
    pct: (v) => `${v}`,
    perfSummary: ref({ total_assets: 101000, total_gain: 1000, flow_count: 1, xirr_status: 'ok' }),
    perfTimeline: ref([]),
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
    perfWindowCards: ref(windowCards),
    selectPerfWindow: vi.fn(),
    perfDailyRows: ref(dailyRows),
    perfTodayRow: ref(null),
    perfDailyStats: ref(summarizeDailyPnl(dailyRows, 30)),
    perfLatestSnapshotDate: ref(dailyRows.length ? dailyRows[0].date : null),
    todaySnapshotDone: ref(true), // 这张卡和收盘提示无关，直接让提示不出现
    createSnapshot: vi.fn(async () => ({})),
  };
  const host = document.createElement('div');
  const App = { setup() { provide(APP_CTX_KEY, ctx); return () => h(PerformanceTab); } };
  const app = createApp(App);
  for (const [name, comp] of Object.entries(STUBS)) app.component(name, comp);
  app.directive('loading', {});
  app.mount(host);
  return { host, app, ctx };
}

/** 走势卡里的两行简报 */
const briefGrid = (host, i = 0) => [...host.querySelectorAll('.perf-daily-card .perf-brief')][i];
const briefCell = (host, label) => [...briefGrid(host).querySelectorAll('.perf-brief-cell')]
  .find((c) => c.querySelector('.k').textContent.trim() === label);
const briefValue = (host, label) => briefCell(host, label).querySelector('.v');

describe('「收益与快照」里的近 7 个交易日简报', () => {
  it('月窗口的值不再在这一页重复：没有「本月累计」，收益尺上仍有「本月」', async () => {
    const { host, app } = mountTab({ dailyRows: DAILY_ROWS, windowCards: [{ key: 'today', label: '今天', gain: 1, gainPct: 1 }, MONTH_CARD] });
    await flush();

    expect(host.textContent).not.toContain('本月累计');
    expect(briefGrid(host).textContent).not.toContain(formatMoney(MONTH_CARD.gain, 2, true));
    // 收益尺（分段控件）上仍然有「本月」这张
    expect(host.querySelector('.perf-window-strip').textContent).toContain('本月');
    app.unmount();
  });

  it('近 7 个交易日 = perfDailyRows 前 7 行：累计 / 涨跌天数 / 最好最差一致', async () => {
    const expected = summarizeDailyPnl(DAILY_ROWS, 7);
    const { host, app } = mountTab({ dailyRows: DAILY_ROWS, windowCards: [MONTH_CARD] });
    await flush();

    expect(briefValue(host, '近 7 个交易日累计').textContent).toContain(formatMoney(expected.total, 2, true));
    expect(briefValue(host, '涨 / 跌 天数').textContent.trim()).toBe(`${expected.upDays} / ${expected.downDays}`);
    expect(briefValue(host, '最好一天').textContent).toContain(`${expected.best.date.slice(5)} ${formatMoney(expected.best.change, 2, true)}`);
    expect(briefValue(host, '最差一天').textContent).toContain(`${expected.worst.date.slice(5)} ${formatMoney(expected.worst.change, 2, true)}`);

    // 第 8 个交易日（2026-02-25，+99999）既没进累计也没当上「最好一天」
    expect(briefGrid(host).textContent).not.toContain('02-25');
    expect(briefGrid(host).textContent).not.toContain(formatMoney(99999, 2, true));
    expect(expected.best.date).not.toBe('2026-02-25');
    app.unmount();
  });

  it('文案不承诺自然日：写「近 7 个交易日」，口径说明挂在 title 上', async () => {
    const { host, app } = mountTab({ dailyRows: DAILY_ROWS, windowCards: [MONTH_CARD] });
    await flush();

    expect(host.textContent).toContain('近 7 个交易日累计');
    expect(host.textContent).not.toContain('最近 7 天');
    // 「按已有快照统计」这层说明还在（悬停可见）
    expect(briefValue(host, '近 7 个交易日累计').getAttribute('title')).toContain('已有快照');
    app.unmount();
  });

  it('近 7 日那一行排在近 30 日那一行之前', async () => {
    const { host, app } = mountTab({ dailyRows: DAILY_ROWS, windowCards: [MONTH_CARD] });
    await flush();

    const labels = [0, 1].map((i) => briefGrid(host, i).querySelector('.k').textContent.trim());
    expect(labels).toEqual(['近 7 个交易日累计', '近 30 日累计']);
    expect(briefGrid(host, 0).compareDocumentPosition(briefGrid(host, 1)) & Node.DOCUMENT_POSITION_FOLLOWING)
      .toBeTruthy();
    app.unmount();
  });

  it('没有快照时不渲染这些数字，只显示空态（不编数、不崩）', async () => {
    const { host, app } = mountTab({ dailyRows: [], windowCards: [] });
    await flush();

    expect(host.querySelector('.perf-daily-card')).toBeTruthy();
    expect(host.querySelectorAll('.perf-daily-card .perf-brief-cell').length).toBe(0);
    expect(host.querySelector('.perf-daily-card').innerHTML).toContain('还没有可比较的两天快照');
    app.unmount();
  });

  it('最好 / 最差是两个格子，各自的值够短（合回一张长串就红）', async () => {
    const expected = summarizeDailyPnl(DAILY_ROWS, 7);
    const { host, app } = mountTab({ dailyRows: DAILY_ROWS, windowCards: [MONTH_CARD] });
    await flush();

    const best = briefValue(host, '最好一天');
    const worst = briefValue(host, '最差一天');
    expect(best.textContent.trim()).toBe(`${expected.best.date.slice(5)} ${formatMoney(expected.best.change, 2, true)}`);
    expect(worst.textContent.trim()).toBe(`${expected.worst.date.slice(5)} ${formatMoney(expected.worst.change, 2, true)}`);
    // 值必须短：合成一行是 35 个字符，会被 text-overflow: ellipsis 切掉后半句
    expect(best.textContent.trim().length).toBeLessThanOrEqual(20);
    expect(worst.textContent.trim().length).toBeLessThanOrEqual(20);
    expect(best.classList.contains('perf-up')).toBe(true);
    expect(worst.classList.contains('perf-down')).toBe(true);
    app.unmount();
  });

  it('连续下跌时「最好一天」也是负数，用 down 配色（不写死 up）', async () => {
    const downRows = [
      { date: '2026-03-04', prevDate: '2026-03-03', change: -300, pct: -0.3, assets: 99000, daysGap: 1, isGap: false },
      { date: '2026-03-03', prevDate: '2026-03-02', change: -100, pct: -0.1, assets: 99300, daysGap: 1, isGap: false },
    ];
    const { host, app } = mountTab({ dailyRows: downRows, windowCards: [MONTH_CARD] });
    await flush();

    const best = briefValue(host, '最好一天');
    expect(best.textContent).toContain('03-03');
    expect(best.classList.contains('perf-down')).toBe(true);
    app.unmount();
  });
});
