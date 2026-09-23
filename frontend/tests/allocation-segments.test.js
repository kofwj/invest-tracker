/**
 * 「结构与目标」页拆成三段（看现状 / 设目标 / 处理偏离）的行为测试。
 *
 * 改之前这页 15 个卡片堆在一起，要滚很久才能找到想改的那块。
 * 这里真挂组件 + 用会"只渲染激活 pane"的 el-tabs/el-tab-pane 桩，断言：
 * 默认停在哪一段、切段真的换内容、三段合起来没丢任何原区块、?seg= 能直接落地。
 */
import { describe, it, expect, vi } from 'vitest';
import { createApp, h, provide, inject, computed, ref, nextTick } from 'vue';
import AllocationTab from '../src/views/AllocationTab.vue';
import { APP_CTX_KEY } from '../src/composables/useAppCtx.js';

vi.mock('../src/charts/index.js', () => ({
  renderAllocationChartsView: () => true,
  renderSnapshotChartsView: () => true,
  renderOverviewWeekChartView: () => true,
  renderDailyPnlChartView: () => true,
  renderKlineChartView: () => {},
  analyzeKlineTrend: () => ({ points: [] }),
  waitForChartDom: async () => true,
  resizeAllCharts: () => {},
  readTheme: () => ({}),
}));

// 透传桩：渲染所有插槽（本页大量使用 #header 具名插槽）
const passthrough = (name) => ({
  name,
  props: { header: { type: String, default: '' } },
  setup(props, { slots, attrs }) {
    return () => h('div', attrs, [
      // header 是 prop（不是插槽），要显式渲染成文本，否则断言看不到卡片标题
      props.header ? h('div', { class: 'stub-card-header' }, props.header) : null,
      slots.header ? slots.header() : null,
      slots.default ? slots.default() : null,
    ]);
  },
});

// el-tabs / el-tab-pane：只渲染激活 pane 的内容（真组件就是这个行为）
const TABS_ACTIVE = Symbol('tabs-active');
const TABS_SET = Symbol('tabs-set');
const ElTabsStub = {
  name: 'ElTabs',
  props: { modelValue: { type: String, default: '' } },
  emits: ['update:modelValue'],
  setup(props, { slots, emit }) {
    provide(TABS_ACTIVE, computed(() => props.modelValue));
    provide(TABS_SET, (v) => emit('update:modelValue', v));
    return () => h('div', { class: 'stub-tabs' }, slots.default ? slots.default() : []);
  },
};
const ElTabPaneStub = {
  name: 'ElTabPane',
  props: { name: { type: String, default: '' }, label: { type: String, default: '' } },
  setup(props, { slots }) {
    const active = inject(TABS_ACTIVE, computed(() => ''));
    const set = inject(TABS_SET, () => {});
    return () => h('div', { class: 'stub-pane' }, [
      h('button', { class: 'stub-tab', 'data-name': props.name, onClick: () => set(props.name) }, props.label),
      active.value === props.name
        ? h('div', { class: 'stub-pane-body' }, slots.default ? slots.default() : [])
        : null,
    ]);
  },
};

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
  props: { label: { type: String, default: '' }, prop: { type: String, default: '' } },
  setup(props, { slots }) {
    const rows = inject(TABLE_ROWS, null);
    return () => h('div', { class: 'stub-col', 'data-label': props.label },
      (rows ? rows.value : []).map((row, $index) => h('div', { class: 'stub-cell' },
        slots.default ? slots.default({ row, $index }) : String(row[props.prop] ?? ''))));
  },
};

// el-collapse / el-collapse-item：真组件折叠时用 v-show 藏内容，桩里直接「折叠就不渲染」，
// 这样「默认收起 → 内容不在可见 DOM 里」在测试里是真的可观察（与 decision-groups.test.js 同一套桩）。
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
      h('div', {
        class: 'stub-collapse-header',
        onClick: () => state && state.toggle(props.name),
      }, slots.title ? slots.title() : []),
      state && state.isOpen(props.name)
        ? h('div', { class: 'stub-collapse-content' }, slots.default ? slots.default() : [])
        : null,
    ]);
  },
};

