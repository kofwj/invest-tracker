/**
 * 切 tab 时同一接口被并发拉多次 —— 「同参数 in-flight Promise 复用」回归测试。
 *
 * main.js 的 watch(activeTab) 在 overview/decision/allocation 之间切换时会重复触发
 * refreshMarket / refreshDiscipline / fetchAllocationStory，同一 tick 内同一接口被
 * 拉两次。这里断言底层 api 只被调用一次，且参数不同不会被错误合并、失败不会被缓存。
 *
 * 注：fetchAlertEvents 的查询条件来自 alertEventCodeFilter 等 ref（模板里
 * @click="fetchAlertEvents" 会把事件对象当第一参数传入，所以函数签名不能加 params），
 * 所以「参数不同」用改 ref 的方式构造。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ref } from 'vue';

const mocks = vi.hoisted(() => ({
  api: {
    getMarketSummary: vi.fn(),
    listAlertRules: vi.fn(),
    listAlertEvents: vi.fn(),
    getDisciplineReport: vi.fn(),
    listDisciplineDrafts: vi.fn(),
    listDisciplinePresets: vi.fn(),
    allocationStory: vi.fn(),
  },
}));

vi.mock('../src/api/index.js', () => ({ default: mocks.api }));
vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), success: vi.fn(), warning: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: vi.fn() },
}));

import api from '../src/api/index.js';
import { createMarketModule } from '../src/modules/market.js';
import { createDisciplineModule } from '../src/modules/discipline.js';
import { createAllocationModule } from '../src/modules/allocation.js';

const deferred = () => {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
};

const makeMarket = () => {
  const marketSummary = ref({});
  const marketLoading = ref(false);
  const alertEventsLoading = ref(false);
  const alertEventCodeFilter = ref('');
  const mod = createMarketModule({
    marketSummary,
    alertRules: ref([]),
    alertEvents: ref([]),
    marketLoading,
    alertChecking: ref(false),
    alertEventsLoading,
    alertForm: ref({}),
    alertEditDialog: ref(false),
    triggeredAlerts: ref([]),
    alertEventCodeFilter,
    alertEventStartDate: ref(''),
    alertEventEndDate: ref(''),
    watchlistDraft: ref([]),
    watchlistSaving: ref(false),
  });
  return { ...mod, marketSummary, marketLoading, alertEventsLoading, alertEventCodeFilter };
};

const makeDiscipline = () => {
  const disciplineReport = ref({});
  const disciplineDrafts = ref([]);
  const disciplineLoading = ref(false);
  const disciplineDraftLoading = ref(false);
  const mod = createDisciplineModule({
    disciplineReport,
    disciplineDrafts,
    disciplinePolicy: ref({}),
    disciplineLoading,
    disciplineDraftLoading,
    disciplinePolicyDialog: ref(false),
    disciplineDraftEditDialog: ref(false),
    disciplineDraftEditForm: ref({}),
    disciplineSelectedDraftIds: ref([]),
    disciplinePresets: ref([]),
    disciplinePresetActiveId: ref(null),
    disciplinePresetLoading: ref(false),
  });
  return { ...mod, disciplineReport, disciplineDrafts, disciplineLoading, disciplineDraftLoading };
};

const makeAllocation = () => {
  const allocationStory = ref(null);
  const allocationStoryLoading = ref(false);
  const mod = createAllocationModule({
    holdings: ref([]),
    deposits: ref([]),
    dashboard: ref({}),
    pendingTransactions: ref([]),
    allocationAnalysis: ref([]),
    macroAllocationAnalysis: ref([]),
    portfolioExpectedReturn: ref(0),
    allocationStory,
    allocationStoryLoading,
  });
  return { ...mod, allocationStory, allocationStoryLoading };
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('market 模块去重', () => {
  it('同一 tick 并发 refreshMarket 两次：底层每个接口只调 1 次', async () => {
    const market = makeMarket();
    api.getMarketSummary.mockResolvedValue({ data: { watchlist: [] } });
    api.listAlertRules.mockResolvedValue({ data: [] });
    api.listAlertEvents.mockResolvedValue({ data: [] });

    await Promise.all([market.refreshMarket(), market.refreshMarket()]);

    expect(api.getMarketSummary).toHaveBeenCalledTimes(1);
    expect(api.listAlertRules).toHaveBeenCalledTimes(1);
    expect(api.listAlertEvents).toHaveBeenCalledTimes(1);
  });

  it('并发 fetchMarketSummary 两次复用同一个 Promise，loading 由发起方清理', async () => {
    const market = makeMarket();
    const d = deferred();
    api.getMarketSummary.mockReturnValue(d.promise);

    const p1 = market.fetchMarketSummary();
    const p2 = market.fetchMarketSummary();
    expect(api.getMarketSummary).toHaveBeenCalledTimes(1);
    // 复用方不能提前把 loading 置回 false，否则按钮会闪
    expect(market.marketLoading.value).toBe(true);

    d.resolve({ data: { watchlist: [{ code: '600000' }] } });
    await Promise.all([p1, p2]);

    expect(market.marketLoading.value).toBe(false);
    expect(market.marketSummary.value.watchlist[0].code).toBe('600000');
  });

  it('fetchAlertEvents 查询条件不同 → 各发一次请求', async () => {
    const market = makeMarket();
    api.listAlertEvents.mockResolvedValue({ data: [] });

    market.alertEventCodeFilter.value = '600000';
    const p1 = market.fetchAlertEvents();
    market.alertEventCodeFilter.value = '000001';
    const p2 = market.fetchAlertEvents();
    await Promise.all([p1, p2]);

    expect(api.listAlertEvents).toHaveBeenCalledTimes(2);
    expect(api.listAlertEvents.mock.calls[0][0].code).toBe('600000');
    expect(api.listAlertEvents.mock.calls[1][0].code).toBe('000001');
  });

  it('fetchAlertEvents 查询条件相同 → 只发一次请求', async () => {
    const market = makeMarket();
    api.listAlertEvents.mockResolvedValue({ data: [] });

    market.alertEventCodeFilter.value = '600000';
    await Promise.all([market.fetchAlertEvents(), market.fetchAlertEvents()]);

    expect(api.listAlertEvents).toHaveBeenCalledTimes(1);
  });

  it('失败不缓存：getMarketSummary reject 之后再调用会重新发请求', async () => {
    const market = makeMarket();
    api.getMarketSummary.mockRejectedValueOnce(new Error('boom'));

    await market.fetchMarketSummary();
    expect(api.getMarketSummary).toHaveBeenCalledTimes(1);
    // 失败后 loading 要归位，否则按钮一直转
    expect(market.marketLoading.value).toBe(false);

    api.getMarketSummary.mockResolvedValueOnce({ data: { watchlist: [{ code: '600519' }] } });
    await market.fetchMarketSummary();
    expect(api.getMarketSummary).toHaveBeenCalledTimes(2);
    expect(market.marketSummary.value.watchlist[0].code).toBe('600519');
  });
});

describe('discipline 模块去重', () => {
  it('同一 tick 并发 refreshDiscipline 两次：底层每个接口只调 1 次', async () => {
    const discipline = makeDiscipline();
    api.getDisciplineReport.mockResolvedValue({ data: {} });
    api.listDisciplineDrafts.mockResolvedValue({ data: [] });
    api.listDisciplinePresets.mockResolvedValue({ data: { presets: [], active_id: null } });

    await Promise.all([discipline.refreshDiscipline(), discipline.refreshDiscipline()]);

    expect(api.getDisciplineReport).toHaveBeenCalledTimes(1);
    expect(api.listDisciplineDrafts).toHaveBeenCalledTimes(1);
    expect(api.listDisciplinePresets).toHaveBeenCalledTimes(1);
  });

  it('并发 fetchDisciplineDrafts 两次：只调 1 次 api', async () => {
    const discipline = makeDiscipline();
    const d = deferred();
    api.listDisciplineDrafts.mockReturnValue(d.promise);

    const p1 = discipline.fetchDisciplineDrafts();
    const p2 = discipline.fetchDisciplineDrafts();
    expect(api.listDisciplineDrafts).toHaveBeenCalledTimes(1);
    expect(discipline.disciplineDraftLoading.value).toBe(true);

    d.resolve({ data: [{ id: 1 }] });
    await Promise.all([p1, p2]);

    expect(discipline.disciplineDraftLoading.value).toBe(false);
    expect(discipline.disciplineDrafts.value).toEqual([{ id: 1 }]);
  });

  it('失败不缓存：listDisciplineDrafts reject 之后再调用会重新发请求', async () => {
    const discipline = makeDiscipline();
    api.listDisciplineDrafts.mockRejectedValueOnce(new Error('boom'));

    await discipline.fetchDisciplineDrafts();
    expect(api.listDisciplineDrafts).toHaveBeenCalledTimes(1);

    api.listDisciplineDrafts.mockResolvedValueOnce({ data: [{ id: 7 }] });
    await discipline.fetchDisciplineDrafts();
    expect(api.listDisciplineDrafts).toHaveBeenCalledTimes(2);
    expect(discipline.disciplineDrafts.value).toEqual([{ id: 7 }]);
  });
});

describe('allocation 模块去重', () => {
  it('并发 fetchAllocationStory 两次：只调 1 次 api', async () => {
    const allocation = makeAllocation();
    const d = deferred();
    api.allocationStory.mockReturnValue(d.promise);

    const p1 = allocation.fetchAllocationStory();
    const p2 = allocation.fetchAllocationStory();
    expect(api.allocationStory).toHaveBeenCalledTimes(1);

    d.resolve({ data: { headline: 'ok' } });
    await Promise.all([p1, p2]);

    expect(allocation.allocationStory.value.headline).toBe('ok');
    expect(allocation.allocationStoryLoading.value).toBe(false);
  });
});
