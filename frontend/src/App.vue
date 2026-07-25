<template>
  <el-config-provider :locale="zhCn">
    <div class="app-container">
      <AppHeader />

      <div class="content-shell">
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
  },
  computed: {
    currentGroupTabs() {
      const hit = (this.tabGroups || []).find((x) => x.id === this.tabGroup);
      return hit ? hit.tabs : [];
    },
  },
};
</script>
