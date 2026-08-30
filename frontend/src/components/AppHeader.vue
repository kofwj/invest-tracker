<template>
  <div class="header">
    <button type="button" class="header-brand" @click="goTab('overview')" :title="`返回总览（当前：${activeTabLabel}）`" aria-label="返回总览">
      <div class="header-mark" aria-hidden="true">
        <Wallet :size="16" :stroke-width="2" />
      </div>
      <div class="header-brand-text">
        <h2>Invest Tracker</h2>
        <div class="header-subtitle">真仓账本{{ versionSuffix }}</div>
      </div>
    </button>

    <nav class="header-nav" role="tablist" aria-label="功能分组">
      <button
        v-for="g in tabGroups"
        :key="g.id"
        type="button"
        class="header-nav-btn"
        :class="{ active: tabGroup === g.id }"
        role="tab"
        :aria-selected="tabGroup === g.id"
        @click="onGroupClick(g.id)"
      >{{ g.label }}</button>
    </nav>

    <div class="header-actions">
      <button
        type="button"
        class="header-icon-btn"
        :title="`主题：${themeLabel}（点击切换）`"
        :aria-label="`主题：${themeLabel}`"
        @click="cycleThemeMode"
      >
        <Monitor v-if="themeMode === 'system'" :size="16" :stroke-width="2" />
        <Sun v-else-if="themeMode === 'light'" :size="16" :stroke-width="2" />
        <Moon v-else :size="16" :stroke-width="2" />
        <span class="header-theme-label">{{ themeLabel }}</span>
      </button>
      <button type="button" class="header-btn" @click="fetchData">
        <RefreshCw :size="14" :stroke-width="2" />
        刷新
      </button>
      <button type="button" class="header-btn primary" :disabled="syncing" @click="syncPrices">
        <Radar :size="14" :stroke-width="2" :class="{ spin: syncing }" />
        同步价
      </button>
      <button v-if="authEnabled" type="button" class="header-btn ghost" @click="handleLogout">
        <LogOut :size="14" :stroke-width="2" />
        退出
      </button>
      <span v-if="syncNotice.text" class="inline-sync-status" :class="syncNotice.type">{{ syncNotice.text }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue';
import { LogOut, Monitor, Moon, Radar, RefreshCw, Sun, Wallet } from 'lucide-vue-next';
import { useAppCtx } from '../composables/useAppCtx.js';
import { tabLabel } from '../modules/tabNav.js';
import api from '../api/index.js';

const {
  authEnabled,
  handleLogout,
  syncing,
  syncNotice,
  syncPrices,
  fetchData,
  themeMode,
  themeLabel,
  cycleThemeMode,
  tabGroups,
  tabGroup,
  activeTab,
  goTab,
} = useAppCtx();

const activeTabLabel = computed(() => tabLabel(activeTab?.value ?? activeTab));

// 版本号从 /api/health 拉取（backend/version.py 是唯一来源）；失败静默不展示
const appVersion = ref('');
onMounted(async () => {
  try {
    const res = await api.getHealth();
    appVersion.value = String(res.data?.version || '');
  } catch { /* 装饰信息，不报错 */ }
});
const versionSuffix = computed(() => (appVersion.value ? ` v${appVersion.value}` : ''));

function onGroupClick(gid) {
  const hit = (tabGroups || []).find((x) => x.id === gid);
  if (!hit || !hit.tabs?.length) return;
  const current = activeTab?.value ?? activeTab;
  if (hit.tabs.includes(current)) return;
  goTab(hit.tabs[0]);
}
</script>