const STUBS = {
  ElCard: passthrough('ElCard'), ElTabs: ElTabsStub, ElTabPane: ElTabPaneStub,
  ElRow: passthrough('ElRow'), ElCol: passthrough('ElCol'),
  ElTable: ElTableStub, ElTableColumn: ElTableColumnStub, ElTag: passthrough('ElTag'),
  ElButton: passthrough('ElButton'), ElDialog: passthrough('ElDialog'),
  ElAlert: passthrough('ElAlert'), ElCollapse: ElCollapseStub, ElCollapseItem: ElCollapseItemStub,
  ElSelect: passthrough('ElSelect'),
  ElOption: passthrough('ElOption'), ElInput: passthrough('ElInput'),
  ElInputNumber: passthrough('ElInputNumber'), ElProgress: passthrough('ElProgress'),
  ElTooltip: passthrough('ElTooltip'), ElRadioGroup: passthrough('ElRadioGroup'),
  ElRadioButton: passthrough('ElRadioButton'), ElForm: passthrough('ElForm'),
  ElFormItem: passthrough('ElFormItem'), ElDivider: passthrough('ElDivider'),
};

function makeCtx() {
  const noop = vi.fn();
  return {
    dashboard: ref({ total_assets: 100000 }),
    allocationAnalysis: ref([]),
    macroAllocationAnalysis: ref([]),
    allocationSummary: ref(null),
    allocationHealth: ref(null),
    portfolioExpectedReturn: ref(0),
    allocationStory: ref(null),
    allocationStoryLoading: ref(false),
    fetchAllocationStory: noop,
    formatMoney: (v) => `¥${Number(v || 0).toFixed(2)}`,
    disciplineDrafts: ref([]),
    disciplinePolicy: ref({ focus: {}, plans: {}, defensive_extra_categories: [] }),
    disciplineLoading: ref(false),
    disciplineDraftLoading: ref(false),
    disciplinePolicyDialog: ref(false),
    disciplineDraftEditDialog: ref(false),
    disciplineDraftEditForm: ref({}),
    refreshDiscipline: noop,
    openPolicyDialog: noop,
    cancelPolicy: noop,
    savePolicy: noop,
    greeReducePct: ref(0),
    createDraftsFromReport: noop,
    openDraftEdit: noop,
    saveDraftEdit: noop,
    deleteDraft: noop,
    confirmDraft: noop,
    confirmSelectedDrafts: noop,
    onDraftSelectionChange: noop,
    fetchDisciplineDrafts: noop,
    disciplinePresets: ref([]),
    disciplinePresetActiveId: ref(''),
    disciplinePresetLoading: ref(false),
    applyDisciplinePreset: noop,
    breaches: ref([]),
    actions: ref([]),
    planItems: ref([]),
    snapshot: ref(null),
    targets: ref([]),
    summaryText: ref(''),
    resolvedTheme: ref('light'),
  };
}

function mountTab(ctx = makeCtx()) {
  const host = document.createElement('div');
  const App = { setup() { provide(APP_CTX_KEY, ctx); return () => h(AllocationTab); } };
  const app = createApp(App);
  for (const [name, comp] of Object.entries(STUBS)) app.component(name, comp);
  app.mount(host);
  return { host, app };
}

const bodyText = (host) => (host.querySelector('.stub-pane-body') || { textContent: '' }).textContent;
// Vue 的更新是异步的：点完必须等一次 nextTick，否则读到的是切换前的 DOM
const clickSeg = async (host, name) => {
  host.querySelector(`.stub-tab[data-name="${name}"]`).click();
  await nextTick();
};

