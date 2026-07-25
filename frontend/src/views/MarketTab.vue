<template>
  <div class="redirect-hint">正在跳转到「今天该看」…</div>
</template>

<script setup>
import { onMounted } from 'vue';
import { useAppCtx } from '../composables/useAppCtx.js';

const { goTab } = useAppCtx();

onMounted(() => {
  if (typeof goTab === 'function') goTab('decision');
});
</script>

<style scoped>
.redirect-hint {
  padding: 24px;
  color: var(--app-muted);
  font-size: 13px;
}
</style>
