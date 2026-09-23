/**
 * 「手动改价」（数据源全挂时的兜底，PUT /holdings/{code}/price）的前端回归测试。
 *
 * 关注四件事：
 *  - 点「改价」→ 确认 → 用 code + 数字价格调 setHoldingPrice，成功后刷新数据；
 *  - 请求在飞的时候连点不会发第二次；
 *  - 后端 400（例如「价格必须大于 0」）的 detail 要原样弹给用户，不能吞；
 *  - dashboard.manual_price_codes 命中的行才显示「人工价」徽标。
 *
 * 挂载方式照抄 views-write-guards.test.js：jsdom + createApp + provide(APP_CTX_KEY, ctx)
 * + el-* 桩组件 + element-plus 的 ElMessage/ElMessageBox mock（生产构建里 el-* 由
 * unplugin-vue-components 自动注册，测试环境没有这层）。
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

// HoldingsTab 直接 import api（不经过 ctx），所以按模块路径 mock 掉真正的 axios 层
const apiMock = vi.hoisted(() => ({ setHoldingPrice: vi.fn(async () => ({ data: {} })) }));

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
  ElTable: ElTableStub,
  ElTableColumn: ElTableColumnStub,
};

function mountView(view, ctx) {
  const host = document.createElement('div');
  const App = { setup() { provide(APP_CTX_KEY, ctx); return () => h(view); } };
  const app = createApp(App);
  for (const [name, comp] of Object.entries(STUBS)) app.component(name, comp);
  app.directive('loading', {});
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

const ROWS = [
  { code: '601288', name: '农业银行', category: 'A股权益', quantity: 1000, last_price: 3.5, avg_cost: 3.1, diluted_cost: 3.05, expected_return: 0.05, trailing_return_1y: 0.12, trailing_return_1y_source: '东财' },
  { code: '600519', name: '贵州茅台', category: 'A股权益', quantity: 10, last_price: 1500, avg_cost: 1400, diluted_cost: 1390, expected_return: null, trailing_return_1y: -0.05, trailing_return_1y_source: '东财' },
];

const holdingsCtx = ({ manualPriceCodes = [], fetchData = vi.fn(async () => {}) } = {}) => ({
  holdings: ref(ROWS.map((r) => ({ ...r }))),
  dashboard: ref({ manual_price_codes: manualPriceCodes, total_assets: 100000 }),
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
  apiMock.setHoldingPrice.mockImplementation(async () => ({ data: {} }));
  elMock.messageBox.prompt.mockResolvedValue({ value: '38.36' });
});

describe('HoldingsTab 手动改价', () => {
  it('点「改价」→ 确认 → 用 code + 数字价格调 setHoldingPrice，并刷新数据', async () => {
    const ctx = holdingsCtx();
    const { host, app } = mountView(HoldingsTab, ctx);
    await flush();

    const btn = findButton(host, '改价');
    expect(btn).toBeTruthy();
    // 已有的「校正」按钮不受影响
    expect(findButton(host, '校正')).toBeTruthy();

    click(btn);
    await flush();

    expect(elMock.messageBox.prompt).toHaveBeenCalledTimes(1);
    expect(elMock.messageBox.prompt.mock.calls[0][0]).toBe('填写最新价（元）');
    expect(elMock.messageBox.prompt.mock.calls[0][1]).toBe('手动改价');
    expect(elMock.messageBox.prompt.mock.calls[0][2].inputErrorMessage).toBe('请输入正数');

    expect(apiMock.setHoldingPrice).toHaveBeenCalledTimes(1);
    expect(apiMock.setHoldingPrice).toHaveBeenCalledWith('601288', 38.36);
    expect(typeof apiMock.setHoldingPrice.mock.calls[0][1]).toBe('number');

    expect(elMock.message.success).toHaveBeenCalledWith('已更新为 38.36');
    expect(ctx.fetchData).toHaveBeenCalled();

    await flush();
    expect(btn.getAttribute('loading')).toBe('false');
    app.unmount();
  });

  it('请求在飞时连点两次只调一次 setHoldingPrice，按钮进 loading', async () => {
    const pending = deferred();
    apiMock.setHoldingPrice.mockImplementation(() => pending.promise);

    const ctx = holdingsCtx();
    const { host, app } = mountView(HoldingsTab, ctx);
    await flush();

    const btn = findButton(host, '改价');
    click(btn);
    click(btn); // 确认框还没回来 / 请求还没回来的第二次点击
    await flush();

    expect(apiMock.setHoldingPrice).toHaveBeenCalledTimes(1);
    expect(btn.getAttribute('loading')).toBe('true');

    pending.resolve({ data: {} });
    await flush();
    expect(btn.getAttribute('loading')).toBe('false');
    expect(apiMock.setHoldingPrice).toHaveBeenCalledTimes(1);
    app.unmount();
  });

  it('后端 400 的 detail 用 ElMessage.error 原样弹出', async () => {
    apiMock.setHoldingPrice.mockImplementation(async () => {
      throw Object.assign(new Error('Request failed with status code 400'), {
        response: { status: 400, data: { detail: '价格必须大于 0' } },
      });
    });

    const ctx = holdingsCtx();
    const { host, app } = mountView(HoldingsTab, ctx);
    await flush();

    click(findButton(host, '改价'));
    await flush();

    expect(elMock.message.error).toHaveBeenCalledTimes(1);
    expect(elMock.message.error).toHaveBeenCalledWith('价格必须大于 0');
    expect(elMock.message.success).not.toHaveBeenCalled();
    expect(ctx.fetchData).not.toHaveBeenCalled();
    app.unmount();
  });

  it('manual_price_codes 命中的行才渲染「人工价」徽标', async () => {
    const ctx = holdingsCtx({ manualPriceCodes: ['601288'] });
    const { host, app } = mountView(HoldingsTab, ctx);
    await flush();

    const priceCells = [...host.querySelectorAll('.stub-col[data-label="最新价"] .stub-cell')];
    expect(priceCells.length).toBe(2);

    expect(priceCells[0].textContent).toContain('人工价');
    expect(priceCells[0].textContent).toContain('3.5000');
    expect(priceCells[1].textContent).not.toContain('人工价');
    // 徽标只出现一次
    expect(host.textContent.split('人工价').length - 1).toBe(1);
    // tooltip 说明文案在 DOM 里
    expect(host.innerHTML).toContain('价格是手动填的，还没被真实行情覆盖');
    app.unmount();
  });
});
