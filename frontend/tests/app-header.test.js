/**
 * 顶栏导航回归测试。
 *
 * 背景：给顶栏「刷新」加 refreshCurrentTab 时，曾经把解构里的 goTab 覆盖掉，
 * 结果点击分组导航 / 品牌按钮时 goTab 是 undefined → 点了完全不跳转。
 * <script setup> 里未定义的标识符不会让 vite build 失败，所以只有行为测试能挡住。
 */
import { describe, it, expect, vi } from 'vitest';
import { createApp, h, provide, ref } from 'vue';
import AppHeader from '../src/components/AppHeader.vue';
import { APP_CTX_KEY } from '../src/composables/useAppCtx.js';
import { TAB_GROUPS } from '../src/modules/tabNav.js';

const passthrough = (name) => ({
  name,
  setup(_, { slots, attrs }) {
    return () => h('div', attrs, slots.default ? slots.default() : []);
  },
});

function makeCtx() {
  const goTab = vi.fn();
  const ctx = {
    authEnabled: ref(false),
    handleLogout: vi.fn(),
    syncing: ref(false),
    syncNotice: ref({ text: '', type: '' }),
    syncPrices: vi.fn(),
    fetchData: vi.fn(),
    refreshCurrentTab: vi.fn(async () => ({ failed: 0 })),
    themeMode: ref('system'),
    themeLabel: ref('跟随系统'),
    cycleThemeMode: vi.fn(),
    tabGroups: TAB_GROUPS,
    tabGroup: ref('home'),
    activeTab: ref('overview'),
    goTab,
  };
  return { ctx, goTab };
}

function mountHeader() {
  const { ctx, goTab } = makeCtx();
  const host = document.createElement('div');
  const App = { setup() { provide(APP_CTX_KEY, ctx); return () => h(AppHeader); } };
  const app = createApp(App);
  app.component('ElCard', passthrough('ElCard'));
  app.mount(host);
  return { host, app, ctx, goTab };
}

const findButton = (host, text) =>
  [...host.querySelectorAll('button')].find((b) => b.textContent.trim() === text);

describe('AppHeader 导航', () => {
  it('renders one nav button per tab group', () => {
    const { host, app } = mountHeader();
    for (const g of TAB_GROUPS) {
      expect(findButton(host, g.label)).toBeTruthy();
    }
    app.unmount();
  });

  it('clicking a group navigates to its first tab', () => {
    const { host, app, goTab } = mountHeader();
    const analysis = TAB_GROUPS.find((g) => g.label === '分析');
    findButton(host, '分析').click();
    expect(goTab).toHaveBeenCalledWith(analysis.tabs[0]);
    app.unmount();
  });

  it('clicking the brand goes back to overview', () => {
    const { host, app, goTab } = mountHeader();
    host.querySelector('.header-brand').click();
    expect(goTab).toHaveBeenCalledWith('overview');
    app.unmount();
  });

  it('does not navigate when clicking the group already active', () => {
    const { host, app, goTab } = mountHeader();
    findButton(host, '总览').click();
    expect(goTab).not.toHaveBeenCalled();
    app.unmount();
  });

  it('the refresh button refreshes the current tab, not just base data', async () => {
    const { host, app, ctx } = mountHeader();
    findButton(host, '刷新').click();
    await new Promise((r) => setTimeout(r, 10));
    expect(ctx.refreshCurrentTab).toHaveBeenCalled();
    app.unmount();
  });
});
