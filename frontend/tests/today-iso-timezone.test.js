/**
 * todayIso 必须能在 getHealth 刷新时区后失效。
 * 旧实现是 computed(() => todayLocalIso())，没有响应式依赖，首次渲染会把上海日期锁死。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { setActivePinia, createPinia } from 'pinia';
import { todayLocalIso } from '../src/utils/index.js';
import { usePortfolioStore } from '../src/stores/portfolio.js';

vi.mock('../src/api/index.js', () => ({ default: {} }));
vi.mock('element-plus', () => ({
  ElLoading: { service: () => ({ close: () => {} }) },
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

describe('todayIso timezone refresh', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it('is a writable ref so refreshTodayIso can replace the cached date', () => {
    const portfolioStore = usePortfolioStore();
    portfolioStore.todayIso = '1999-01-01';
    expect(portfolioStore.todayIso).toBe('1999-01-01');
    portfolioStore.dashboard = { latest_snapshot_date: '1999-01-01' };
    expect(portfolioStore.todaySnapshotDone).toBe(true);
    portfolioStore.refreshTodayIso();
    expect(portfolioStore.todayIso).toBe(todayLocalIso());
    expect(portfolioStore.todaySnapshotDone).toBe(false);
  });
});
