import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    port: 8080,
    host: '0.0.0.0',
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  build: {
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return;
          if (id.includes('element-plus')) return 'element-plus';
          if (id.includes('echarts') || id.includes('zrender')) return 'echarts';
          if (id.includes('/vue/') || id.includes('\\vue\\') || id.includes('@vue')) return 'vue';
          if (id.includes('axios')) return 'axios';
          return 'vendor';
        },
      },
    },
  },
});
