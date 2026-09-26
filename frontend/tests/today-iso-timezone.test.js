/**
 * todayIso 必须能在 getHealth 刷新时区后失效。
 * 旧实现是 computed(() => todayLocalIso())，没有响应式依赖，首次渲染会把上海日期锁死。
 */
import { describe, it, expect, vi } from 'vitest';
import { ref } from 'vue';
import { todayLocalIso } from '../src/utils/index.js';
import { createDataSync } from '../src/modules/dataSync.js';

vi.mock('../src/api/index.js', () => ({ default: {} }));
vi.mock('element-plus', () => ({
  ElLoading: { service: () => ({ close: () => {} }) },
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

const stubs = () => ({
  dashboard: ref({ latest_snapshot_date: null }),
  holdings: ref([]),
  deposits: ref([]),
  cashForm: ref({}),
  cashFlowForm: ref({}),
  activeFeeAccount: ref(''),
  syncing: ref(false),
  trailingSyncing: ref(false),
  syncNotice: ref(''),
  maintenanceStatus: ref({}),
  loadFeeSettingsToForm: () => {},
  calculateAllocationAnalysis: () => {},
  activeTab: ref(''),
  showSyncNotice: () => {},
  renderAllocationCharts: () => {},
});

describe('todayIso timezone refresh', () => {
  it('is a writable ref so refreshTodayIso can replace the cached date', () => {
    const ctx = stubs();
    const mod = createDataSync(ctx);
    mod.todayIso.value = '1999-01-01';
    expect(mod.todayIso.value).toBe('1999-01-01');
    ctx.dashboard.value.latest_snapshot_date = '1999-01-01';
    expect(mod.todaySnapshotDone.value).toBe(true);
    mod.refreshTodayIso();
    expect(mod.todayIso.value).toBe(todayLocalIso());
    expect(mod.todaySnapshotDone.value).toBe(false);
  });
});
