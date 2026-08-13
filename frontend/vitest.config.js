import { defineConfig } from 'vitest/config';
import vue from '@vitejs/plugin-vue';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      // charts/index.js imports echarts submodules at top level; unit tests
      // only exercise pure helpers, so stub echarts to keep node env clean.
      'echarts/core': fileURLToPath(new URL('./tests/mocks/echarts.js', import.meta.url)),
      'echarts/charts': fileURLToPath(new URL('./tests/mocks/echarts.js', import.meta.url)),
      'echarts/components': fileURLToPath(new URL('./tests/mocks/echarts.js', import.meta.url)),
      'echarts/renderers': fileURLToPath(new URL('./tests/mocks/echarts.js', import.meta.url)),
    },
  },
  test: {
    environment: 'jsdom',
    include: ['tests/**/*.test.js'],
    exclude: ['tests/mocks/**', 'node_modules/**'],
  },
});