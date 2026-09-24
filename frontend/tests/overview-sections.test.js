/**
 * 首页按已确认原型（docs/design/prototype/overview.html）重排后的回归测试。
 *
 * 结构固定成三段（DOM 顺序就是视觉顺序）：
 *   ① [data-section="today"]  今天的卡：左「今日盈亏 + 盘中粗估 + 最新价同步时间」/ 右「N 项要动手」
 *   ② [data-section="assets"] 资产四个数字一行（总资产 / 持仓浮盈 / 现金+存款 / 权益·防御）+ 持仓速览表
 *   ③ [data-section="detail"] 组合脉搏（4×2）+ 同步与备份（4 项），都不折叠
 * 「近半月资产」曲线、本月/今年两张卡、「今天可做」入口、底部三条状态条在这个版本里被删掉了。
 *
 * 覆盖：
 *  - 三段都在，且顺序固定；今日盈亏在 ① 里；
 *  - 「今日盈亏」用 performance 模块的 perfTodayPnl：为 null 时显示「—」+ 原因，不编数；
 *    注意**不能**用 perfTodayRow（那个在「今天已有正式快照」时返回 null，是给收益分析表补行用的）——
 *    之前首页用错了它，导致每天快照一写、首页今日盈亏就永远是「—」。
 *  - 「当日参考」降级成 ① 今天卡里的一行小字，仍标「盘中粗估 / 不入账」，不再单独成卡；
 *  - 待办：无待办显示「今天没有待办」，todaySnapshotDone === false 出现「今日快照」条目且可跳转，
 *    没有人工对账记录时出现「还没做过人工对账」条目且跳 performance；
 *  - 资产段四个数字、组合脉搏 8 项、同步与备份 4 项：取不到一律「—」，不编数。
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
    perfLatestSnapshotDate: ref('2026-03-06'),
    // 默认「已经做过人工对账」；不传记录（ref(null)）才出那条待办
    reconcileData: ref({ date: '2026-03-01', manual_total_assets: 100000, gap: 1000 }),
    fetchReconcile: vi.fn(async () => {}),
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
/** 组合脉搏 8 项 + 同步与备份 4 项，按 DOM 顺序取值 */
const briefValues = (host) => [...host.querySelectorAll('.ov-brief-v')].map((el) => el.textContent.trim());

describe('OverviewTab 固定三段', () => {
  it('三段都在，顺序是 ① 今天 → ② 资产 → ③ 脉搏/同步，今日盈亏在 ① 里', async () => {
    const { host, app } = mountOverview();
    await flush();

    const names = [...host.querySelectorAll('.ov-section')].map((el) => el.getAttribute('data-section'));
    expect(names).toEqual(['today', 'assets', 'detail']);

    // 区块顺序（原型自上而下）：今天 → 持仓速览 → 组合脉搏 → 同步与备份
    const text = host.textContent;
    const iToday = text.indexOf('今天 · 最近一个交易日');
    const iHoldings = text.indexOf('持仓速览');
    const iPulse = text.indexOf('组合脉搏');
    const iSync = text.indexOf('同步与备份');
    expect(iToday).toBeGreaterThan(-1);
    expect(iHoldings).toBeGreaterThan(iToday);
    expect(iPulse).toBeGreaterThan(iHoldings);
    expect(iSync).toBeGreaterThan(iPulse);

    // 「今日盈亏」在 ① 今天里，而不是被账本数字挤到后面
    const today = section(host, 'today');
    expect(today.querySelector('.ov-lede').textContent).toContain('1234.50');
    expect(today.textContent).toContain('今天 · 最近一个交易日');
    // 「本月 / 今年」两张卡按新原型删掉了（收益窗口在「收益分析」页看）
    expect(today.textContent).not.toContain('本月');
    expect(today.textContent).not.toContain('今年');
    app.unmount();
  });

  it('第 ③ 段收着组合脉搏与同步/备份，且都直接可见；近半月曲线与「今天可做」已删', async () => {
    const { host, app } = mountOverview();
    await flush();
    const detail = section(host, 'detail');
    expect(detail.textContent).toContain('组合脉搏');
    expect(detail.textContent).toContain('同步与备份');
    expect(detail.textContent).not.toContain('今天可做');
    // 组合脉搏 8 项 + 同步与备份 6 项（4 项时效 + 2 项备份）都直接渲染出来（不折叠）
    expect(briefValues(host).length).toBe(14);
    // 「近半月资产」整块删掉：容器和标题都不再存在
    expect(host.querySelector('#overviewWeekChart')).toBeNull();
    expect(host.textContent).not.toContain('近半月');
    app.unmount();
  });
});

