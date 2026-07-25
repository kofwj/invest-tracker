<template>
  <div class="page-shell" :class="{ 'is-flush': flush, 'is-compact': compact }">
    <div v-if="showHeader" class="page-shell-header">
      <div class="page-shell-heading">
        <slot name="heading">
          <h3 v-if="title" class="page-shell-title">{{ title }}</h3>
          <div v-if="subtitle" class="page-shell-subtitle">{{ subtitle }}</div>
        </slot>
      </div>
      <div v-if="$slots.actions" class="page-shell-actions">
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

const props = defineProps({
  title: { type: String, default: '' },
  subtitle: { type: String, default: '' },
  /** 无外边距，给特殊页用 */
  flush: { type: Boolean, default: false },
  /** 更紧的页头 */
  compact: { type: Boolean, default: false },
});

const slots = useSlots();
const showHeader = computed(() => !!(props.title || props.subtitle || slots.heading || slots.actions));
</script>
