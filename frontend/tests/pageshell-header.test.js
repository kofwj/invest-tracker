/**
 * 页头合并成一行（子导航 + 页面操作）的行为测试。
 *
 * 改之前：第 2 行是子导航 tab（收益分析），第 3 行是页面标题（收益分析）——同一个词连出两行。
 * 现在标题降级为屏幕阅读器专用的隐藏 h1，tab 与 actions 同处 .page-shell-header 一行。
 * 静态测试只能查"没再传 title"，这里真挂一次组件，确认 DOM 上确实是一行、点击能跳转。
 */
import { describe, it, expect, vi } from 'vitest';
import { createApp, h, provide, ref } from 'vue';
import PageShell from '../src/components/PageShell.vue';
import { APP_CTX_KEY } from '../src/composables/useAppCtx.js';
import { TAB_GROUPS, tabLabel } from '../src/modules/tabNav.js';

function mountShell({ tabGroups = TAB_GROUPS } = {}) {
  const goTab = vi.fn();
  const activeTab = ref('performance');
  const ctx = { tabGroups, tabGroup: ref('analysis'), activeTab, goTab };
  const host = document.createElement('div');
  const App = {
    setup() {
      provide(APP_CTX_KEY, ctx);
      return () => h(PageShell, null, { actions: () => h('button', { class: 'act' }, '动作') });
    },
  };
  const app = createApp(App);
  app.mount(host);
  return { host, app, goTab, activeTab };
}

const analysisTabs = TAB_GROUPS.find((g) => g.id === 'analysis').tabs;

describe('PageShell 一行式页头', () => {
  it('tab 列表与页面操作在同一个页头容器里（不再占两行）', () => {
    const { host, app } = mountShell();
    const header = host.querySelector('.page-shell-header');
    expect(header).toBeTruthy();
    expect(header.querySelector('.page-tabs')).toBeTruthy();
    expect(header.querySelector('.page-shell-actions')).toBeTruthy();
    // 两者必须是同一个页头的直接子节点，而不是分处两个容器
    const tabs = header.querySelector('.page-tabs');
    const actions = header.querySelector('.page-shell-actions');
    expect(tabs.parentElement).toBe(header);
    expect(actions.parentElement).toBe(header);
    app.unmount();
  });

  it('渲染当前分组的全部 tab，顺序与分组定义一致，当前页高亮', () => {
    const { host, app } = mountShell();
    const labels = [...host.querySelectorAll('.page-tab')].map((b) => b.textContent.trim());
    expect(labels).toEqual(analysisTabs.map((t) => tabLabel(t)));
    const active = host.querySelector('.page-tab.active');
    expect(active.textContent.trim()).toBe('收益与快照');
    app.unmount();
  });

  it('资产快照已并入「收益与快照」：不再是独立 tab，点它跳 performance', () => {
    const { host, app, goTab } = mountShell();
    const labels = [...host.querySelectorAll('.page-tab')].map((b) => b.textContent.trim());
    // 分析组收敛：资产快照并入收益与快照、K 线降级为持仓页弹窗
    expect(labels).not.toContain('资产快照');
    expect(labels).not.toContain('K线查询');
    expect(labels).toContain('收益与快照');
    host.querySelectorAll('.page-tab')[labels.indexOf('收益与快照')].click();
    expect(goTab).toHaveBeenCalledWith('performance');
    app.unmount();
  });

  it('当前页名仍以隐藏 h1 保留（无障碍与语义不丢，但不占一行）', () => {
    const { host, app } = mountShell();
    const h1 = host.querySelector('h1');
    expect(h1).toBeTruthy();
    expect(h1.textContent.trim()).toBe('收益与快照');
    expect(h1.className).toContain('visually-hidden');
    app.unmount();
  });

  it('单页分组不渲染 tab 行，但有 actions 时页头仍然存在', () => {
    const host = document.createElement('div');
    const App = {
      setup() {
        provide(APP_CTX_KEY, {
          tabGroups: [{ id: 'home', label: '总览', tabs: ['overview'] }],
          tabGroup: ref('home'),
          activeTab: ref('overview'),
          goTab: vi.fn(),
        });
        return () => h(PageShell, null, { actions: () => h('button', '动作') });
      },
    };
    const app = createApp(App);
    app.mount(host);
    expect(host.querySelector('.page-tabs')).toBeNull();
    // 页头不能因为少了 title/tab 就整块消失（否则 actions 也没了）
    expect(host.querySelector('.page-shell-header')).toBeTruthy();
    app.unmount();
  });

  it('ctx 里没有 tabGroups 时不抛错、也不渲染 tab 行', () => {
    const host = document.createElement('div');
    const App = {
      setup() {
        provide(APP_CTX_KEY, { activeTab: ref('performance'), goTab: vi.fn() });
        return () => h(PageShell, null, { actions: () => h('button', '动作') });
      },
    };
    const app = createApp(App);
    app.mount(host);
    expect(host.querySelector('.page-tabs')).toBeNull();
    expect(host.textContent).toContain('动作');
    app.unmount();
  });
});
