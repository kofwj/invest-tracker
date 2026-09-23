/**
 * 「今日（未收盘）」行的判定逻辑。
 *
 * 快照一天才写一条，所以逐日列表天然只到昨天；但 16:40 的定时任务跑完之后
 * 今天就有正式快照了，此时**不能再补一行假的今天**，否则列表里会出现两行今天。
 */
import { describe, it, expect } from 'vitest';
import { ref } from 'vue';
import { createPerformanceModule } from '../src/modules/performance.js';
import { todayLocalIso } from '../src/utils/index.js';

const TODAY = todayLocalIso();

function buildModule({ windows = [], timeline = [], totalAssets = 100000 } = {}) {
  return createPerformanceModule({
    perfSummary: ref({ total_assets: totalAssets }),
    perfTimeline: ref(timeline),
    perfContribution: ref([]),
    perfFlows: ref([]),
    perfStory: ref(null),
    perfLoading: ref(false),
    perfContributionFilter: ref('all'),
    perfContributionSort: ref('contribution'),
    perfTimelineRange: ref('all'),
    perfWindows: ref(windows),
    perfFlowForm: ref({}),
    showSyncNotice: () => {},
    nextTick: (fn) => (fn ? fn() : undefined),
  });
}

const todayWindow = (extra = {}) => ({
  key: 'today', label: '今天', gain: 1234.5, gain_pct: 0.42,
  start_date: '2026-09-22', stale_days: 1, ...extra,
});

describe('perfTodayRow', () => {
  it('今天还没有快照时补一行「今日（未收盘）」', () => {
    const mod = buildModule({ windows: [todayWindow()], timeline: [{ date: '2026-09-22', total_assets: 1 }] });
    const row = mod.perfTodayRow.value;
    expect(row).toBeTruthy();
    expect(row.isToday).toBe(true);
    expect(row.date).toBe(TODAY);
    expect(row.change).toBe(1234.5);
    expect(row.baseDate).toBe('2026-09-22');
    expect(row.stale).toBe(false);
  });

  it('今天已经有正式快照时不再补，避免出现两行今天', () => {
    const mod = buildModule({
      windows: [todayWindow()],
      timeline: [{ date: '2026-09-22', total_assets: 1 }, { date: TODAY, total_assets: 2 }],
    });
    expect(mod.perfTodayRow.value).toBeNull();
  });

  it('今天窗口拿不到收益时不伪造', () => {
    const mod = buildModule({ windows: [todayWindow({ gain: null, gain_pct: null })], timeline: [] });
    expect(mod.perfTodayRow.value).toBeNull();
  });

  it('基准快照不是上一交易日时带上跨度，让界面转警告色', () => {
    const mod = buildModule({
      windows: [todayWindow({ start_date: '2026-08-02', stale_days: 52 })],
      timeline: [{ date: '2026-08-02', total_assets: 1 }],
    });
    const row = mod.perfTodayRow.value;
    expect(row.stale).toBe(true);
    expect(row.daysGap).toBe(52);
    expect(row.baseDate).toBe('2026-08-02');
  });
});
