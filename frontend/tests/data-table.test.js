/**
 * DataTable 基础件：宽屏原样透传、窄屏换成卡片、没给卡片就退回现状。
 *
 * jsdom 里没有 `window.matchMedia`，而 `useMediaQuery` 是在 setup 里同步读值的，
 * 所以必须在挂载之前把 stub 装好。stub 也负责发 change 事件，用来模拟手机横竖屏
 * 切换后 DOM 真的换掉（而不是留着两份）。
 */
import { describe, it, expect, afterEach, beforeEach } from 'vitest';
import { createApp, h, nextTick } from 'vue';
import DataTable from '../src/components/DataTable.vue';
import { cardKeyOf, CARD_QUERY } from '../src/modules/dataTable.js';

let host = null;
let app = null;
let restoreMatchMedia = null;

/** 装一个可控的 matchMedia；返回 restore 与手动触发 change 的 emit */
function stubMatchMedia(initial) {
  const had = 'matchMedia' in window;
  const original = window.matchMedia;
  const listeners = new Set();
  const mediaQuery = {
    media: CARD_QUERY,
    matches: initial,
    onchange: null,
    addEventListener(type, handler) {
      if (type === 'change') listeners.add(handler);
    },
    removeEventListener(type, handler) {
      if (type === 'change') listeners.delete(handler);
    },
    addListener(handler) {
      listeners.add(handler);
    },
    removeListener(handler) {
      listeners.delete(handler);
    },
    dispatchEvent: () => true,
  };
  window.matchMedia = () => mediaQuery;
  return {
    emit(matches) {
      mediaQuery.matches = matches;
      for (const handler of [...listeners]) handler({ matches, media: CARD_QUERY });
    },
    restore() {
      if (had) window.matchMedia = original;
      else delete window.matchMedia;
    },
  };
}

function mountTable(props, slots) {
  host = document.createElement('div');
  document.body.appendChild(host);
  app = createApp({ render: () => h(DataTable, props, slots) });
  // 生产里 v-loading 由 unplugin-vue-components 按需注册；测试环境没有插件，
  // 用同样的形状记一笔，好断言它挂在外壳而不是 el-table 上。
  app.directive('loading', {
    mounted(el, binding) {
      el.dataset.loading = String(binding.value);
    },
    updated(el, binding) {
      el.dataset.loading = String(binding.value);
    },
  });
  app.component('el-empty', {
    props: { description: { type: String, default: '' } },
    render() {
      return h('div', { class: 'empty-stub' }, this.description);
    },
  });
  app.mount(host);
  return host;
}

beforeEach(() => {
  restoreMatchMedia = null;
});

afterEach(() => {
  if (app) app.unmount();
  if (host) host.remove();
  app = null;
  host = null;
  if (restoreMatchMedia) restoreMatchMedia.restore();
  restoreMatchMedia = null;
});

const rows = [
  { code: '600519', name: '贵州茅台' },
  { code: '000001', name: '平安银行' },
];

describe('DataTable 宽屏', () => {
  it('原样渲染默认插槽，不渲染卡片', () => {
    restoreMatchMedia = stubMatchMedia(false);
    const host = mountTable({ rows }, {
      default: () => h('table', { class: 'wide' }, '表格'),
      card: () => h('div', { class: 'card-body' }, '卡片'),
    });
    expect(host.querySelector('.wide')).toBeTruthy();
    expect(host.querySelector('.data-card')).toBeNull();
    expect(host.querySelector('.data-table-cards')).toBeNull();
  });

  it('加载态挂在外壳容器上（宽屏只挂一次，不会叠两层遮罩）', () => {
    restoreMatchMedia = stubMatchMedia(false);
    const host = mountTable({ rows, loading: true }, { default: () => h('table') });
    const shells = host.querySelectorAll('.data-table');
    expect(shells).toHaveLength(1);
    expect(shells[0].dataset.loading).toBe('true');
  });
});

describe('DataTable 窄屏', () => {
  it('有 #card 时按行渲染卡片，默认插槽整体卸载', () => {
    restoreMatchMedia = stubMatchMedia(true);
    const host = mountTable({ rows, label: '持仓明细' }, {
      default: () => h('table', { class: 'wide' }),
      card: ({ row }) => h('span', { class: 'card-name' }, row.name),
    });
    expect(host.querySelector('.wide')).toBeNull();
    const cards = host.querySelectorAll('.data-card');
    expect(cards).toHaveLength(rows.length);
    expect(host.querySelector('.card-name').textContent).toBe('贵州茅台');
    expect(host.querySelector('.data-table-cards').getAttribute('aria-label')).toBe('持仓明细');
  });

  it('没给 #card 就退回表格（等于改造前的横向滚动）', () => {
    restoreMatchMedia = stubMatchMedia(true);
    const host = mountTable({ rows }, { default: () => h('table', { class: 'wide' }) });
    expect(host.querySelector('.wide')).toBeTruthy();
    expect(host.querySelector('.data-card')).toBeNull();
  });

  it('没有数据时显示空态文案，不渲染空卡片', () => {
    restoreMatchMedia = stubMatchMedia(true);
    const host = mountTable({ rows: [], emptyText: '暂无持仓' }, {
      card: () => h('div', { class: 'card-body' }),
    });
    expect(host.querySelectorAll('.data-card')).toHaveLength(0);
    expect(host.querySelector('.empty-stub').textContent).toBe('暂无持仓');
  });

  it('视口变宽后卡片卸载、表格回来（DOM 只有一份）', async () => {
    restoreMatchMedia = stubMatchMedia(true);
    const host = mountTable({ rows }, {
      default: () => h('table', { class: 'wide' }),
      card: () => h('div', { class: 'card-body' }),
    });
    expect(host.querySelector('.data-card')).toBeTruthy();

    restoreMatchMedia.emit(false);
    await nextTick();

    expect(host.querySelector('.data-card')).toBeNull();
    expect(host.querySelector('.wide')).toBeTruthy();
  });
});

describe('卡片 row-key', () => {
  it('字符串按字段取值、函数直接调用、没给就退回索引', () => {
    expect(cardKeyOf({ code: '600519' }, 0, 'code')).toBe('600519');
    expect(cardKeyOf({ code: '600519' }, 2, (row) => `k-${row.code}`)).toBe('k-600519');
    expect(cardKeyOf({ code: '600519' }, 3, '')).toBe(3);
  });

  it('字段缺失时不会把 undefined 当成 key', () => {
    expect(cardKeyOf({ name: '无代码' }, 5, 'code')).toBe(5);
  });
});
