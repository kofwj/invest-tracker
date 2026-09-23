/**
 * 写操作按钮的 loading / 防连点 + 「价格没更新」提示的回归测试。
 *
 * 这些按钮以前点两下就会发两份 PUT/DELETE/POST（按钮既没有 loading，处理函数也没有入口判断）。
 * 这里用 jsdom 真挂几个 view，直接点桩组件渲染出来的按钮，断言：
 *  - 连点两次只触发一次底层调用；
 *  - 进行中按钮带上 loading（真实 Element Plus 里 :loading 同时会 disabled）；
 *  - createSnapshot 409 → 确认 → 带 force 重试，且重试前不会重复发首轮请求。
 *
 * 注：生产构建里 el-* 由 unplugin-vue-components 自动注册，测试环境没有这层，
 * 所以下面用桩组件代替（只关心本页自己的结构、事件和插槽里的数据）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createApp, h, provide, inject, computed, ref } from 'vue';
import { APP_CTX_KEY } from '../src/composables/useAppCtx.js';
import CashTab from '../src/views/CashTab.vue';
import SnapshotPanel from '../src/components/SnapshotPanel.vue';
import BackupOpsTab from '../src/views/BackupOpsTab.vue';
import PerformanceTab from '../src/views/PerformanceTab.vue';

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

// 透传桩：渲染默认插槽、保留 attrs（@click 会挂成原生监听，所以可以直接点）
const passthrough = (name) => ({
  name,
  setup(_, { slots, attrs }) {
    return () => h('div', attrs, slots.default ? slots.default() : []);
  },
});

// el-table / el-table-column：列插槽依赖 row scope，这里用 provide/inject 把当前表的 data 传下去
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
  ElSpace: passthrough('ElSpace'),
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
  ElStatistic: {
    name: 'ElStatistic',
    props: { title: { type: String, default: '' }, value: { type: [Number, String], default: '' }, precision: { type: Number, default: 0 }, prefix: { type: String, default: '' }, suffix: { type: String, default: '' } },
    setup(props) {
      return () => h('div', { class: 'stub-statistic' }, `${props.title} ${props.value}`);
    },
  },
  ElEmpty: passthrough('ElEmpty'),
  ElUpload: passthrough('ElUpload'),
  ElTable: ElTableStub,
  ElTableColumn: ElTableColumnStub,
};

function mountView(view, ctx) {
  const host = document.createElement('div');
  const App = { setup() { provide(APP_CTX_KEY, ctx); return () => h(view); } };
  const app = createApp(App);
  for (const [name, comp] of Object.entries(STUBS)) app.component(name, comp);
  app.directive('loading', {}); // 桩环境没装 ElLoading 指令，避免刷屏告警
  app.mount(host);
  return { host, app };
}

const flush = () => new Promise((r) => setTimeout(r, 20));
const deferred = () => {
  let resolve;
  const promise = new Promise((r) => { resolve = r; });
  return { promise, resolve };
};

/** 按文案找桩按钮（passthrough 渲染出来的最内层 div） */
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

// ---------------------------------------------------------------- CashTab

function mountCashTab() {
  const pending = deferred();
  const ctx = {
    dashboard: ref({ securities_cash: 1000 }),
    feeSettings: ref({
      华泰证券: {
        A股权益: { commission_rate_pct: 0.025, stamp_tax_rate_pct: 0.05, transfer_fee_rate_pct: 0.001, min_commission: 0 },
      },
    }),
    feeAccounts: ref(['华泰证券']),
    activeFeeAccount: ref('华泰证券'),
    newFeeAccountName: ref(''),
    feeCategories: ref(['A股权益']),
    cashForm: ref({ amount: 1000 }),
    cashFlows: ref([]),
    cashFlowForm: ref({ date: '', account: '华泰证券', flow_type: '银证转入', amount: 0, remark: '' }),
    cashFlowQuery: ref({ dateRange: [], account: '', flow_type: '' }),
    cashFlowSummary: ref({ inflow: 0, outflowAbs: 0, net: 0 }),
    cashAudit: ref(null),
    cashFlowTagType: () => '',
    formatMoney,
    onActiveFeeAccountChange: vi.fn(),
    // 三个写操作都返回挂起的 promise，模拟请求在飞
    saveFeeSettings: vi.fn(() => pending.promise),
    resetFeeSettings: vi.fn(async () => {}),
    addFeeAccount: vi.fn(),
    removeFeeAccount: vi.fn(async () => {}),
    updateCash: vi.fn(() => pending.promise),
    addCashFlow: vi.fn(async () => {}),
    queryCashFlows: vi.fn(async () => {}),
    resetCashFlowQuery: vi.fn(async () => {}),
    openCashFlowEditDialog: vi.fn(),
    deleteCashFlow: vi.fn(async () => {}),
    fetchCashAudit: vi.fn(async () => {}),
  };
  return { ctx, host: mountView(CashTab, ctx), pending };
}

