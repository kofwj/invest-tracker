import { onBeforeUnmount, ref } from 'vue';

/**
 * 订阅一条媒体查询，setup 里同步给出初始值。
 *
 * 为什么不在 onMounted 里再读：手机上首屏会先按宽屏渲染一帧，DataTable 会闪一下
 * 被截断的桌面表格。纯 SPA 没有水合问题，同步读没有副作用。
 *
 * `matchMedia` 不存在时（jsdom、老浏览器）固定返回 `fallback`，DataTable 因此默认
 * 走表格分支——现有测试不受影响。
 */
export function useMediaQuery(query, { fallback = false } = {}) {
  const supported = typeof window !== 'undefined' && typeof window.matchMedia === 'function';
  const mediaQuery = supported ? window.matchMedia(query) : null;
  const matches = ref(mediaQuery ? mediaQuery.matches : fallback);

  if (mediaQuery) {
    const onChange = (event) => {
      matches.value = event.matches;
    };
    // Safari < 14 只有 addListener/removeListener
    if (typeof mediaQuery.addEventListener === 'function') {
      mediaQuery.addEventListener('change', onChange);
      onBeforeUnmount(() => mediaQuery.removeEventListener('change', onChange));
    } else if (typeof mediaQuery.addListener === 'function') {
      mediaQuery.addListener(onChange);
      onBeforeUnmount(() => mediaQuery.removeListener(onChange));
    }
  }

  return matches;
}
