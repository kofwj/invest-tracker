/**
 * K线弹窗入口回归测试（决策 D3：整页 KlineTab 降级成「持仓明细里点标的名」打开的弹窗）。
 *
 * 关注三件事：
 *  - 点第一列「标的」的名称 → 弹窗打开，并且打开就以该行的 code 调 api.getKlines；
 *  - 关掉弹窗、再点另一行 → getKlines 拿到的是新的 code（不是上一只残留的）；
 *  - 弹窗没打开时不请求 getKlines（挂载持仓页不会顺手去外网拉 K 线）。
 *
 * 挂载方式照抄 manual-price-ui.test.js：jsdom + createApp + provide(APP_CTX_KEY, ctx)
 * + el-* 桩组件（el-dialog 桩按 modelValue 开关，顺带反映 destroy-on-close）
 * + element-plus 的 ElMessage mock（生产构建里 el-* 由 unplugin-vue-components 注册）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createApp, h, provide, inject, computed, ref } from 'vue';
import { APP_CTX_KEY } from '../src/composables/useAppCtx.js';
import HoldingsTab from '../src/views/HoldingsTab.vue';

const elMock = vi.hoisted(() => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  messageBox: { confirm: vi.fn(), alert: vi.fn(), prompt: vi.fn() },
}));

vi.mock('element-plus', () => ({
  ElMessage: elMock.message,
  ElMessageBox: elMock.messageBox,
  ElLoading: { service: () => ({ close: () => {} }) },
  ElNotification: elMock.message.info,
}));

const ROWS = [
  { code: '601288', name: '农业银行', category: 'A股权益', quantity: 1000, last_price: 3.5, avg_cost: 3.1, diluted_cost: 3.05, expected_return: 0.05, trailing_return_1y: 0.12, trailing_return_1y_source: '东财' },
  { code: '600519', name: '贵州茅台', category: 'A股权益', quantity: 10, last_price: 1500, avg_cost: 1400, diluted_cost: 1390, expected_return: null, trailing_return_1y: -0.05, trailing_return_1y_source: '东财' },
];

// HoldingsTab 与 KlineDialog 都直接 import api（不经过 ctx），所以按模块路径 mock 掉 axios 层
const apiMock = vi.hoisted(() => ({
  getKlines: vi.fn(async () => ({ data: { code: '', count: 0, rows: [] } })),
  getHoldings: vi.fn(async () => ({ data: [] })),
  fundamentalCheck: vi.fn(async () => ({ data: { sections: [], profile: null, dividends: [], dividend_summary: null } })),
  syncKlines: vi.fn(async () => ({ data: {} })),
  setHoldingPrice: vi.fn(async () => ({ data: {} })),
}));

vi.mock('../src/api/index.js', () => ({
  API: '/api',
  SESSION_EXPIRED_MESSAGE: '登录状态已过期，请重新登录',
  api: apiMock,
  default: apiMock,
}));

// 透传桩：渲染默认插槽、保留 attrs（@click 会挂成原生监听，所以可以直接点）
const passthrough = (name) => ({
  name,
  setup(_, { slots, attrs }) {
    return () => h('div', attrs, slots.default ? slots.default() : []);
  },
});

// el-dialog 桩：modelValue 为真才渲染 body + footer —— 这样「开/关」在 DOM 上看得见，
// 也顺带复现 destroy-on-close（关掉内容就没了）
const ElDialogStub = {
  name: 'ElDialog',
  props: {
    modelValue: { type: Boolean, default: false },
    title: { type: String, default: '' },
    width: { type: String, default: '' },
    top: { type: String, default: '' },
    destroyOnClose: { type: Boolean, default: false },
  },
  emits: ['update:modelValue', 'closed'],
  setup(props, { slots }) {
    return () => (props.modelValue
      ? h('div', {
        class: 'stub-dialog',
        'data-title': props.title,
        'data-destroy-on-close': String(props.destroyOnClose),
      }, [
        slots.default ? slots.default() : [],
        slots.footer ? slots.footer() : [],
      ])
      : null);
  },
};

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
  ElInput: passthrough('ElInput'),
  ElRadioGroup: passthrough('ElRadioGroup'),
  ElRadioButton: passthrough('ElRadioButton'),
  ElDialog: ElDialogStub,
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

/** 按文案找桩按钮（passthrough 渲染出来的最内层 div） */
function findButton(root, label) {
  const nodes = [...root.querySelectorAll('div')].filter((el) => el.textContent.trim() === label);
  return nodes.find((el) => el.children.length === 0) || nodes[0] || null;
}
const click = (el) => el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
const formatMoney = (v, d = 2, s = false) => (
  v == null ? '—' : `${s && Number(v) >= 0 ? '+' : ''}${Number(v).toFixed(d)}`
);