describe('OverviewTab 今日盈亏口径', () => {
  it('perfTodayPnl 为 null 时显示「—」并说明原因，不编数', async () => {
    const { host, app } = mountOverview({ perfTodayPnl: ref(null), todaySnapshotDone: ref(true) });
    await flush();

    const today = section(host, 'today');
    const value = today.querySelector('.ov-lede');
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
    });
    await flush();

    const today = section(host, 'today');
    expect(today.querySelector('.ov-lede').textContent.trim()).toBe('—');
    expect(today.textContent).toContain('收益数据未加载');
    // 盘中粗估是另一条口径：照样显示，但明确标「不入账」，不能当成今日盈亏
    expect(today.textContent).toContain('盘中粗估');
    expect(today.textContent).toContain('不入账');
    expect(today.textContent).toContain('120.00');
    app.unmount();
  });

  it('今天已有正式快照（已收盘）时照样显示数字——快照写完不能让首页变「—」', async () => {
    const { host, app } = mountOverview({
      perfTodayPnl: ref({ ...TODAY_ROW, closed: true }),
      todaySnapshotDone: ref(true),
      perfLatestSnapshotDate: ref('2026-03-07'),
    });
    await flush();

    const card = section(host, 'today');
    expect(card.querySelector('.ov-lede').textContent).toContain('1234.50');
    expect(card.textContent).toContain('+1.23%');
    expect(card.textContent).toContain('已收盘');
    app.unmount();
  });

  it('perfTodayPnl 有值时显示金额与涨跌幅', async () => {
    const { host, app } = mountOverview();
    await flush();

    const card = section(host, 'today');
    expect(card.querySelector('.ov-lede').textContent).toContain('1234.50');
    expect(card.textContent).toContain('+1.23%');
    expect(card.textContent).toContain('盘中口径');
    expect(card.textContent).toContain('2026-03-06'); // 说清基准是哪天
    app.unmount();
  });
});

describe('OverviewTab 「当日参考」的位置', () => {
  it('降为「今天」卡里的一行小字（盘中粗估，不入账），资产段只剩四个账本数字', async () => {
    const { host, app } = mountOverview();
    await flush();

    const today = section(host, 'today');
    expect(today.textContent).toContain('盘中粗估');
    expect(today.textContent).toContain('不入账');
    expect(today.textContent).toContain('120.00');

    // 资产段不再有「当日参考」卡片：它是盘中口径，不能和账本口径并排
    const assets = section(host, 'assets');
    expect(assets.textContent).not.toContain('当日参考');
    expect(assets.textContent).toContain('现在总资产');
    expect(assets.textContent).toContain('持仓浮盈');
    expect(assets.textContent).toContain('现金 + 存款');
    expect(assets.textContent).toContain('权益 / 防御');
    expect(assets.textContent).toContain('60.0% / 40.0%');
    app.unmount();
  });
});

