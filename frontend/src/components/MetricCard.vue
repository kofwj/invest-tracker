<template>
  <div class="ledger-metric" :class="rootClass">
    <div v-if="plain" class="ledger-metric-plain">{{ plain }}</div>
    <div v-if="label || $slots.icon" class="ledger-metric-label">
      <slot name="icon" />
      <span v-if="label">{{ label }}</span>
    </div>
    <div class="ledger-metric-value" :class="valueClass" :style="valueStyle" :title="title || (value != null ? String(value) : undefined)">
      <slot>{{ value }}</slot>
    </div>
    <div v-if="sub || $slots.sub" class="ledger-metric-sub" :title="typeof sub === 'string' ? sub : undefined">
      <slot name="sub">{{ sub }}</slot>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({
  label: { type: String, default: '' },
  value: { type: [String, Number], default: '' },
  sub: { type: String, default: '' },
  /** 人话标题（收益分析主卡） */
  plain: { type: String, default: '' },
  /** 主卡加宽/强调 */
  main: { type: Boolean, default: false },
  /** 次卡弱样式 */
  secondary: { type: Boolean, default: false },
  /** up | down | warn | ok | muted | '' */
  tone: { type: String, default: '' },
  /** 直接上色（兼容旧 color 字段） */
  color: { type: String, default: '' },
  /** hover 显示完整值（解决大数字被截断） */
  title: { type: String, default: '' },
});

const rootClass = computed(() => ({
  'is-main': props.main,
  'is-secondary': props.secondary,
  [`is-${props.tone}`]: !!props.tone,
}));

const valueClass = computed(() => {
  if (props.tone === 'up' || props.tone === 'down' || props.tone === 'warn' || props.tone === 'ok') {
    return props.tone;
  }
  return '';
});

const valueStyle = computed(() => (props.color ? { color: props.color } : undefined));
</script>