const holdingsCtx = ({ fetchData = vi.fn(async () => {}) } = {}) => ({
  holdings: ref(ROWS.map((r) => ({ ...r }))),
  dashboard: ref({ manual_price_codes: [], total_assets: 100000 }),
  showTransactions: vi.fn(),
  openExpectedReturnDialog: vi.fn(),
  openHoldingCorrectionDialog: vi.fn(),
  formatMoney,
  formatPercent: (v, d = 2) => (v == null ? '—' : `${(Number(v) * 100).toFixed(d)}%`),
  holdingFloatProfit: (row) => (Number(row.last_price) - Number(row.avg_cost)) * Number(row.quantity),
  holdingLifetimeProfit: (row) => (Number(row.last_price) - Number(row.diluted_cost)) * Number(row.quantity),
  holdingFloatProfitRate: (row) => (Number(row.avg_cost) ? Number(row.last_price) / Number(row.avg_cost) - 1 : null),
  holdingLifetimeProfitRate: (row) => (Number(row.diluted_cost) ? Number(row.last_price) / Number(row.diluted_cost) - 1 : null),
  trailingSyncing: ref(false),
  syncTrailingReturns: vi.fn(async () => {}),
  fetchData,
  goTab: vi.fn(),
  // HomeDashboard 也要用的 ctx key
  maintenanceStatus: ref(null),
  todaySnapshotDone: ref(false),
  latestPriceStatusText: ref('—'),
  latestBackupText: ref('—'),
  pendingTransactions: ref([]),
  goPendingTransactions: vi.fn(),
});

beforeEach(() => {
  vi.clearAllMocks();
  apiMock.getHoldings.mockImplementation(async () => ({ data: ROWS.map((r) => ({ ...r })) }));
  apiMock.getKlines.mockImplementation(async (c) => ({
    data: { code: c, count: 0, rows: [] },
  }));
  apiMock.fundamentalCheck.mockImplementation(async () => ({
    data: { sections: [], profile: null, dividends: [], dividend_summary: null },
  }));
});

describe('持仓明细 → K线弹窗', () => {
  it('点标的名 → 弹窗打开，并用这一行的 code 调 getKlines', async () => {
    const ctx = holdingsCtx();
    const { host, app } = mountView(HoldingsTab, ctx);
    await flush();

    // 点之前弹窗压根没挂（惰性挂载），更不会去拉 K 线
    expect(host.querySelector('.stub-dialog')).toBeNull();
    expect(apiMock.getKlines).not.toHaveBeenCalled();

    const nameBtn = findButton(host, '农业银行');
    expect(nameBtn).toBeTruthy();
    // @click.stop：点标的名不该冒泡成「行点击 → 看交易记录」
    let bubbled = false;
    nameBtn.parentElement.addEventListener('click', () => { bubbled = true; });
    click(nameBtn);
    expect(bubbled).toBe(false);
    expect(ctx.showTransactions).not.toHaveBeenCalled();
    await flush();

    const dlg = host.querySelector('.stub-dialog');
    expect(dlg).toBeTruthy();
    expect(dlg.getAttribute('data-destroy-on-close')).toBe('true');
    // 标题里带上标的 code（有名称就带名称）
    expect(dlg.getAttribute('data-title')).toContain('601288');
    expect(dlg.getAttribute('data-title')).toContain('农业银行');
    // 内容真的渲染进了弹窗（K线图容器）
    expect(dlg.querySelector('.kline-chart')).toBeTruthy();

    expect(apiMock.getKlines).toHaveBeenCalledTimes(1);
    expect(apiMock.getKlines.mock.calls[0][0]).toBe('601288');
    app.unmount();
  });

  it('关掉弹窗再点另一行 → getKlines 收到新的 code，不是上一只', async () => {
    const ctx = holdingsCtx();
    const { host, app } = mountView(HoldingsTab, ctx);
    await flush();

    click(findButton(host, '农业银行'));
    await flush();
    expect(host.querySelector('.stub-dialog')).toBeTruthy();
    expect(apiMock.getKlines.mock.calls[0][0]).toBe('601288');

    click(findButton(host, '关闭'));
    await flush();
    expect(host.querySelector('.stub-dialog')).toBeNull(); // 关掉后内容被销毁
    expect(apiMock.getKlines).toHaveBeenCalledTimes(1); // 关窗不会再发一次

    click(findButton(host, '贵州茅台'));
    await flush();

    expect(apiMock.getKlines).toHaveBeenCalledTimes(2);
    expect(apiMock.getKlines.mock.calls.map((c) => c[0])).toEqual(['601288', '600519']);
    expect(host.querySelector('.stub-dialog').getAttribute('data-title')).toContain('600519');
    app.unmount();
  });

  it('弹窗未打开时不请求 getKlines', async () => {
    const ctx = holdingsCtx();
    const { host, app } = mountView(HoldingsTab, ctx);
    await flush();
    await flush();

    expect(host.querySelector('.stub-dialog')).toBeNull();
    expect(apiMock.getKlines).not.toHaveBeenCalled();
    // 持仓页自己也不去拉 K 线持仓列表（打开弹窗时才拉）
    expect(apiMock.getHoldings).not.toHaveBeenCalled();
    app.unmount();
  });
});
