/**
 * fetchPerformance 的 silent 选项。
 *
 * 首页（总览）第一段要用「今日盈亏/本月/今年」，那几张卡的数据来自 performance 模块，
 * 所以停在总览时也要拉一次 —— 但那边不该弹「收益分析已刷新」这种收益分析的提示。
 * 失败提示不受 silent 影响（失败了要让人知道）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ref } from 'vue';
import { createPerformanceModule } from '../src/modules/performance.js';

const ok = (data = {}) => Promise.resolve({ data });
const apiMock = vi.hoisted(() => ({
  performanceSummary: vi.fn(),
  performanceTimeline: vi.fn(),
  performanceContribution: vi.fn(),
  listPortfolioCashFlows: vi.fn(),
  performanceStory: vi.fn(),
  performanceWindows: vi.fn(),
}));

vi.mock('../src/api/index.js', () => ({ default: apiMock }));

function build(showSyncNotice) {
  return createPerformanceModule({
    perfSummary: ref(null),
    perfTimeline: ref([]),
    perfContribution: ref([]),
    perfFlows: ref([]),
    perfStory: ref(null),
    perfLoading: ref(false),
    perfContributionFilter: ref('all'),
    perfContributionSort: ref('contribution'),
    perfTimelineRange: ref('all'),
    perfWindows: ref([]),
    perfFlowForm: ref({}),
    showSyncNotice,
    nextTick: (fn) => (fn ? fn() : undefined),
  });
}

beforeEach(() => {
  for (const fn of Object.values(apiMock)) fn.mockReset();
  for (const fn of Object.values(apiMock)) fn.mockImplementation(() => ok({}));
});

describe('fetchPerformance 的 silent', () => {
  it('silent=true 时不弹「收益分析已刷新」的成功提示', async () => {
    const notice = vi.fn();
    const mod = build(notice);
    await mod.fetchPerformance({ silent: true });
    expect(notice).not.toHaveBeenCalled();
  });

  it('默认（不传）仍会弹成功提示，保持手动刷新与页内按钮的原有行为', async () => {
    const notice = vi.fn();
    const mod = build(notice);
    await mod.fetchPerformance();
    expect(notice).toHaveBeenCalledWith('收益分析已刷新', 'success');
  });

  it('silent=true 时失败仍然提示（不能把失败静音掉）', async () => {
    apiMock.performanceWindows.mockImplementation(() => Promise.reject(new Error('504')));
    const notice = vi.fn();
    const mod = build(notice);
    await mod.fetchPerformance({ silent: true });
    const errorCalls = notice.mock.calls.filter(([, type]) => type === 'error');
    expect(errorCalls.length).toBe(1);
    expect(String(errorCalls[0][0])).toContain('时间轴收益尺');
  });

  it('把点击事件当参数传进来（@click="fetchPerformance"）不会被当成 silent', async () => {
    const notice = vi.fn();
    const mod = build(notice);
    await mod.fetchPerformance({ type: 'click' }); // 真实的 MouseEvent 就是这样
    expect(notice).toHaveBeenCalledWith('收益分析已刷新', 'success');
  });
});