describe('结构与目标页的三段', () => {
  it('渲染三个段按钮，默认停在「看现状」', () => {
    const { host, app } = mountTab();
    const tabs = [...host.querySelectorAll('.stub-tab')].map((b) => b.textContent.trim());
    expect(tabs).toEqual(['看现状', '设目标', '处理偏离']);
    expect(host.querySelector('.stub-pane-body')).toBeTruthy();
    // ① 里的区块在，②③ 的不在
    expect(bodyText(host)).toContain('配置结论');
    expect(bodyText(host)).toContain('配置健康检查');
    expect(bodyText(host)).not.toContain('目标尺子');
    expect(bodyText(host)).not.toContain('纪律草稿');
    app.unmount();
  });

  it('切到「设目标」后换内容', async () => {
    const { host, app } = mountTab();
    await clickSeg(host, 'target');
    expect(bodyText(host)).toContain('目标尺子');
    expect(bodyText(host)).not.toContain('配置结论');
    app.unmount();
  });

  it('切到「处理偏离」能看到偏离与明细', async () => {
    const { host, app } = mountTab();
    await clickSeg(host, 'deviation');
    const t = bodyText(host);
    expect(t).toContain('纪律检查');
    expect(t).toContain('再平衡建议');
    expect(t).toContain('细分类别明细');
    expect(t).toContain('纪律草稿');
    expect(t).not.toContain('配置健康检查');
    app.unmount();
  });

  it('三段合起来没有丢任何原区块', async () => {
    const { host, app } = mountTab();
    const seen = new Set();
    for (const seg of ['overview', 'target', 'deviation']) {
      await clickSeg(host, seg);
      // 注意：『问题清单』『个人计划』两张卡带 v-if（无数据不渲染），空 ctx 下本来就不出现，
      // 所以这里只校验无条件渲染的区块标题。
      for (const title of ['配置结论', '当前结构', '权益情景粗估', '目标与纪律', '目标尺子',
        '纪律检查', '再平衡建议', '细分类别明细', '纪律草稿']) {
        if (bodyText(host).includes(title)) seen.add(title);
      }
    }
    expect([...seen]).toEqual(expect.arrayContaining([
      '配置结论', '当前结构', '权益情景粗估',     // ①
      '目标与纪律', '目标尺子',                    // ②
      '纪律检查', '再平衡建议', '细分类别明细', '纪律草稿', // ③
    ]));
    app.unmount();
  });

  it('?seg=target 直接落到「设目标」', () => {
    window.history.replaceState({}, '', '/allocation?seg=target');
    const { host, app } = mountTab();
    expect(bodyText(host)).toContain('目标尺子');
    expect(bodyText(host)).not.toContain('配置结论');
    app.unmount();
    window.history.replaceState({}, '', '/allocation');
  });

  it('切段时把 seg 同步进 URL（replaceState，不新增历史）', async () => {
    window.history.replaceState({}, '', '/allocation');
    const before = window.history.length;
    const { host, app } = mountTab();
    await clickSeg(host, 'deviation');
    expect(window.location.search).toBe('?seg=deviation');
    expect(window.history.length).toBe(before);
    app.unmount();
    window.history.replaceState({}, '', '/allocation');
  });
});

/* ===== 批次 C：③「处理偏离」段内排优先级 + 段尾折叠 =====
   这一段原有 6 个区块平铺，最该动手的混在明细里。现在把它们分开：
   纪律检查 / 问题清单（+ 个人计划）/ 再平衡建议 排在前面（默认可见），
   细分类别明细与纪律草稿折到段尾并默认收起 —— 只动顺序与折叠，区块、绑定、文案一个没改。 */

/** 本页原有 10 个区块标题（名单：布局整改计划里列的 8 个 + 后来补的纪律检查、细分类别明细） */
const BLOCK_TITLES = [
  '配置结论', '当前结构', '权益情景粗估',                                  // ① 看现状
  '目标与纪律', '目标尺子',                                               // ② 设目标
  '纪律检查', '个人计划', '再平衡建议', '细分类别明细', '纪律草稿',        // ③ 处理偏离
];

