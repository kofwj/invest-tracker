<template>
  <el-config-provider :locale="zhCn">
    <div class="app-container">
      <AppHeader />

      <div class="content-shell">
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

export default {
  name: 'App',
  components: {
    AppHeader,
    AppDialogs,
    LoginOverlay,
  },
};
</script>