describe('CashTab 写按钮防连点', () => {
  it('「保存费率」连点两次只 PUT 一次，进行中按钮进 loading', async () => {
    const { ctx, host, pending } = mountCashTab();
    await flush();
    const btn = findButton(host.host, '保存费率');
    expect(btn).toBeTruthy();

    click(btn);
    expect(ctx.saveFeeSettings).toHaveBeenCalledTimes(1);
    click(btn); // DOM 还没来得及重渲染（真实环境里 :loading 已经 disabled）
    expect(ctx.saveFeeSettings).toHaveBeenCalledTimes(1);

    await flush();
    expect(btn.getAttribute('loading')).toBe('true');

    pending.resolve({});
    await flush();
    expect(btn.getAttribute('loading')).toBe('false');
    host.app.unmount();
  });

  it('「保存校准」连点两次只调 updateCash 一次', async () => {
    const { ctx, host } = mountCashTab();
    await flush();
    const btn = findButton(host.host, '保存校准');
    expect(btn).toBeTruthy();

    click(btn);
    click(btn);
    expect(ctx.updateCash).toHaveBeenCalledTimes(1);
    host.app.unmount();
  });
});

// ------------------------------- SnapshotPanel（原 SnapshotsTab，已并入「收益与快照」页）

describe('SnapshotPanel 写按钮防连点', () => {
  it('「压缩历史快照」连点两次只调 compactSnapshots 一次', async () => {
    const pending = deferred();
    const ctx = {
      snapshots: ref([]),
      snapshotRange: ref([]),
      snapshotMetrics: ref([]),
      snapshotChangeRows: ref([]),
      snapshotInsights: ref([]),
      snapshotSummary: ref(null),
      snapshotLoading: ref(false),
      reconcileData: ref(null),
      reconcileForm: ref({ date: '', amount: 0, note: '' }),
      reconcileSaving: ref(false),
      createSnapshot: vi.fn(async () => ({})),
      fetchSnapshots: vi.fn(async () => {}),
      exportSnapshots: vi.fn(async () => {}),
      compactSnapshots: vi.fn(() => pending.promise),
      saveReconcile: vi.fn(async () => {}),
      formatMoney,
      pct: (a, b) => (b ? `${(Number(a || 0) / Number(b) * 100).toFixed(1)}%` : '—'),
    };
    const { host, app } = mountView(SnapshotPanel, ctx);
    await flush();
    const btn = findButton(host, '压缩历史快照');
    expect(btn).toBeTruthy();
    // 组件化后不再有 PageShell 外壳，但内的四个区块必须都还在（原来靠整页挂载隐含覆盖）
    expect(host.innerHTML).toContain('人工对账（实盘核对）');
    expect(host.innerHTML).toContain('快照历史记录');
    expect(host.innerHTML).toContain('区间变化明细');
    expect(host.querySelector('[aria-label="快照历史记录"]')).toBeTruthy();
    expect(host.querySelector('[aria-label="区间变化明细"]')).toBeTruthy();
    // 决策 D4：组件里不再有「总资产趋势」图
    expect(host.innerHTML).not.toContain('总资产趋势');
    expect(host.querySelector('#snapshotTrendChart')).toBeNull();

    click(btn);
    click(btn);
    expect(ctx.compactSnapshots).toHaveBeenCalledTimes(1);

    await flush();
    expect(btn.getAttribute('loading')).toBe('true');
    pending.resolve({});
    await flush();
    expect(btn.getAttribute('loading')).toBe('false');
    app.unmount();
  });

  it('「记录/更新今日快照」连点两次只调 createSnapshot 一次（复用 snapshotLoading）', async () => {
    const pending = deferred();
    const ctx = {
      snapshots: ref([]),
      snapshotRange: ref([]),
      snapshotMetrics: ref([]),
      snapshotChangeRows: ref([]),
      snapshotInsights: ref([]),
      snapshotSummary: ref(null),
      snapshotLoading: ref(false),
      reconcileData: ref(null),
      reconcileForm: ref({ date: '', amount: 0, note: '' }),
      reconcileSaving: ref(false),
      // 模块里的 createSnapshot 会同步把 snapshotLoading 置位；这里照做
      createSnapshot: vi.fn(() => {
        ctx.snapshotLoading.value = true;
        return pending.promise;
      }),
      fetchSnapshots: vi.fn(async () => {}),
      exportSnapshots: vi.fn(async () => {}),
      compactSnapshots: vi.fn(async () => {}),
      saveReconcile: vi.fn(async () => {}),
      formatMoney,
      pct: () => '—',
    };
    const { host, app } = mountView(SnapshotPanel, ctx);
    await flush();
    const btn = findButton(host, '记录/更新今日快照');

    click(btn);
    click(btn);
    expect(ctx.createSnapshot).toHaveBeenCalledTimes(1);
    pending.resolve({});
    ctx.snapshotLoading.value = false;
    await flush();
    app.unmount();
  });
});