/** 有数据的 ctx：③ 段的「问题清单」「个人计划」带 v-if，空数据下根本不渲染 */
function deviationCtx() {
  const ctx = makeCtx();
  ctx.allocationStory = ref({
    headline: '权益偏高，先减一点',
    bullets: [],
    issues: [
      { id: 'i1', level: 'warning', title: '权益超出带宽', text: '权益 52.0% 高于上限 48%', action_hint: '减宽基' },
      { id: 'i2', level: 'warning', title: '单票集中', text: '格力占比 12%', action_hint: '分批减' },
      { id: 'i3', level: 'warning', title: '现金偏低', text: '证券现金 < 5%', action_hint: '留一点' },
      { id: 'i4', level: 'info', title: '卫星仓未到位', text: '510880 只到 3%', action_hint: '继续加' },
    ],
    scenarios: [{ label: '权益 -10%', estimated_pnl: -5200, estimated_total_assets: 94800 }],
  });
  ctx.breaches = ref([
    { level: 'warning', title: '权益超上限', text: '52.0% > 48.0%' },
    { level: 'ok', title: '固收正常', text: '在带宽内' },
  ]);
  ctx.actions = ref([{ side: 'sell', name: '沪深300ETF', code: '510300', amount: 10000, reason: '超出带宽' }]);
  ctx.planItems = ref([{
    title: 'A500 分批', level: 'info', text: '还差 8 万', target_amount: 200000,
    progress_pct: 60, remaining_amount: 80000, suggested_next_amount: 20000,
  }]);
  ctx.allocationAnalysis = ref([{ category: '权益', market_value: 52000, percentage: 52, count: 3 }]);
  ctx.disciplineDrafts = ref([{
    id: 1, side: 'sell', name: '沪深300ETF', code: '510300',
    amount: 10000, quantity: 1000, reason: '超出带宽', created_at: '2026-03-06',
  }]);
  return ctx;
}

/** 段尾两个折叠块的标题栏 */
const tailHeaders = (host) => [...host.querySelectorAll('.stub-collapse-header')];

describe('③ 处理偏离：段内顺序 + 段尾折叠', () => {
  it('要动手的三块排在 细分类别明细 / 纪律草稿 之前', async () => {
    const { host, app } = mountTab(deviationCtx());
    await clickSeg(host, 'deviation');

    const text = bodyText(host);
    for (const title of ['纪律检查', '问题清单', '再平衡建议']) {
      expect(text, `③ 段里没有渲染「${title}」`).toContain(title);
      expect(text.indexOf(title)).toBeLessThan(text.indexOf('细分类别明细（点开看）'));
      expect(text.indexOf(title)).toBeLessThan(text.indexOf('纪律草稿（点开看）'));
    }
    // DOM 顺序同样成立：三块"要动手的"都在段内 pane 里，折叠块是段内最后一个元素
    const body = host.querySelector('.stub-pane-body');
    const pane = body.querySelector('.merge-pane');
    expect(pane.textContent).toContain('纪律检查');
    expect(pane.textContent).toContain('问题清单');
    expect(pane.textContent).toContain('再平衡建议');
    expect(pane.textContent).not.toContain('细分类别明细');
    expect(body.lastElementChild).toBe(body.querySelector('.stub-collapse'));

    app.unmount();
  });

  it('细分类别明细 / 纪律草稿默认收起，点开后才出现', async () => {
    const { host, app } = mountTab(deviationCtx());
    await clickSeg(host, 'deviation');

    expect(tailHeaders(host).map((el) => el.textContent.trim())).toEqual([
      '细分类别明细（点开看）', '纪律草稿（点开看）',
    ]);
    // 默认收起：两块的内容（两张表）根本不在 DOM 里，页面上只剩标题一行
    expect(host.querySelectorAll('.stub-collapse-content').length).toBe(0);
    expect(host.querySelector('[aria-label="细分类别明细"]')).toBeNull();
    expect(host.querySelector('[aria-label="纪律草稿"]')).toBeNull();
    expect(bodyText(host)).toContain('细分类别明细（点开看）');

    // 点开第一块：细分类别明细的表出现，纪律草稿仍然收起
    tailHeaders(host)[0].click();
    await nextTick();
    expect(host.querySelector('[aria-label="细分类别明细"]')).toBeTruthy();
    expect(host.querySelector('[aria-label="纪律草稿"]')).toBeNull();

    // 再点开第二块：纪律草稿的表也出现
    tailHeaders(host)[1].click();
    await nextTick();
    expect(host.querySelector('[aria-label="纪律草稿"]')).toBeTruthy();

    app.unmount();
  });

  it('三段合起来仍是原来那 10 个区块标题（防搬丢）', async () => {
    const { host, app } = mountTab(deviationCtx());
    const seen = new Set();
    for (const name of ['overview', 'target', 'deviation']) {
      await clickSeg(host, name);
      const text = bodyText(host);
      for (const title of BLOCK_TITLES) if (text.includes(title)) seen.add(title);
    }
    expect([...seen].sort()).toEqual([...BLOCK_TITLES].sort());
    expect(BLOCK_TITLES.length).toBe(10);

    app.unmount();
  });
});
