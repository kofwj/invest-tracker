/**
 * 收盘后「今天还没记快照」提示的回归测试。
 *
 * 为什么要有这条提示：每日收益靠服务器 16:40 的定时快照，cron 停了、或当天价格源挂了
 * 被后端闸门拦下，序列就断一天，而界面上原来完全看不出来。
 *
 * 覆盖：
 *  - isAfterMarketClose 纯函数的边界（15:29 / 15:30 / 16:00）；
 *  - 收盘前的页面不渲染提示、收盘后未记才渲染、已记不渲染；
 *  - 「补记今日快照」复用 409 → 确认（用后端 detail）→ 带 force 重试的流程，取消则不重试；
 *  - 两个页面（总览 / 收益分析）都真的挂了这个组件。
 *
 * 注：生产构建里 el-* 由 unplugin-vue-components 自动注册，测试环境没有这层，
 * 所以用桩组件代替（只关心本页自己的结构、事件）。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { createApp, h, provide, inject, computed, ref } from 'vue';
import { APP_CTX_KEY } from '../src/composables/useAppCtx.js';
import SnapshotReminder from '../src/components/SnapshotReminder.vue';
import OverviewTab from '../src/views/OverviewTab.vue';
import PerformanceTab from '../src/views/PerformanceTab.vue';
import { isAfterMarketClose, MARKET_CLOSE_MINUTES } from '../src/utils/marketTime.js';

const elMock = vi.hoisted(() => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  messageBox: { confirm: vi.fn(), alert: vi.fn() },
}));

vi.mock('element-plus', () => ({
  ElMessage: elMock.message,
  ElMessageBox: elMock.messageBox,
  ElLoading: { service: () => ({ close: () => {} }) },
  ElNotification: elMock.message.info,
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

function mountView(view, ctx, props = undefined) {
  const host = document.createElement('div');
  const App = { setup() { provide(APP_CTX_KEY, ctx); return () => h(view, props); } };
  const app = createApp(App);
  for (const [name, comp] of Object.entries(STUBS)) app.component(name, comp);
  app.directive('loading', {});
  app.mount(host);
  return { host, app };
}

const flush = () => new Promise((r) => setTimeout(r, 20));

function findButton(root, label) {
  const nodes = [...root.querySelectorAll('div')].filter((el) => el.textContent.trim() === label);
  return nodes.find((el) => el.children.length === 0) || nodes[0] || null;
}
const click = (el) => el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));

const formatMoney = (v, d = 2, s = false) => (
  v == null ? '—' : `${s && Number(v) >= 0 ? '+' : ''}${Number(v).toFixed(d)}`
);

beforeEach(() => {
  vi.clearAllMocks();
  elMock.messageBox.confirm.mockResolvedValue('confirm');
});

afterEach(() => {
  vi.useRealTimers();
});

/** 固定上海时间（只假 Date，不动 setTimeout），与 CI 的系统时区无关。 */
function shanghaiDate(hours, minutes) {
  const hour = String(hours).padStart(2, '0');
  const minute = String(minutes).padStart(2, '0');
  return new Date(`2026-03-06T${hour}:${minute}:00+08:00`);
}

function freezeAt(hours, minutes) {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(shanghaiDate(hours, minutes));
}

// ---------------------------------------------------------------- 纯函数

describe('isAfterMarketClose 纯函数', () => {
  it('收盘线是 15:30', () => {
    expect(MARKET_CLOSE_MINUTES).toBe(15 * 60 + 30);
  });

  it('14:00 → false，15:29 → false', () => {
    expect(isAfterMarketClose(shanghaiDate(14, 0))).toBe(false);
    expect(isAfterMarketClose(shanghaiDate(15, 29))).toBe(false);
  });

  it('15:30 → true（边界含等于），16:00 → true', () => {
    expect(isAfterMarketClose(shanghaiDate(15, 30))).toBe(true);
    expect(isAfterMarketClose(shanghaiDate(16, 0))).toBe(true);
  });

  it('早盘 09:35 → false，深夜 23:59 → true', () => {
    expect(isAfterMarketClose(shanghaiDate(9, 35))).toBe(false);
    expect(isAfterMarketClose(shanghaiDate(23, 59))).toBe(true);
  });
});

// ------------------------------------------------------------------ 组件

