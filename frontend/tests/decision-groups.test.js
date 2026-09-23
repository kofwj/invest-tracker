/**
 * DecisionTab 三分组结构的回归测试。
 *
 * 背景：这一页标题叫「今天该看」，却把 10 个区块平铺成 828 行，第一屏看不到「今天该做什么」；
 * 而生产库里 alert_rules / alert_events 都是 0 行 —— 价格预警整套从未被用过，却占了 3 个区块。
 *
 * 现在归成三组：
 *   ① 今天该看什么（默认展开）= 市场与结论 / 今日看点 + 行情带（关键指标一行 + 破线摘要一行）
 *   ② 我的持仓今天怎么样（默认展开）= 持仓今日贡献（粗估）
 *   ③ 观察与预警（默认收起，el-collapse）= 关键指数 / 自选关注 / 价格预警规则 / 最近一次检查触发 / 预警历史
 *
 * 这里要钉住的是：分组之后「10 个区块标题一个都没少」，且预警相关的按钮/请求仍然接在原 ctx 函数上
 * —— 折叠只改可见性，不删功能。
 *
 * 挂载方式照抄 views-write-guards.test.js（jsdom + createApp + provide(APP_CTX_KEY, ctx) + el-* 桩组件）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createApp, h, provide, inject, computed, ref } from 'vue';
import { APP_CTX_KEY } from '../src/composables/useAppCtx.js';
import DecisionTab from '../src/views/DecisionTab.vue';

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

// 透传桩：渲染默认插槽、保留 attrs（@click 会挂成原生监听，所以可以直接点）
const passthrough = (name) => ({
  name,
  setup(_, { slots, attrs }) {
    return () => h('div', attrs, slots.default ? slots.default() : []);
  },
});

// el-card 的 #header 是具名插槽，透传桩会把它丢掉；本页所有区块标题都在 #header 里，必须一起渲染
const ElCardStub = {
  name: 'ElCard',
  setup(_, { slots, attrs }) {
    return () => h('div', attrs, [
      slots.header ? h('div', { class: 'stub-card-header' }, slots.header()) : null,
      slots.default ? h('div', { class: 'stub-card-body' }, slots.default()) : null,
    ]);
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
  props: {
    label: { type: String, default: '' },
    prop: { type: String, default: '' },
  },
  setup(props, { slots }) {
    const rows = inject(TABLE_ROWS, null);
    return () => h(
      'div',
      { class: 'stub-col', 'data-label': props.label },
      (rows ? rows.value : []).map((row, $index) => h(
        'div',
        { class: 'stub-cell' },
        // 有列插槽就走插槽，没有就渲染 prop 对应的原始值（本页「说明」「代码」这类列只有 prop）
        slots.default ? slots.default({ row, $index }) : String(row?.[props.prop] ?? ''),
      )),
    );
  },
};
// el-collapse / el-collapse-item：真组件折叠时用 v-show 藏内容，桩里直接「折叠就不渲染」，
// 这样「默认收起 → 内容不可见」在测试里是真的可观察的。
const COLLAPSE_STATE = Symbol('collapse-state');
const ElCollapseStub = {
  name: 'ElCollapse',
  props: { modelValue: { type: Array, default: () => [] } },
  emits: ['update:modelValue'],
  setup(props, { slots, emit }) {
    provide(COLLAPSE_STATE, {
      isOpen: (name) => (props.modelValue || []).includes(name),
      toggle: (name) => {
        const open = props.modelValue || [];
        emit('update:modelValue', open.includes(name) ? open.filter((n) => n !== name) : [...open, name]);
      },
    });
    return () => h('div', { class: 'stub-collapse' }, slots.default ? slots.default() : []);
  },
};
const ElCollapseItemStub = {
  name: 'ElCollapseItem',
  props: { name: { type: String, default: '' } },
  setup(props, { slots }) {
    const state = inject(COLLAPSE_STATE, null);
    return () => h('div', { class: 'stub-collapse-item' }, [
      h(
        'div',
        {
          class: 'stub-collapse-header',
          onClick: () => state && state.toggle(props.name),
        },
        slots.title ? slots.title() : [],
      ),
      state && state.isOpen(props.name)
        ? h('div', { class: 'stub-collapse-content' }, slots.default ? slots.default() : [])
        : null,
    ]);
  },
};

const STUBS = {
  ElCard: ElCardStub,
  ElAlert: passthrough('ElAlert'),
  ElButton: passthrough('ElButton'),
  ElTag: passthrough('ElTag'),
  ElTooltip: passthrough('ElTooltip'),
  ElSpace: passthrough('ElSpace'),
  ElForm: passthrough('ElForm'),
  ElFormItem: passthrough('ElFormItem'),
  ElDialog: passthrough('ElDialog'),
  ElSelect: passthrough('ElSelect'),
  ElOption: passthrough('ElOption'),
  ElInput: passthrough('ElInput'),
  ElInputNumber: passthrough('ElInputNumber'),
  ElDatePicker: passthrough('ElDatePicker'),
  ElSwitch: passthrough('ElSwitch'),
  ElCollapse: ElCollapseStub,
  ElCollapseItem: ElCollapseItemStub,
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

/** 本页 <script setup> 里 useAppCtx() 解构出来的 key，一个不少（少一个模板就少一块内容） */
function decisionCtx(overrides = {}) {
  const ctx = {
    goTab: vi.fn(),
    dashboard: ref({ total_assets: 100000 }),
    marketSignals: ref({ today_contrib_estimate: 1200, portfolio_change_pct_estimate: 1.2, portfolio_vs_market: '今天跑赢大盘' }),
    marketLoading: ref(false),
    refreshMarket: vi.fn(async () => {}),
    breaches: ref([
      { level: 'warning', title: '沪深300 跌破', text: '较昨日 -1.8%' },
      { level: 'ok', title: '无关项', text: '不该出现' },
    ]),
    summaryText: ref(''),
    snapshot: ref({ total_assets: 100000, equity_pct: 62, defensive_pct: 38 }),
    targets: ref({ equity_pct: 60, band_pct: 5 }),
    disciplineLoading: ref(false),
    refreshDiscipline: vi.fn(async () => {}),
    depositRows: ref([]),
    formatMoney,
    alertChecking: ref(false),
    alertEventsLoading: ref(false),
    alertRules: ref([
      { id: 1, target_type: 'holding', name: '沪深300ETF', code: '510300', condition: 'below', threshold: 3.5, enabled: 1 },
    ]),
    alertEvents: ref([
      { target_code: '510300', message: '沪深300ETF 下穿 3.5', triggered_price: 3.42, threshold: 3.5, trigger_time: '2026-03-06 10:00:00' },
    ]),
    alertEventCodeFilter: ref(''),
    alertEventStartDate: ref(null),
    alertEventEndDate: ref(null),
    watchlistDraft: ref([{ code: '000300', name: '沪深300', secid: '1.000300' }]),
    watchlistSaving: ref(false),
    watchlistRows: ref([{ code: '000300', price: 3800, change_pct: 0.5 }]),
    alertForm: ref({ id: null, target_type: 'holding', code: '', name: '', condition: 'above', threshold: 0, enabled: true }),
    alertEditDialog: ref(false),
    triggeredAlerts: ref([{ message: '沪深300ETF 下穿 3.5', price: 3.42, change_pct: -1.2, trigger_time: '2026-03-06 10:00:00' }]),
    indexRows: ref([{ name: '沪深300', code: '000300', price: 3800, change_pct: 0.5 }]),
    holdingsDayRows: ref([{ name: '沪深300ETF', code: '510300', market_value: 50000, change_pct: 1.1, day_contrib: 550 }]),
    marketHighlights: ref(['今天组合涨 1.2%，主要来自宽基 ETF。']),
    marketComparisons: ref([{ benchmark: '沪深300', diff_pct: 0.4, portfolio_pct: 1.2, benchmark_pct: 0.8, text: 'vs 沪深300 +0.40pt' }]),
    marketUpdatedAt: ref('2026-03-06 15:00'),
    quoteCacheSeconds: ref(60),
    alertCooldownMinutes: ref(240),
    openAlertCreate: vi.fn(),
    openAlertEdit: vi.fn(),
    saveAlertRule: vi.fn(async () => {}),
    deleteAlertRule: vi.fn(async () => {}),
    toggleAlertEnabled: vi.fn(async () => {}),
    checkAlerts: vi.fn(async () => {}),
    fetchAlertEvents: vi.fn(async () => {}),
    exportAlertEvents: vi.fn(async () => {}),
    clearAlertEvents: vi.fn(async () => {}),
    addWatchlistRow: vi.fn(),
    removeWatchlistRow: vi.fn(),
    saveWatchlist: vi.fn(async () => {}),
    ...overrides,
  };
  return ctx;
}

