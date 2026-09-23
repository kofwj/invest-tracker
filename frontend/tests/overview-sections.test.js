/**
 * 首页重排成固定三段的回归测试。
 *
 * 改之前第一排是「总资产 / 当日参考（盘中粗估，不入账）/ 持仓浮盈 / 现金+存款」：
 * 账本口径和盘中估算并排，最容易看错；而"今天赚了多少"根本不在第一排。
 * 现在固定成 ① 今天 → ② 资产与仓位 → ③ 明细与入口，待办单独聚合。
 *
 * 覆盖：
 *  - 三段都在，且顺序固定（① 在今天盈亏之前，②③ 依次在后）；
 *  - 「今日盈亏」用 performance 模块的 perfTodayPnl：为 null 时显示「—」+ 原因，不编数；
 *    注意**不能**用 perfTodayRow（那个在「今天已有正式快照」时返回 null，是给收益分析表补行用的）——
 *    之前首页用错了它，导致每天快照一写、首页今日盈亏就永远是「—」。
 *  - 「当日参考」不在第一段，落在第二段并标出"盘中粗估，不入账"；
 *  - 待办：无待办显示「今天没有待办」，todaySnapshotDone === false 时出现「今日快照」条目且可跳转。
 *
 * 注：生产构建里 el-* 由 unplugin-vue-components 自动注册，测试环境没有这层，
 * 所以用桩组件代替（只关心本页自己的结构、文案与跳转）。
 */
import { describe, it, expect, vi } from 'vitest';
import { createApp, h, provide, inject, computed, ref } from 'vue';
import OverviewTab from '../src/views/OverviewTab.vue';
import { APP_CTX_KEY } from '../src/composables/useAppCtx.js';

// OverviewTab 顶部挂着 SnapshotReminder（真的），它会 import element-plus
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), alert: vi.fn() },
  ElLoading: { service: () => ({ close: () => {} }) },
  ElNotification: vi.fn(),
}));

// 本页用动态 import 画近半月曲线
vi.mock('../src/charts/index.js', () => ({
  renderOverviewWeekChartView: () => true,
  waitForChartDom: async () => true,
}));

const passthrough = (name) => ({
  name,
  setup(_, { slots, attrs }) {
    return () => h('div', attrs, slots.default ? slots.default() : []);
  },
});

// el-table / el-table-column：列插槽依赖行作用域，用 provide/inject 把当前表的 data 传下去
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
  ElButton: passthrough('ElButton'),
  ElTable: ElTableStub,
  ElTableColumn: ElTableColumnStub,
};

const formatMoney = (v, d = 2, s = false) => (
  v == null ? '—' : `${s && Number(v) >= 0 ? '+' : ''}${Number(v).toFixed(d)}`
);

const TODAY_ROW = {
  date: '2026-03-07',
  prevDate: '2026-03-06',
  change: 1234.5,
  pct: 1.23,
  daysGap: 1,
  baseDate: '2026-03-06',
  stale: false,
  closed: false, // 默认：盘中口径（还没收盘 / 还没写快照）
};

const flatDashboard = (extra = {}) => ({
  total_assets: 101000,
  total_profit: 1000,
  securities_cash: 500,
  bank_balance: 200,
  latest_snapshot_date: '2026-03-06',
  ...extra,
});

