<template>
  <PageShell
    title="K线查询"
    subtitle="输入任意 A 股代码（含 ETF）查询日 K 线。支持持仓外标的，本地缓存 + 腾讯/东方财富源。"
  >
    <template #actions>
      <el-button size="small" @click="syncAllHoldings" :loading="loading">同步全部持仓 K 线</el-button>
      <el-button size="small" @click="clearAll">清空</el-button>
    </template>

    <div class="kline-page">
      <!-- 代码输入 + 操作 -->
      <div class="kline-controls">
        <el-input
          v-model="code"
          placeholder="输入代码，如 000001 / 600519 / 159352"
          style="width: 280px"
          @keyup.enter="loadKline"
          clearable
        />
        <el-button type="primary" @click="loadKline" :loading="loading">查询</el-button>
        <el-button @click="refreshKline" :loading="loading" plain>拉取最新</el-button>

        <el-radio-group v-model="days" size="small" @change="onDaysChange">
          <el-radio-button :value="60">60日</el-radio-button>
          <el-radio-button :value="120">120日</el-radio-button>
          <el-radio-button :value="250">250日</el-radio-button>
          <el-radio-button :value="500">500日</el-radio-button>
        </el-radio-group>

        <span v-if="info" class="kline-meta">
          {{ info.code }} · {{ info.count }} 条 · {{ latestDate }}
        </span>
      </div>

      <!-- 持仓快捷入口 -->
      <div v-if="holdings.length" class="quick-holdings">
        <span class="quick-label">持仓快捷：</span>
        <el-tag
          v-for="h in holdings"
          :key="h.code"
          size="small"
          @click="selectHolding(h)"
          style="margin: 2px; cursor: pointer"
        >
          {{ h.code }} {{ h.name }}
        </el-tag>
      </div>

      <!-- 图表 -->
      <div ref="chartEl" class="kline-chart" v-loading="loading"></div>

      <div v-if="error" class="kline-error">{{ error }}</div>

      <div v-if="!code && !rows.length" class="kline-hint">
        输入代码后点击「查询」或从上方持仓快捷选择。数据优先走本地缓存，首次或点「拉取最新」会从网络更新。
      </div>
    </div>
  </PageShell>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue';
import PageShell from '../components/PageShell.vue';
import api from '../api/index.js';
import { renderKlineChartView } from '../charts/index.js';
import { ElMessage } from 'element-plus';

const code = ref('');
const days = ref(120);
const rows = ref([]);
const loading = ref(false);
const error = ref('');
const chartEl = ref(null);
const holdings = ref([]);
const info = ref(null);

const latestDate = computed(() => {
  if (!rows.value.length) return '';
  const last = rows.value[rows.value.length - 1];
  return last?.date || '';
});

async function loadHoldings() {
  try {
    const res = await api.getHoldings();
    holdings.value = Array.isArray(res.data) ? res.data : (res.data?.items || []);
  } catch (e) {
    // 静默
  }
}

async function loadKline() {
  const c = (code.value || '').trim();
  if (!c) {
    ElMessage.warning('请输入代码');
    return;
  }
  loading.value = true;
  error.value = '';
  try {
    const res = await api.getKlines(c, days.value);
    rows.value = res.data?.rows || [];
    info.value = {
      code: res.data?.code || c,
      count: res.data?.count || rows.value.length,
    };
    if (!rows.value.length) {
      error.value = '本地暂无缓存，点击「拉取最新」从网络获取';
    }
    renderChart();
  } catch (e) {
    error.value = '加载失败：' + (e?.response?.data?.detail || e?.message || '未知错误');
  } finally {
    loading.value = false;
  }
}

async function refreshKline() {
  const c = (code.value || '').trim();
  if (!c) {
    ElMessage.warning('请输入代码');
    return;
  }
  loading.value = true;
  error.value = '';
  try {
    await api.syncKlines({ code: c, force: true });
    ElMessage.success('K线已更新');
    await loadKline();
  } catch (e) {
    error.value = '同步失败：' + (e?.response?.data?.detail || e?.message || '网络错误');
  } finally {
    loading.value = false;
  }
}

async function syncAllHoldings() {
  loading.value = true;
  try {
    await api.syncKlines({ force: true });
    ElMessage.success('持仓 K 线已同步');
    // 如果当前有 code，重新加载
    if (code.value) await loadKline();
  } catch (e) {
    ElMessage.error('同步失败');
  } finally {
    loading.value = false;
  }
}

function selectHolding(h) {
  code.value = h.code || '';
  loadKline();
}

function onDaysChange() {
  if (code.value) {
    loadKline();
  }
}

function renderChart() {
  if (chartEl.value) {
    renderKlineChartView(chartEl.value, rows.value);
  }
}

function clearAll() {
  code.value = '';
  rows.value = [];
  info.value = null;
  error.value = '';
  if (chartEl.value) {
    renderKlineChartView(chartEl.value, []);
  }
}

onMounted(() => {
  loadHoldings();
});
</script>

<style scoped>
.kline-page {
  padding: 4px 0;
}
.kline-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.kline-meta {
  margin-left: 8px;
  font-size: 12px;
  color: var(--app-muted);
}
.quick-holdings {
  margin-bottom: 10px;
  font-size: 12px;
}
.quick-label {
  color: var(--app-muted);
  margin-right: 6px;
}
.kline-chart {
  width: 100%;
  height: 520px;
  border: 1px solid var(--app-border);
  border-radius: 6px;
  background: var(--app-surface);
}
.kline-error {
  color: var(--app-down, #d64545);
  font-size: 13px;
  margin-top: 8px;
}
.kline-hint {
  margin-top: 12px;
  color: var(--app-muted);
  font-size: 12px;
}
</style>
