<template>
  <div class="redirect-hint">正在跳转到「结构与目标」…</div>
</template>

<script setup>
import { onMounted } from 'vue';
import { useAppCtx } from '../composables/useAppCtx.js';

const { goTab } = useAppCtx();

onMounted(() => {
  if (typeof goTab === 'function') goTab('allocation');
});
</script>

<style scoped>
.redirect-hint {
  padding: 24px;
  color: var(--app-muted);
  font-size: 13px;
}
</style>
