/**
 * 「月度概览」卡的取数与文案回归测试。
 *
 * 这张卡不新增任何接口，取数只有两处：
 *  - 本月累计：收益尺里 key === 'month' 的那张卡（口径与收益尺一致，不另算）；
 *  - 最近 7 个交易日：perfDailyRows 的前 7 行 + summarizeDailyPnl。
 * perfDailyRows 只包含"有快照的日子"，所以卡片上必须如实写「最近 7 个交易日」，
 * 不能承诺自然日——这里连文案一起钉住。
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

const monthCardText = (host) => host.querySelector('.perf-month-card').textContent;

describe('月度概览卡', () => {
  it('本月累计取收益尺的 month 窗口', async () => {
    const { host, app } = mountTab({ dailyRows: DAILY_ROWS, windowCards: [{ key: 'today', label: '今天', gain: 1, gainPct: 1 }, MONTH_CARD] });
    await flush();

    const text = monthCardText(host);
    expect(text).toContain('本月累计');
    expect(text).toContain(formatMoney(MONTH_CARD.gain, 2, true)); // +3456.78
    // 今天窗口的值不该出现在月度卡里
    expect(text).not.toContain('+1.00 ');
    app.unmount();
  });

  it('最近 7 个交易日 = perfDailyRows 前 7 行：累计 / 涨跌天数 / 最好最差一致', async () => {
    const expected = summarizeDailyPnl(DAILY_ROWS, 7);
    const { host, app } = mountTab({ dailyRows: DAILY_ROWS, windowCards: [MONTH_CARD] });
    await flush();

    const text = monthCardText(host);
    expect(text).toContain('最近 7 个交易日累计');
    expect(text).toContain(formatMoney(expected.total, 2, true)); // -920.00
    expect(text).toContain(`${expected.upDays} / ${expected.downDays}`); // 4 / 3
    expect(text).toContain(`${expected.best.date.slice(5)} ${formatMoney(expected.best.change, 2, true)}`); // 03-05 +800.00
    expect(text).toContain(`${expected.worst.date.slice(5)} ${formatMoney(expected.worst.change, 2, true)}`); // 03-06 -2000.00

    // 第 8 个交易日（2026-02-25，+99999）既没进累计也没当上"最好一天"
    expect(text).not.toContain('02-25');
    expect(text).not.toContain(formatMoney(99999, 2, true));
    expect(expected.best.date).not.toBe('2026-02-25');
    app.unmount();
  });

  it('文案如实说明是"按已有快照的最近 7 个交易日"，不承诺自然日', async () => {
    const { host, app } = mountTab({ dailyRows: DAILY_ROWS, windowCards: [MONTH_CARD] });
    await flush();

    const text = monthCardText(host);
    expect(text).toContain('最近 7 个交易日');
    expect(text).toContain('已有快照');
    expect(text).not.toContain('最近 7 天');
    app.unmount();
  });

  it('卡的位置在「每日收益」区块上方', async () => {
    const { host, app } = mountTab({ dailyRows: DAILY_ROWS, windowCards: [MONTH_CARD] });
    await flush();

    const blocks = [...host.querySelectorAll('.perf-month-card, .perf-daily-card')];
    expect(blocks.length).toBe(2);
    expect(blocks[0].className).toContain('perf-month-card');
    expect(blocks[1].className).toContain('perf-daily-card');
    app.unmount();
  });

  it('没有月窗口 / 没有快照时显示 —，卡片仍然在', async () => {
    const { host, app } = mountTab({ dailyRows: [], windowCards: [] });
    await flush();

    expect(host.querySelector('.perf-month-card')).toBeTruthy();
    expect(monthCardText(host)).toContain('本月累计');
    expect(monthCardText(host)).toContain('—');
    app.unmount();
  });
});