// ----------------------------------------------------------- BackupOpsTab

describe('BackupOpsTab 行内写按钮防连点', () => {
  it('「下载」连点两次只调 downloadBackup 一次，同行动作一并禁用', async () => {
    const pending = deferred();
    const ctx = {
      maintenanceStatus: ref({ backup_count: 1, db_exists: true, db_size: 1024 }),
      backups: ref([{ filename: 'backup_1.db', size: 2048, created_at: '2026-03-01 10:00:00' }]),
      maintenanceLoading: ref(false),
      latestBackupText: ref(''),
      fetchMaintenance: vi.fn(async () => {}),
      createDbBackup: vi.fn(async () => {}),
      downloadBackup: vi.fn(() => pending.promise),
      restoreBackup: vi.fn(async () => {}),
      deleteBackup: vi.fn(async () => {}),
      restoreUploadedBackup: vi.fn(async () => {}),
    };
    const { host, app } = mountView(BackupOpsTab, ctx);
    await flush();
    const btn = findButton(host, '下载');
    expect(btn).toBeTruthy();

    click(btn);
    click(btn);
    expect(ctx.downloadBackup).toHaveBeenCalledTimes(1);
    expect(ctx.downloadBackup.mock.calls[0][0].filename).toBe('backup_1.db');

    await flush();
    expect(btn.getAttribute('loading')).toBe('true');
    expect(findButton(host, '恢复').getAttribute('disabled')).toBe('true');
    pending.resolve({});
    await flush();
    app.unmount();
  });
});

// --------------------------------------------------------- PerformanceTab

function perfCtx(overrides = {}) {
  const pending = deferred();
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
    addPerfFlow: vi.fn(() => pending.promise),
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
  };
  return { ctx, pending };
}

describe('PerformanceTab 写按钮防连点', () => {
  it('「新增」流水连点两次只调 addPerfFlow 一次', async () => {
    const { ctx, pending } = perfCtx();
    const { host, app } = mountView(PerformanceTab, ctx);
    await flush();
    const btn = findButton(host, '新增');
    expect(btn).toBeTruthy();

    click(btn);
    click(btn);
    expect(ctx.addPerfFlow).toHaveBeenCalledTimes(1);

    await flush();
    expect(btn.getAttribute('loading')).toBe('true');
    pending.resolve(true);
    await flush();
    app.unmount();
  });
});

describe('PerformanceTab 记录今日快照的 409 闸门', () => {
  it('409 → 弹确认（用后端 detail）→ 带 force 重试一次；连点不会重发首轮请求', async () => {
    const err409 = Object.assign(new Error('价格未更新'), {
      response: { status: 409, data: { detail: '最新价基准日期是 2026-02-27，不是今天，确认后仍要记录吗？' } },
    });
    const createSnapshot = vi.fn(async (force) => {
      if (force !== true) throw err409;
      return { data: { action: 'created' } };
    });
    const { ctx } = perfCtx({ createSnapshot, todaySnapshotDone: ref(false) });
    const { host, app } = mountView(PerformanceTab, ctx);
    await flush();
    const btn = findButton(host, '记录今日快照');
    expect(btn).toBeTruthy();

    click(btn);
    click(btn); // 第一轮还在飞（等确认框）时的第二次点击
    expect(createSnapshot).toHaveBeenCalledTimes(1);
    expect(createSnapshot.mock.calls[0]).toEqual([false]);

    await flush();
    expect(elMock.messageBox.confirm).toHaveBeenCalledTimes(1);
    expect(elMock.messageBox.confirm.mock.calls[0][0]).toContain('2026-02-27');
    expect(elMock.messageBox.confirm.mock.calls[0][1]).toBe('价格未更新');
    // 用户确认后带 force 重试
    expect(createSnapshot).toHaveBeenCalledTimes(2);
    expect(createSnapshot.mock.calls[1]).toEqual([true]);
    expect(ctx.fetchPerformance).toHaveBeenCalled();
    app.unmount();
  });

  it('用户取消确认时不带 force 重试', async () => {
    elMock.messageBox.confirm.mockRejectedValue('cancel');
    const err409 = Object.assign(new Error('价格未更新'), {
      response: { status: 409, data: { detail: '最新价不是今天的' } },
    });
    const createSnapshot = vi.fn(async (force) => {
      if (force !== true) throw err409;
      return {};
    });
    const ctx = perfCtx({ createSnapshot }).ctx;
    const { host, app } = mountView(PerformanceTab, ctx);
    await flush();
    click(findButton(host, '记录今日快照'));
    await flush();
    expect(createSnapshot).toHaveBeenCalledTimes(1);
    expect(createSnapshot.mock.calls.every((call) => call[0] !== true)).toBe(true);
    app.unmount();
  });
});

