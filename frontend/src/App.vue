<template>
  <el-config-provider :locale="zhCn">
    <div ref="shell" class="app-container">
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
  mounted() {
    this.measureHeader();
  },
  beforeUnmount() {
    if (this.headerObserver) {
      this.headerObserver.disconnect();
      this.headerObserver = null;
    }
  },
  methods: {
    /**
     * 把顶栏实际高度写进 --app-shell-header-h。
     *
     * 二级导航（.page-shell-header）要吸在顶栏正下方，但顶栏高度随断点变化：
     * 宽屏是一行，≤900px 换成 flex-wrap，≤640px 换成两行 grid。写死一个数字
     * 在任何一档都会错位，所以直接量。
     */
    measureHeader() {
      // 注意：不能用 this.$el——el-config-provider 渲染成 Fragment，$el 会落在
      // 文本锚点上（没有 querySelector），量高度永远拿不到元素。用 ref 取容器。
      const shell = this.$refs.shell;
      if (!shell || typeof shell.querySelector !== 'function') return;
      const el = shell.querySelector('.header');
      if (!el) return;
      const apply = (h) => {
        if (!(h > 0)) return;
        document.documentElement.style.setProperty('--app-shell-header-h', `${Math.round(h)}px`);
      };
      apply(el.getBoundingClientRect().height);
      // jsdom 没有 ResizeObserver，测试环境直接跳过（吸顶只是视觉，不影响行为）
      if (typeof ResizeObserver === 'undefined') return;
      // 回调里不能用 entry.contentRect.height——那是内容盒，不含上下 padding。
      // 顶栏有 11~13px 上下内边距，用内容盒会把二级导航顶进顶栏里一截，
      // 所以统一以 border-box 为准，直接重量一次。
      this.headerObserver = new ResizeObserver(() => {
        apply(el.getBoundingClientRect().height);
      });
      this.headerObserver.observe(el);
    },
  },
};
</script>