/** ctx 的 key 与 OverviewTab 里 useAppCtx() 的解构保持一致 */
function mountOverview(overrides = {}) {
  const ctx = {
    dashboard: ref(flatDashboard()),
    holdings: ref([]),
    snapshots: ref([]),
    maintenanceStatus: ref({ backup_count: 1 }),
    // 默认「今天已记快照」：这样默认 ctx 下没有待办，便于断言空待办文案
    todaySnapshotDone: ref(true),
    latestPriceStatusText: ref('最新价 2026-03-06'),
    latestBackupText: ref('2026-03-06 18:00'),
    pendingTransactions: ref([]),
    goPendingTransactions: vi.fn(),
    marketSignals: ref({ today_contrib_estimate: 120 }),
    refreshMarket: vi.fn(async () => {}),
    fetchSnapshots: vi.fn(async () => {}),
    showTransactions: vi.fn(),
    formatMoney,
    holdingFloatProfit: () => 0,
    goTab: vi.fn(),
    allocationSummary: ref({ equityRatio: 60, defensiveRatio: 40 }),
    portfolioExpectedReturn: ref(5),
    resolvedTheme: ref('light'),
    perfSummary: ref({ total_assets: 101000, total_gain: 1000 }),
    perfTodayPnl: ref({ ...TODAY_ROW }),
    perfWindowCards: ref([
      { key: 'month', label: '本月', gain: 3200, gainPct: 3.2, tone: 'up', stale: false, baseDate: '2026-03-01' },
      { key: 'ytd', label: '今年', gain: -800, gainPct: -0.8, tone: 'down', stale: true, staleDays: 40, baseDate: '2026-01-02' },
    ]),
    perfLatestSnapshotDate: ref('2026-03-06'),
    createSnapshot: vi.fn(async () => ({})),
    ...overrides,
  };
  const host = document.createElement('div');
  const App = { setup() { provide(APP_CTX_KEY, ctx); return () => h(OverviewTab); } };
  const app = createApp(App);
  for (const [name, comp] of Object.entries(STUBS)) app.component(name, comp);
  app.directive('loading', {});
  app.mount(host);
  return { host, app, ctx };
}

const flush = () => new Promise((r) => setTimeout(r, 20));
const section = (host, name) => host.querySelector(`[data-section="${name}"]`);
const todoItems = (host) => [...section(host, 'today').querySelectorAll('.ov-todo-item')];

describe('OverviewTab 固定三段', () => {
  it('三段都在，顺序是 ① 今天 → ② 资产与仓位 → ③ 明细与入口，今日盈亏在第一段里', async () => {
    const { host, app } = mountOverview();
    await flush();

    const names = [...host.querySelectorAll('.ov-section')].map((el) => el.getAttribute('data-section'));
    expect(names).toEqual(['today', 'assets', 'detail']);

    const text = host.textContent;
    const iToday = text.indexOf('① 今天');
    const iAssets = text.indexOf('② 资产与仓位');
    const iDetail = text.indexOf('③ 明细与入口');
    expect(iToday).toBeGreaterThan(-1);
    expect(iAssets).toBeGreaterThan(iToday);
    expect(iDetail).toBeGreaterThan(iAssets);

    // 「今日盈亏」在 ① 今天里，而不是被账本卡片挤到后面
    const iPnl = text.indexOf('今日盈亏');
    expect(iPnl).toBeGreaterThan(iToday);
    expect(iPnl).toBeLessThan(iAssets);
    expect(section(host, 'today').textContent).toContain('本月');
    expect(section(host, 'today').textContent).toContain('今年');
    app.unmount();
  });

  it('第 ③ 段收着曲线、持仓速览、快捷入口和同步/备份状态', async () => {
    const { host, app } = mountOverview();
    await flush();
    const detail = section(host, 'detail');
    expect(detail.querySelector('#overviewWeekChart')).toBeTruthy();
    expect(detail.textContent).toContain('持仓速览');
    expect(detail.textContent).toContain('今天可做');
    expect(detail.textContent).toContain('最新价同步');
    expect(detail.textContent).toContain('最近备份');
    app.unmount();
  });
});