describe('PerformanceTab 每日收益的价格新鲜度标记', () => {
  it('price_stale 的行打「价格未更新」标签（title 带 price_date），并渲染缺价只数', async () => {
    const { ctx } = perfCtx({
      perfDailyRows: ref([
        { date: '2026-03-06', prevDate: '2026-03-05', change: -2000, pct: -1.94, assets: 101000, daysGap: 1, isGap: false },
        { date: '2026-03-05', prevDate: '2026-03-04', change: 500, pct: 0.5, assets: 103000, daysGap: 1, isGap: false },
      ]),
      perfTimeline: ref([
        { date: '2026-03-05', total_assets: 103000 },
        { date: '2026-03-06', total_assets: 101000, price_stale: 1, price_date: '2026-02-27', unpriced_count: 2 },
      ]),
      perfLatestSnapshotDate: ref('2026-03-06'),
    });
    const { host, app } = mountView(PerformanceTab, ctx);
    await flush();

    const html = host.innerHTML;
    expect(html).toContain('价格未更新');
    // hover 文案里带基准日期
    expect(html).toContain('2026-02-27');
    expect(host.textContent).toContain('缺价 2 只');
    // 只有 stale 的那一行有标记
    expect(host.textContent.split('价格未更新').length - 1).toBe(1);
    app.unmount();
  });
});

// ----------------------------------------------------------- SnapshotsTab 409

describe('SnapshotPanel 记录今日快照的 409 闸门', () => {
  const snapCtx = (createSnapshot) => ({
    snapshots: ref([]),
    snapshotRange: ref([]),
    snapshotMetrics: ref([]),
    snapshotChangeRows: ref([]),
    snapshotInsights: ref([]),
    snapshotSummary: ref(null),
    snapshotLoading: ref(false),
    reconcileData: ref(null),
    reconcileForm: ref({ date: '', amount: 0, note: '' }),
    reconcileSaving: ref(false),
    createSnapshot,
    fetchSnapshots: vi.fn(async () => {}),
    exportSnapshots: vi.fn(async () => {}),
    compactSnapshots: vi.fn(async () => {}),
    saveReconcile: vi.fn(async () => {}),
    formatMoney,
    pct: () => '—',
  });

  it('409 → 弹确认（用后端 detail）→ 带 force 重试；不会变成 unhandled rejection', async () => {
    elMock.messageBox.confirm.mockClear();
    const err409 = Object.assign(new Error('价格未更新'), {
      response: { status: 409, data: { detail: '最新价还是 2026-09-22 的，确认后仍要记录吗？' } },
    });
    const createSnapshot = vi.fn(async (force) => {
      if (force !== true) throw err409;
      return {};
    });
    const ctx = snapCtx(createSnapshot);
    const { host, app } = mountView(SnapshotPanel, ctx);
    await flush();

    click(findButton(host, '记录/更新今日快照'));
    await flush();

    expect(createSnapshot).toHaveBeenCalledTimes(2);
    expect(createSnapshot.mock.calls[0]).toEqual([false]);
    expect(createSnapshot.mock.calls[1]).toEqual([true]);
    expect(elMock.messageBox.confirm).toHaveBeenCalledTimes(1);
    expect(elMock.messageBox.confirm.mock.calls[0][0]).toContain('2026-09-22');
    app.unmount();
  });

  it('用户取消确认时不带 force 重试', async () => {
    elMock.messageBox.confirm.mockClear();
    elMock.messageBox.confirm.mockRejectedValueOnce('cancel');
    const err409 = Object.assign(new Error('价格未更新'), {
      response: { status: 409, data: { detail: '最新价不是今天的' } },
    });
    const createSnapshot = vi.fn(async (force) => {
      if (force !== true) throw err409;
      return {};
    });
    const ctx = snapCtx(createSnapshot);
    const { host, app } = mountView(SnapshotPanel, ctx);
    await flush();

    click(findButton(host, '记录/更新今日快照'));
    await flush();

    expect(createSnapshot).toHaveBeenCalledTimes(1);
    expect(createSnapshot.mock.calls.every((c) => c[0] !== true)).toBe(true);
    app.unmount();
  });
});