/** 页面里所有区块标题（10 个） */
const BLOCK_TITLES = [
  '关键指标',
  '破线摘要',
  '市场与结论',
  '今日看点',
  '关键指数',
  '持仓今日贡献（粗估）',
  '自选关注',
  '价格预警规则',
  '最近一次检查触发',
  '预警历史',
];

const blockTitles = (host) => [...host.querySelectorAll('.section-title')]
  .map((el) => el.textContent.trim())
  .sort();

const groupTitles = (host) => [...host.querySelectorAll('.group-title')]
  .map((el) => el.textContent.trim());

const expandObserve = async (host, app) => {
  const header = host.querySelector('.stub-collapse-header');
  expect(header, '没有找到第三组的 el-collapse 标题栏').toBeTruthy();
  click(header);
  await flush();
  return header;
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('DecisionTab 三组结构', () => {
  it('① ② 默认展开可见，③ 观察与预警默认收起、内容不可见', async () => {
    const ctx = decisionCtx();
    const { host, app } = mountView(DecisionTab, ctx);
    await flush();

    const text = host.textContent;
    // 三组标题齐了
    expect(groupTitles(host)).toEqual(['今天该看什么', '我的持仓今天怎么样', '观察与预警']);
    // 第一屏就是「今天该做什么」
    expect(text).toContain('市场与结论');
    expect(text).toContain('今日看点');
    expect(text).toContain('关键指标');
    expect(text).toContain('破线摘要');
    expect(text).toContain('我的持仓今天怎么样');
    expect(text).toContain('持仓今日贡献（粗估）');
    // 第三组默认收起：内容没渲染，只有一行收起状态的标题
    expect(host.querySelector('.stub-collapse-content')).toBeNull();
    expect(host.querySelector('.observe-body')).toBeNull();
    for (const title of ['关键指数', '自选关注', '价格预警规则', '最近一次检查触发', '预警历史']) {
      expect(text, `第三组的「${title}」默认不该可见`).not.toContain(title);
    }
    // 第一屏顺序：今日看点排在持仓贡献之前
    expect(text.indexOf('今日看点')).toBeLessThan(text.indexOf('持仓今日贡献（粗估）'));

    app.unmount();
  });

  it('③ 点标题栏能展开，展开后预警规则 / 预警历史 / 关键指数 / 自选都出现', async () => {
    const ctx = decisionCtx();
    const { host, app } = mountView(DecisionTab, ctx);
    await flush();

    expect(host.textContent).not.toContain('价格预警规则');

    await expandObserve(host, app);

    const text = host.textContent;
    expect(host.querySelector('.observe-body')).toBeTruthy();
    expect(text).toContain('关键指数');
    expect(text).toContain('自选关注');
    expect(text).toContain('价格预警规则');
    expect(text).toContain('最近一次检查触发');
    expect(text).toContain('预警历史');
    // 表数据也真的渲染出来了（沿用 el-table 桩的 data 传递）
    expect(text).toContain('沪深300ETF 下穿 3.5');

    // 再点一次收起：内容重新不可见
    const header = host.querySelector('.stub-collapse-header');
    click(header);
    await flush();
    expect(host.querySelector('.observe-body')).toBeNull();
    expect(host.textContent).not.toContain('价格预警规则');

    app.unmount();
  });

  it('原有 10 个区块标题一个都没少（三组里正好这 10 个）', async () => {
    const ctx = decisionCtx();
    const { host, app } = mountView(DecisionTab, ctx);
    await flush();

    // 前两组里能看到 5 个（破线摘要需要真的有破线才渲染）
    expect(blockTitles(host)).toEqual(
      ['关键指标', '破线摘要', '市场与结论', '今日看点', '持仓今日贡献（粗估）'].sort(),
    );

    await expandObserve(host, app);
    expect(blockTitles(host)).toEqual([...BLOCK_TITLES].sort());

    app.unmount();
  });

  it('关键交互仍在：立即检查预警 → checkAlerts；保存自选 → saveWatchlist', async () => {
    const ctx = decisionCtx();
    const { host, app } = mountView(DecisionTab, ctx);
    await flush();

    const checkBtn = findButton(host, '立即检查预警');
    expect(checkBtn).toBeTruthy();
    click(checkBtn);
    await flush();
    expect(ctx.checkAlerts).toHaveBeenCalledTimes(1);
    expect(ctx.checkAlerts.mock.calls[0][0]).toBe(false);

    // 保存自选在第三组里 —— 折叠期间按钮不在 DOM，展开后才拿得到，点下去仍走 saveWatchlist
    expect(findButton(host, '保存自选')).toBeNull();
    await expandObserve(host, app);
    const saveBtn = findButton(host, '保存自选');
    expect(saveBtn, '展开第三组后应该有「保存自选」').toBeTruthy();
    click(saveBtn);
    await flush();
    expect(ctx.saveWatchlist).toHaveBeenCalledTimes(1);

    // 预警规则的新增/编辑入口也还在
    expect(findButton(host, '添加规则')).toBeTruthy();
    expect(findButton(host, '编辑')).toBeTruthy();

    app.unmount();
  });
});