function mountReminder({ now = null, todaySnapshotDone = false, createSnapshot = vi.fn(async () => ({})) } = {}) {
  const ctx = { todaySnapshotDone: ref(todaySnapshotDone), createSnapshot };
  const { host, app } = mountView(SnapshotReminder, ctx, { now: now || undefined });
  return { host, app, ctx };
}

describe('SnapshotReminder 渲染时机', () => {
  it('收盘前（14:00）不渲染提示', async () => {
    const { host, app } = mountReminder({ now: shanghaiDate(14, 0), todaySnapshotDone: false });
    await flush();
    expect(host.querySelector('.snapshot-reminder')).toBeNull();
    app.unmount();
  });

  it('15:29 还不渲染，15:30 起渲染（边界）', async () => {
    const before = mountReminder({ now: shanghaiDate(15, 29), todaySnapshotDone: false });
    await flush();
    expect(before.host.querySelector('.snapshot-reminder')).toBeNull();
    before.app.unmount();

    const after = mountReminder({ now: shanghaiDate(15, 30), todaySnapshotDone: false });
    await flush();
    expect(after.host.querySelector('.snapshot-reminder')).toBeTruthy();
    after.app.unmount();
  });

  it('收盘后还没记快照 → 提示 + 补记按钮', async () => {
    const { host, app } = mountReminder({ now: shanghaiDate(16, 0), todaySnapshotDone: false });
    await flush();
    const box = host.querySelector('.snapshot-reminder');
    expect(box).toBeTruthy();
    expect(box.textContent).toContain('今天还没记快照');
    expect(box.textContent).toContain('每日收益会少一天');
    expect(findButton(host, '补记今日快照')).toBeTruthy();
    app.unmount();
  });

  it('已经记过今天快照时不渲染', async () => {
    const { host, app } = mountReminder({ now: shanghaiDate(16, 0), todaySnapshotDone: true });
    await flush();
    expect(host.querySelector('.snapshot-reminder')).toBeNull();
    app.unmount();
  });

  it('todaySnapshotDone 从 false 变 true 时提示消失', async () => {
    const createSnapshot = vi.fn(async () => ({}));
    const { host, app, ctx } = mountReminder({ now: shanghaiDate(16, 0), createSnapshot });
    await flush();
    expect(host.querySelector('.snapshot-reminder')).toBeTruthy();

    ctx.todaySnapshotDone.value = true;
    await flush();
    expect(host.querySelector('.snapshot-reminder')).toBeNull();
    app.unmount();
  });
});

// ---------------------------------------------------------- 补记的 409 闸门

describe('SnapshotReminder 补记今日快照的 409 闸门', () => {
  const err409 = () => Object.assign(new Error('价格未更新'), {
    response: { status: 409, data: { detail: '最新价基准日期是 2026-03-05，不是今天，确认后仍要记录吗？' } },
  });

  it('409 → 弹确认（用后端 detail）→ 带 force 重试一次', async () => {
    const err = err409();
    const createSnapshot = vi.fn(async (force) => {
      if (force !== true) throw err;
      return { data: { action: 'created' } };
    });
    const { host, app } = mountReminder({
      now: shanghaiDate(16, 0),
      todaySnapshotDone: false,
      createSnapshot,
    });
    await flush();

    click(findButton(host, '补记今日快照'));
    await flush();

    expect(createSnapshot).toHaveBeenCalledTimes(2);
    expect(createSnapshot.mock.calls[0]).toEqual([false]);
    expect(createSnapshot.mock.calls[1]).toEqual([true]);
    expect(elMock.messageBox.confirm).toHaveBeenCalledTimes(1);
    expect(elMock.messageBox.confirm.mock.calls[0][0]).toContain('2026-03-05');
    expect(elMock.messageBox.confirm.mock.calls[0][1]).toBe('价格未更新');
    app.unmount();
  });

  it('用户取消确认时不带 force 重试', async () => {
    elMock.messageBox.confirm.mockRejectedValue('cancel');
    const err = err409();
    const createSnapshot = vi.fn(async (force) => {
      if (force !== true) throw err;
      return {};
    });
    const { host, app } = mountReminder({
      now: shanghaiDate(16, 0),
      todaySnapshotDone: false,
      createSnapshot,
    });
    await flush();

    click(findButton(host, '补记今日快照'));
    await flush();

    expect(createSnapshot).toHaveBeenCalledTimes(1);
    expect(createSnapshot.mock.calls.every((c) => c[0] !== true)).toBe(true);
    app.unmount();
  });

  it('连点两次只发一轮首请求（按钮 loading 期间不再是空窗）', async () => {
    let resolveFirst;
    const createSnapshot = vi.fn(() => new Promise((r) => { resolveFirst = r; }));
    const { host, app } = mountReminder({
      now: shanghaiDate(16, 0),
      todaySnapshotDone: false,
      createSnapshot,
    });
    await flush();

    const btn = findButton(host, '补记今日快照');
    click(btn);
    click(btn);
    expect(createSnapshot).toHaveBeenCalledTimes(1);

    await flush();
    expect(btn.getAttribute('loading')).toBe('true');
    resolveFirst({});
    await flush();
    expect(btn.getAttribute('loading')).toBe('false');
    app.unmount();
  });

  it('非 409 错误只 console.error，不弹确认框', async () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const createSnapshot = vi.fn(async () => { throw new Error('boom'); });
    const { host, app } = mountReminder({
      now: shanghaiDate(16, 0),
      todaySnapshotDone: false,
      createSnapshot,
    });
    await flush();

    click(findButton(host, '补记今日快照'));
    await flush();

    expect(createSnapshot).toHaveBeenCalledTimes(1);
    expect(elMock.messageBox.confirm).not.toHaveBeenCalled();
    expect(spy).toHaveBeenCalled();
    spy.mockRestore();
    app.unmount();
  });
});

