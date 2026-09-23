<template>
  <div class="page-shell" :class="{ 'is-flush': flush, 'is-compact': compact }">
    <div v-if="showHeader" class="page-shell-header">
      <!-- 页面标题只留给屏幕阅读器：可见标题文字与子导航 tab 完全重复 -->
      <h1 class="page-shell-title visually-hidden">{{ headingText }}</h1>

      <nav v-if="tabs.length > 1" class="page-tabs" aria-label="页面导航">
        <button
          v-for="t in tabs"
          :key="t"
          type="button"
          class="page-tab"
          :class="{ active: currentTab === t }"
          @click="goTab(t)"
        >{{ tabLabel(t) }}</button>
      </nav>

      <div v-if="slots.heading" class="page-shell-heading">
        <slot name="heading" />
      </div>

      <div v-if="slots.actions" class="page-shell-actions">
        <slot name="actions" />
      </div>
    </div>
    <div class="page-shell-body">
      <slot />
    </div>
  </div>
</template>

<script setup>
import { computed, useSlots } from 'vue';
import { useAppCtx } from '../composables/useAppCtx.js';
import { tabLabel } from '../modules/tabNav.js';

const props = defineProps({
  title: { type: String, default: '' },
  /** 无外边距，给特殊页用 */
  flush: { type: Boolean, default: false },
  /** 更紧的页头；默认开（全站 12 个页面共用，窄一点的页头省垂直空间） */
  compact: { type: Boolean, default: true },
});

const slots = useSlots();

// 测试里挂载这些 view 时提供的 ctx 可能没有导航字段（tabGroups / goTab 等），
// 这里一律兜底：拿不到就当成「没有子导航」，不抛错。
let ctx = {};
try {
  ctx = useAppCtx() || {};
} catch {
  ctx = {};
}
const { tabGroups, tabGroup, activeTab, goTab } = ctx;

/** ref / computed / 裸值都兼容 */
const unwrap = (v) => (v && typeof v === 'object' && 'value' in v ? v.value : v);

const currentTab = computed(() => unwrap(activeTab));
const currentGroupId = computed(() => unwrap(tabGroup));
const tabs = computed(() => {
  const groups = unwrap(tabGroups);
  const hit = (groups || []).find((g) => g.id === currentGroupId.value);
  return (hit && hit.tabs) || [];
});

/** 没有 title 时回退成当前 tab 的名字，别让 h1 空着 */
const headingText = computed(() => props.title || tabLabel(currentTab.value));

const showHeader = computed(
  () => !!(props.title || slots.heading || slots.actions || tabs.value.length > 1),
);
</script>
