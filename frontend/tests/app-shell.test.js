/**
 * 应用外壳：顶栏高度测量回归测试。
 *
 * 背景：二级导航（.page-shell-header）靠 --app-shell-header-h 吸在顶栏下方，
 * 这个值由 App.vue 的 measureHeader() 实测后写入。第一版用 this.$el 取容器，
 * 但 el-config-provider 渲染成 Fragment，$el 落在文本锚点上、没有 querySelector，
 * 于是量高度静默失败——页面看着正常，只是吸顶错位到 60px。这条测试盯住它。
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import App from '../src/App.vue';

const CSS_VAR = '--app-shell-header-h';

function makeShell(headerHeight) {
  const shell = document.createElement('div');
  shell.className = 'app-container';
  shell.innerHTML = '<div class="header"></div>';
  const header = shell.querySelector('.header');
  header.getBoundingClientRect = () => ({ height: headerHeight });
  return shell;
}

describe('App 外壳顶栏测量', () => {
  beforeEach(() => {
    document.documentElement.style.removeProperty(CSS_VAR);
  });
  afterEach(() => {
    document.documentElement.style.removeProperty(CSS_VAR);
  });

  it('把顶栏实际高度写进 --app-shell-header-h', () => {
    const shell = makeShell(88);
    App.methods.measureHeader.call({ $refs: { shell } });
    expect(document.documentElement.style.getPropertyValue(CSS_VAR)).toBe('88px');
  });

  it('高度取整（亚像素不进 CSS 变量）', () => {
    const shell = makeShell(60.6);
    App.methods.measureHeader.call({ $refs: { shell } });
    expect(document.documentElement.style.getPropertyValue(CSS_VAR)).toBe('61px');
  });

  it('ref 缺失时安静返回，不抛错也不写变量', () => {
    expect(() => App.methods.measureHeader.call({ $refs: {} })).not.toThrow();
    expect(document.documentElement.style.getPropertyValue(CSS_VAR)).toBe('');
  });

  it('高度为 0（未布局 / 隐藏）时不写变量，避免二级导航吸到 0', () => {
    const shell = makeShell(0);
    App.methods.measureHeader.call({ $refs: { shell } });
    expect(document.documentElement.style.getPropertyValue(CSS_VAR)).toBe('');
  });
  it('ResizeObserver 回调按 border-box 量高度，不用 contentRect', () => {
    const shell = makeShell(69);
    const header = shell.querySelector('.header');
    const origRO = globalThis.ResizeObserver;
    let fire = null;
    globalThis.ResizeObserver = class {
      constructor(fn) { fire = fn; }
      observe() {}
      disconnect() {}
    };
    try {
      const ctx = { $refs: { shell } };
      App.methods.measureHeader.call(ctx);
      expect(document.documentElement.style.getPropertyValue(CSS_VAR)).toBe('69px');

      // 换断点后顶栏变高：回调里的 contentRect 不含上下 padding，
      // 若按 contentRect 写变量，二级导航会被顶栏压住一截。
      header.getBoundingClientRect = () => ({ height: 112 });
      document.documentElement.style.removeProperty(CSS_VAR);
      fire([{ contentRect: { height: 90 }, target: header }]);
      expect(document.documentElement.style.getPropertyValue(CSS_VAR)).toBe('112px');
    } finally {
      if (origRO === undefined) delete globalThis.ResizeObserver;
      else globalThis.ResizeObserver = origRO;
    }
  });
});
