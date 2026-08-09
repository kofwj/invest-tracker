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

      <!-- 基本面体检：估值 / 盈利 / 杠杆 / 现金 -->
      <div v-if="fundCode" class="fund-block">
        <div class="fund-header">
          <span class="fund-title">基本面体检</span>
          <span class="fund-sub">输入代码自动拉取，只给指标和白话，不是买卖结论</span>
          <el-button v-if="fundLoading" size="small" text loading>体检中…</el-button>
        </div>
        <div v-if="fundLoading" class="fund-hint">正在拉取财报与估值指标…</div>
        <div v-else-if="fundError" class="fund-hint">{{ fundError }}</div>
        <div v-else-if="fundSections && fundSections.length" class="fund-grid">
          <div v-for="sec in fundSections" :key="sec.key" class="fund-card">
            <div class="fund-card-title">{{ sec.label }}</div>
            <div class="fund-row" v-for="item in sec.items" :key="item.label">
              <span class="fund-row-label">{{ item.label }}</span>
              <span class="fund-row-value" :class="{ 'muted': item.value == null }">
                {{ item.value != null ? item.value : '—' }}
              </span>
              <span v-if="item.note" class="fund-row-note" :title="item.note">?</span>
            </div>
          </div>
        </div>
        <div v-else class="fund-hint">该标的无财务/估值数据（可能是 ETF 或指数）。</div>
      </div>

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
const fundCode = ref('');
const fundSections = ref([]);
const fundLoading = ref(false);
const fundError = ref('');

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

async function loadFundamental(c) {
  if (!c) {
    fundCode.value = '';
    fundSections.value = [];
    fundError.value = '';
    return;
  }
  fundCode.value = c;
  fundLoading.value = true;
  fundError.value = '';
  fundSections.value = [];
  try {
    const res = await api.fundamentalCheck(c);
    fundSections.value = res.data?.sections || [];
    if (res.data?.error) fundError.value = res.data.error;
  } catch (e) {
    fundError.value = '体检拉取失败：' + (e?.response?.data?.detail || e?.message || '网络错误');
  } finally {
    fundLoading.value = false;
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
    loadFundamental(c);
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
  loadFundamental('');
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
.fund-block {
  margin-top: 16px;
}
.fund-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.fund-title {
  font-weight: 700;
  color: var(--app-text);
  font-size: 14px;
}
.fund-sub {
  color: var(--app-muted);
  font-size: 12px;
}
.fund-hint {
  color: var(--app-muted);
  font-size: 13px;
}
.fund-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
  gap: 10px;
}
.fund-card {
  border: 1px solid var(--app-border);
  border-radius: 8px;
  background: var(--app-surface);
  padding: 12px;
}
.fund-card-title {
  font-weight: 600;
  font-size: 13px;
  color: var(--app-primary);
  margin-bottom: 8px;
}
.fund-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 3px 0;
  font-size: 13px;
}
.fund-row-label {
  color: var(--app-muted);
  min-width: 0;
  flex: 1;
}
.fund-row-value {
  color: var(--app-text);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.fund-row-value.muted {
  color: var(--app-muted);
  font-weight: 400;
}
.fund-row-note {
  cursor: help;
  color: var(--app-warn);
  font-size: 11px;
}
</style>