describe('OverviewTab 今日盈亏口径', () => {
  it('perfTodayPnl 为 null 时显示「—」并说明原因，不编数', async () => {
    const { host, app } = mountOverview({ perfTodayPnl: ref(null), todaySnapshotDone: ref(true) });
    await flush();

    const today = section(host, 'today');
    const value = today.querySelector('.ov-metric.main .ov-metric-value');
    expect(value.textContent.trim()).toBe('—');
    // 说明原因，而不是留个空格
    expect(today.textContent).toContain('今日快照已记录');
    expect(today.textContent).toContain('2026-03-06');
    app.unmount();
  });

  it('收益分析数据还没加载时说清是「未加载」，不拿盘中估算冒充今日盈亏', async () => {
    const { host, app } = mountOverview({
      perfSummary: ref(null),
      perfTodayPnl: ref(null),
      perfWindowCards: ref([]),
    });
    await flush();

    const today = section(host, 'today');
    expect(today.querySelector('.ov-metric.main .ov-metric-value').textContent.trim()).toBe('—');
    expect(today.textContent).toContain('收益数据未加载');
    // 本月 / 今年同样不编数
    expect(today.querySelectorAll('.ov-metric-value')[1].textContent.trim()).toBe('—');
    app.unmount();
  });

  it('今天已有正式快照（已收盘）时照样显示数字——快照写完不能让首页变「—」', async () => {
    const { host, app } = mountOverview({
      perfTodayPnl: ref({ ...TODAY_ROW, closed: true }),
      todaySnapshotDone: ref(true),
      perfLatestSnapshotDate: ref('2026-03-07'),
    });
    await flush();

    const card = section(host, 'today').querySelector('.ov-metric.main');
    expect(card.querySelector('.ov-metric-value').textContent).toContain('1234.50');
    expect(card.textContent).toContain('+1.23%');
    expect(card.textContent).toContain('已收盘');
    app.unmount();
  });

  it('perfTodayPnl 有值时显示金额与涨跌幅', async () => {
    const { host, app } = mountOverview();
    await flush();

    const card = section(host, 'today').querySelector('.ov-metric.main');
    expect(card.querySelector('.ov-metric-value').textContent).toContain('1234.50');
    expect(card.textContent).toContain('+1.23%');
    expect(card.textContent).toContain('盘中口径');
    expect(card.textContent).toContain('2026-03-06'); // 说清基准是哪天
    app.unmount();
  });
});

describe('OverviewTab 「当日参考」的位置', () => {
  it('不再出现在第一段，落在第二段并标明盘中粗估、不入账', async () => {
    const { host, app } = mountOverview();
    await flush();

    expect(section(host, 'today').textContent).not.toContain('当日参考');

    const assets = section(host, 'assets');
    expect(assets.textContent).toContain('当日参考');
    expect(assets.textContent).toContain('盘中粗估，不入账');
    expect(assets.textContent).toContain('现金 + 存款');
    expect(assets.textContent).toContain('权益 / 防御占比');
    app.unmount();
  });
});

describe('OverviewTab 待办聚合', () => {
  it('没有待办时显示「今天没有待办」', async () => {
    const { host, app } = mountOverview();
    await flush();

    const today = section(host, 'today');
    expect(today.textContent).toContain('今天没有待办');
    expect(todoItems(host).length).toBe(0);
    app.unmount();
  });

  it('todaySnapshotDone === false 时出现「今日快照」条目，点了跳资产快照', async () => {
    const { host, app, ctx } = mountOverview({ todaySnapshotDone: ref(false) });
    await flush();

    const today = section(host, 'today');
    expect(today.textContent).not.toContain('今天没有待办');

    const item = todoItems(host).find((b) => b.textContent.includes('今日快照'));
    expect(item).toBeTruthy();
    // 资产快照页已并入「收益与快照」（快照明细在那里），所以待办跳的是 performance
    expect(item.textContent).toContain('去收益与快照');

    item.click();
    expect(ctx.goTab).toHaveBeenCalledWith('performance');
    // 收盘提示组件全页最多出现一次（页面顶部那一条）
    expect(host.querySelectorAll('.snapshot-reminder').length).toBeLessThanOrEqual(1);
    app.unmount();
  });

  it('在途申购进待办，点「查看在途」走 goPendingTransactions', async () => {
    const { host, app, ctx } = mountOverview({
      dashboard: ref(flatDashboard({ pending_purchase: 5000, pending_count: 2 })),
    });
    await flush();

    const item = todoItems(host).find((b) => b.textContent.includes('申购在途'));
    expect(item).toBeTruthy();
    expect(item.textContent).toContain('2 笔');
    expect(item.textContent).toContain('5000.00');

    item.click();
    expect(ctx.goPendingTransactions).toHaveBeenCalled();
    app.unmount();
  });

  it('最新价偏旧进待办，点了去持仓明细', async () => {
    const { host, app, ctx } = mountOverview({
      dashboard: ref(flatDashboard({ price_stale: true })),
    });
    await flush();

    const item = todoItems(host).find((b) => b.textContent.includes('最新价偏旧'));
    expect(item).toBeTruthy();
    item.click();
    expect(ctx.goTab).toHaveBeenCalledWith('holdings');
    app.unmount();
  });
});
