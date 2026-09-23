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

const STUBS = {
  ElCard: passthrough('ElCard'), ElTabs: ElTabsStub, ElTabPane: ElTabPaneStub,
  ElRow: passthrough('ElRow'), ElCol: passthrough('ElCol'),
  ElTable: ElTableStub, ElTableColumn: ElTableColumnStub, ElTag: passthrough('ElTag'),
  ElButton: passthrough('ElButton'), ElDialog: passthrough('ElDialog'),
  ElAlert: passthrough('ElAlert'), ElCollapse: passthrough('ElCollapse'),
  ElCollapseItem: passthrough('ElCollapseItem'), ElSelect: passthrough('ElSelect'),
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