// ------------------------------------------------------------ 两个页面的挂载

const perfCtx = (overrides = {}) => ({
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
  perfWindowCards: ref([]),
  selectPerfWindow: vi.fn(),
  perfDailyRows: ref([]),
  perfTodayRow: ref(null),
  perfDailyStats: ref({ count: 0, total: 0, upDays: 0, downDays: 0, best: null, worst: null }),
  perfLatestSnapshotDate: ref(null),
  todaySnapshotDone: ref(false),
  createSnapshot: vi.fn(async () => ({})),
  ...overrides,
});

const overviewCtx = (overrides = {}) => ({
  dashboard: ref({ total_assets: 101000, total_profit: 1000, securities_cash: 500, bank_balance: 200 }),
  holdings: ref([]),
  snapshots: ref([]),
  maintenanceStatus: ref({ backup_count: 1 }),
  todaySnapshotDone: ref(false),
  latestPriceStatusText: ref(''),
  latestBackupText: ref(''),
  pendingTransactions: ref([]),
  goPendingTransactions: vi.fn(),
  marketSignals: ref({ today_contrib_estimate: 0 }),
  refreshMarket: vi.fn(async () => {}),
  fetchSnapshots: vi.fn(async () => {}),
  showTransactions: vi.fn(),
  formatMoney,
  holdingFloatProfit: () => 0,
  goTab: vi.fn(),
  allocationSummary: ref({ equityRatio: 60, defensiveRatio: 40 }),
  portfolioExpectedReturn: ref(5),
  resolvedTheme: ref('light'),
  createSnapshot: vi.fn(async () => ({})),
  ...overrides,
});

describe('收盘提示挂在两个页面顶部', () => {
  it('收益分析页：收盘后未记快照 → 页面里有提示', async () => {
    freezeAt(16, 0);
    const { host, app } = mountView(PerformanceTab, perfCtx());
    await flush();
    expect(host.querySelector('.snapshot-reminder')).toBeTruthy();
    expect(host.textContent).toContain('今天还没记快照');
    app.unmount();
  });

  it('收益分析页：已记快照 → 没有提示', async () => {
    freezeAt(16, 0);
    const { host, app } = mountView(PerformanceTab, perfCtx({ todaySnapshotDone: ref(true) }));
    await flush();
    expect(host.querySelector('.snapshot-reminder')).toBeNull();
    app.unmount();
  });

  it('总览页：收盘后未记快照 → 页面里有提示', async () => {
    freezeAt(16, 0);
    const { host, app } = mountView(OverviewTab, overviewCtx());
    await flush();
    expect(host.querySelector('.snapshot-reminder')).toBeTruthy();
    app.unmount();
  });

  it('总览页：收盘前不提示', async () => {
    freezeAt(11, 0);
    const { host, app } = mountView(OverviewTab, overviewCtx());
    await flush();
    expect(host.querySelector('.snapshot-reminder')).toBeNull();
    app.unmount();
  });
});
