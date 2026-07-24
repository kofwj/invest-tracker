<template>
  <el-config-provider :locale="zhCn">
    <div class="app-container">
      <AppHeader />

      <div class="content-shell">
        <div class="tab-group-bar" role="tablist" aria-label="功能分组">
          <button
            v-for="g in tabGroups"
            :key="g.id"
            type="button"
            class="tab-group-btn"
            :class="{ active: tabGroup === g.id }"
            role="tab"
            :aria-selected="tabGroup === g.id"
            @click="onGroupClick(g.id)"
          >{{ g.label }}</button>
        </div>

        <nav v-if="currentGroupTabs.length > 1" class="page-nav" aria-label="页面导航">
          <button
            v-for="t in currentGroupTabs"
            :key="t"
            type="button"
            class="page-nav-btn"
            :class="{ active: activeTab === t }"
            @click="goTab(t)"
          >{{ tabLabelOf(t) }}</button>
        </nav>

        <div class="page-view">
          <router-view />
        </div>
      </div>

      <AppDialogs />
      <LoginOverlay />
    </div>
  </el-config-provider>
</template>

<script>
import AppHeader from './components/AppHeader.vue';
import AppDialogs from './components/AppDialogs.vue';
import LoginOverlay from './components/LoginOverlay.vue';
import { tabLabel } from './modules/tabNav.js';

export default {
  name: 'App',
  components: {
    AppHeader,
    AppDialogs,
    LoginOverlay,
  },
  methods: {
    tabLabelOf(t) {
      return tabLabel(t);
    },
    onGroupClick(gid) {
      const hit = (this.tabGroups || []).find((x) => x.id === gid);
      if (!hit || !hit.tabs?.length) return;
      if (hit.tabs.includes(this.activeTab)) return;
      this.goTab(hit.tabs[0]);
    },
  },
  computed: {
    currentGroupTabs() {
      const hit = (this.tabGroups || []).find((x) => x.id === this.tabGroup);
      return hit ? hit.tabs : [];
    },
  },
};
</script>