describe('OverviewTab 资产四数字 / 持仓速览 / 脉搏 / 同步备份', () => {
  it('资产四个数字取 dashboard 与配置口径，等权一行', async () => {
    const { host, app } = mountOverview({
      dashboard: ref(flatDashboard({ total_market_value: 80000, holdings_count: 3 })),
      holdings: ref([{ code: 'a', total_dividend: 1234.5 }, { code: 'b', total_dividend: 100 }]),
    });
    await flush();

    const values = [...section(host, 'assets').querySelectorAll('.ov-metric-value')].map((el) => el.textContent.trim());
    expect(values).toEqual(['101000.00', '+1000.00', '700.00', '60.0% / 40.0%']);
    const assets = section(host, 'assets').textContent;
    expect(assets).toContain('含分红 1334.50');
    expect(assets).toContain('银行 200.00 · 证券 500.00');
    app.unmount();
  });

  it('持仓速览：保留 aria-label，按市值降序，新增「分红」列', async () => {
    const { host, app } = mountOverview({
      holdings: ref([
        { code: '000001', name: '小额', category: 'A股权益', quantity: 1, last_price: 10, avg_cost: 9, total_dividend: 5 },
        { code: '600028', name: '大额', category: 'A股权益', quantity: 10, last_price: 100, avg_cost: 90, total_dividend: 0 },
      ]),
    });
    await flush();

    const table = host.querySelector('[aria-label="持仓速览"]');
    expect(table).toBeTruthy();
    const cols = [...table.querySelectorAll('.stub-col')];
    expect(cols.map((el) => el.getAttribute('data-label'))).toEqual(['标的', '最新价', '市值', '持仓浮盈', '分红']);
    // 按市值降序：大额（1000）排在小额（10）前面
    expect([...cols[0].querySelectorAll('.asset-cell-name')].map((el) => el.textContent.trim()))
      .toEqual(['大额', '小额']);
    // 「分红」列 = 每行的 total_dividend
    expect([...cols[4].querySelectorAll('.stub-cell')].map((el) => el.textContent.trim())).toEqual(['0.00', '5.00']);
    app.unmount();
  });

  it('组合脉搏 8 项：权益/防御/现金占比/在途/市值/只数/全周期/目标年化', async () => {
    const { host, app } = mountOverview({
      dashboard: ref(flatDashboard({
        total_market_value: 80000,
        lifetime_profit: 12345.67,
        holdings_count: 3,
      })),
    });
    await flush();

    expect(briefValues(host).slice(0, 8)).toEqual([
      '60.0%', '40.0%', '0.7%', '0 笔', '80000.00', '3 只', '+12345.67', '5.00%',
    ]);
    app.unmount();
  });

  it('同步与备份 4 项取价格与快照时效；取不到的显示「—」而不是 0', async () => {
    const bare = mountOverview();
    await flush();
    expect(briefValues(bare.host).slice(8, 12)).toEqual(['—', '—', '2026-03-06', '— / —']);
    bare.app.unmount();

    const rich = mountOverview({
      dashboard: ref(flatDashboard({
        last_price_sync_at: '2026-03-07T19:30:00',
        price_age_hours: 13.7,
        price_stale: false,
        unpriced_count: 0,
        manual_price_codes: ['600028'],
      })),
    });
    await flush();
    expect(briefValues(rich.host).slice(8, 12)).toEqual([
      '03-07 19:30', '13.7 小时前 · 未过期', '2026-03-06', '0 只 / 1 只',
    ]);
    rich.app.unmount();
  });

  it('备份两项：有记录显示时间与份数，取不到显示「—」而不是编一个', async () => {
    const bare = mountOverview();
    await flush();
    // 默认 fixture：ctx 给了最近备份时间；份数回落到 maintenanceStatus.backup_count
    expect(briefValues(bare.host).slice(12)).toEqual(['2026-03-06 18:00', '1 份']);
    bare.app.unmount();

    // 两边都取不到 → 「—」：不编「暂无备份」，也不写 0
    const unknown = mountOverview({ latestBackupText: ref(''), maintenanceStatus: ref({}) });
    await flush();
    expect(briefValues(unknown.host).slice(12)).toEqual(['—', '—']);
    unknown.app.unmount();

    const withBackup = mountOverview({ latestBackupText: ref('2026-03-07 02:15'), backups: ref([{}, {}]) });
    await flush();
    expect(briefValues(withBackup.host).slice(12)).toEqual(['2026-03-07 02:15', '2 份']);
    withBackup.app.unmount();
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
    expect(today.textContent).toContain('项要动手');

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

  it('没有人工对账记录时出现「还没做过人工对账」，点了跳收益与快照', async () => {
    const { host, app, ctx } = mountOverview({ reconcileData: ref(null) });
    await flush();

    expect(section(host, 'today').textContent).toContain('1 项要动手');
    const item = todoItems(host).find((b) => b.textContent.includes('人工对账'));
    expect(item).toBeTruthy();
    expect(item.textContent).toContain('每周对照券商实际余额录一次');
    expect(item.textContent).toContain('去对账');

    item.click();
    expect(ctx.goTab).toHaveBeenCalledWith('performance');
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
