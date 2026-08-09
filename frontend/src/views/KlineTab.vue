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

      <!-- 走势解读：均线视角 -->
      <div v-if="trend && trend.ok" class="trend-block">
        <div class="trend-header">
          <span class="trend-title">走势解读（均线）</span>
          <span class="fund-tag" :class="'s-' + trend.status">{{ trend.tag }}</span>
        </div>
        <div class="trend-brief">{{ trend.brief }}</div>
        <div class="trend-grid">
          <div class="trend-cell"><span class="trend-k">现价</span><b>{{ trend.cur }}</b></div>
          <div class="trend-cell"><span class="trend-k">MA5</span><b>{{ trend.ma5 }}</b></div>
          <div class="trend-cell"><span class="trend-k">MA10</span><b>{{ trend.ma10 }}</b></div>
          <div class="trend-cell"><span class="trend-k">MA20</span><b>{{ trend.ma20 }}</b></div>
          <div class="trend-cell"><span class="trend-k">偏离20日</span><b :class="trend.dev20 >= 0 ? 'up' : 'down'">{{ trend.dev20 >= 0 ? '+' : '' }}{{ trend.dev20 }}%</b></div>
        </div>
        <ul class="trend-points">
          <li v-for="(p, i) in trend.points" :key="i">{{ p }}</li>
        </ul>
      </div>
      <div v-if="trend && !trend.ok" class="kline-hint">{{ trend.brief }}</div>

      <!-- 公司简报 -->
      <div v-if="fundProfile" class="cx-block">
        <div class="cx-header">
          <span class="fund-title">公司简报</span>
          <span v-if="fundProfile.holder_count" class="fund-sub">股东户数 {{ Number(fundProfile.holder_count).toLocaleString() }}</span>
        </div>
        <div class="cx-profile">
          <div class="cx-name">{{ fundProfile.name }} <span v-if="fundProfile.short_name" class="cx-short">({{ fundProfile.short_name }})</span></div>
          <div class="cx-kv">
            <span class="cx-k">行业</span><b>{{ fundProfile.industry || '—' }}</b>
            <span class="cx-k">法人</span><b>{{ fundProfile.legal_rep || '—' }}</b>
            <span class="cx-k">上市</span><b>{{ fundProfile.listed || '—' }}</b>
            <span class="cx-k">成立</span><b>{{ fundProfile.founded || '—' }}</b>
          </div>
          <div v-if="fundProfile.main_biz" class="cx-biz">主营：{{ fundProfile.main_biz }}</div>
          <div class="cx-kv">
            <span class="cx-k">市场</span><b>{{ fundProfile.market || '—' }}</b>
            <span class="cx-k">官网</span><b>{{ fundProfile.website || '—' }}</b>
          </div>
        </div>

        <!-- 机构持仓：前十大股东 -->
        <div v-if="fundProfile.top_holders && fundProfile.top_holders.length" class="cx-holders">
          <div class="cx-subtitle">前十大股东</div>
          <div class="cx-holder-row" v-for="(h, i) in fundProfile.top_holders" :key="i">
            <span class="cx-holder-idx">{{ i + 1 }}</span>
            <span class="cx-holder-name">{{ h.name }}</span>
            <span class="cx-holder-kind" :class="'k-' + h.kind">{{ holderKindText(h.kind) }}</span>
            <span class="cx-holder-pct">{{ h.pct != null ? h.pct + '%' : '—' }}</span>
          </div>
          <!-- 合计行：钱攥在谁手里 -->
          <div v-if="holderSummary.top != null" class="cx-summary">
            <span class="cx-sum-key">前十大合计</span><b>{{ holderSummary.top }}%</b>
            <span v-if="holderSummary.inst" class="cx-sum-key">机构/北向/国资合计</span><b>{{ holderSummary.inst }}%</b>
            <span v-if="holderSummary.hasMissing" class="cx-sum-note">（含未披露持股数股东，合计为披露部分）</span>
          </div>
        </div>
      </div>

      <!-- 历史分红 -->
      <div v-if="fundDividends && fundDividends.length" class="cx-block">
        <div class="cx-header">
          <span class="fund-title">历史分红</span>
          <span class="fund-sub">最近 {{ fundDividends.length }} 次已实施</span>
        </div>
        <div class="cx-divs">
          <div class="cx-div-row" v-for="(d, i) in fundDividends" :key="i">
            <span class="cx-div-report">{{ d.report }}</span>
            <span class="cx-div-desc">{{ d.desc }}</span>
            <span v-if="d.yield_pct != null" class="cx-div-yield">{{ d.yield_pct }}%</span>
            <span v-if="d.ex_date" class="cx-div-date">除息 {{ d.ex_date }}</span>
          </div>
        </div>
      </div>

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
              <div class="fund-row-head">
                <span class="fund-row-label">{{ item.label }}</span>
                <span class="fund-row-value" :class="{ 'muted': item.value == null }">
                  {{ item.value != null ? item.value : '—' }}
                </span>
                <span v-if="item.status" class="fund-tag" :class="'s-' + item.status">{{ item.status === 'ok' ? '正常' : item.status === 'high' ? '偏高' : '偏低' }}</span>
              </div>
              <div v-if="item.note" class="fund-row-note">{{ item.note }}</div>
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
import { renderKlineChartView, analyzeKlineTrend } from '../charts/index.js';
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
const trend = ref(null);
const fundProfile = ref(null);
const fundDividends = ref([]);

const latestDate = computed(() => {
  if (!rows.value.length) return '';
  const last = rows.value[rows.value.length - 1];
  return last?.date || '';
});

// 股东类别中文标签
function holderKindText(kind) {
  const map = { north: '北向', institution: '机构', state: '国有', person: '个人', other: '' };
  return map[kind] || '';
}

// 前十大股东汇总：合计占比 + 机构/北向/国资合计
const holderSummary = computed(() => {
  const hs = fundProfile.value?.top_holders;
  if (!hs || !hs.length) return { top: null, inst: null, hasMissing: false };
  let top = 0, inst = 0, hasVal = false, hasMissing = false;
  const instKinds = new Set(['institution', 'north', 'state']);
  for (const h of hs) {
    if (h.pct == null) { hasMissing = true; continue; }
    top += h.pct; hasVal = true;
    if (instKinds.has(h.kind)) inst += h.pct;
  }
  if (!hasVal) return { top: null, inst: null, hasMissing };
  const fmt = (n) => (Math.round(n * 10) / 10).toFixed(1).replace(/\.0$/, '');
  return {
    top: fmt(top),
    inst: inst > 0 ? fmt(inst) : null,
    hasMissing,
  };
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
    fundProfile.value = null;
    fundDividends.value = [];
    return;
  }
  fundCode.value = c;
  fundLoading.value = true;
  fundError.value = '';
  fundSections.value = [];
  try {
    const res = await api.fundamentalCheck(c);
    fundSections.value = res.data?.sections || [];
    fundProfile.value = res.data?.profile || null;
    fundDividends.value = res.data?.dividends || [];
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
    // 场外开放式基金（f 开头）没有股票式 K 线，只给净值走势
    if (res.data?.is_fund) {
      error.value = '场外基金没有K线（无盘中开收高低），只有每日净值，看持仓/净值走势即可';
      trend.value = null;
      renderChart();
      return;
    }
    if (!rows.value.length) {
      error.value = '本地暂无缓存，点击「拉取最新」从网络获取';
    }
    trend.value = analyzeKlineTrend(rows.value);
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
  trend.value = null;
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
.trend-block {
  margin-top: 16px;
  border: 1px solid var(--app-border);
  border-radius: 8px;
  background: var(--app-surface);
  padding: 12px;
}
.trend-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
}
.trend-title {
  font-weight: 700;
  color: var(--app-text);
  font-size: 14px;
}
.trend-brief {
  font-size: 13px;
  color: var(--app-text);
  margin-bottom: 8px;
}
.trend-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
  gap: 6px;
  margin-bottom: 8px;
}
.trend-cell {
  border: 1px solid var(--app-border);
  border-radius: 6px;
  padding: 5px 8px;
  font-size: 12px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.trend-k {
  color: var(--app-muted);
}
.trend-cell b {
  font-weight: 600;
  color: var(--app-text);
  font-variant-numeric: tabular-nums;
}
.trend-cell b.up {
  color: #16a34a;
}
.trend-cell b.down {
  color: #dc2626;
}
.trend-points {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  color: var(--app-text);
  line-height: 1.7;
}

.cx-block {
  margin-top: 16px;
  border: 1px solid var(--app-border);
  border-radius: 8px;
  background: var(--app-surface);
  padding: 12px;
}
.cx-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
.cx-profile {
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.cx-name {
  font-size: 14px;
  font-weight: 700;
  color: var(--app-text);
}
.cx-short {
  font-weight: 400;
  color: var(--app-muted);
  font-size: 12px;
}
.cx-kv {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 16px;
  font-size: 12px;
  color: var(--app-muted);
}
.cx-kv b {
  color: var(--app-text);
  font-weight: 600;
  margin-left: 2px;
}
.cx-biz {
  font-size: 13px;
  color: var(--app-text);
  line-height: 1.6;
  padding: 5px 8px;
  background: var(--app-bg);
  border-radius: 6px;
}
.cx-divs {
  display: flex;
  flex-direction: column;
  font-size: 13px;
}
.cx-div-row {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding: 6px 0;
  border-bottom: 1px solid var(--app-border);
}
.cx-div-row:last-child {
  border-bottom: none;
}
.cx-div-report {
  color: var(--app-muted);
  font-variant-numeric: tabular-nums;
  min-width: 60px;
}
.cx-div-desc {
  color: var(--app-text);
  flex: 1;
}
.cx-div-yield {
  color: #16a34a;
  font-weight: 600;
}
.cx-div-date {
  color: var(--app-muted);
  font-size: 12px;
}
.cx-holders {
  margin-top: 10px;
  border-top: 1px solid var(--app-border);
  padding-top: 8px;
}
.cx-subtitle {
  font-weight: 600;
  color: var(--app-text);
  font-size: 12px;
  margin-bottom: 6px;
}
.cx-holder-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 4px 0;
  font-size: 12.5px;
  border-bottom: 1px dashed var(--app-border);
}
.cx-holder-row:last-child {
  border-bottom: none;
}
.cx-holder-idx {
  color: var(--app-muted);
  width: 18px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}
.cx-holder-name {
  flex: 1;
  color: var(--app-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cx-holder-kind {
  font-size: 11px;
  padding: 0 5px;
  border-radius: 4px;
  color: var(--app-muted);
  background: var(--app-bg);
}
.cx-holder-kind.k-north {
  color: #2563eb;
  background: rgba(37, 99, 235, 0.12);
}
.cx-holder-kind.k-institution {
  color: #7c3aed;
  background: rgba(124, 58, 237, 0.12);
}
.cx-holder-kind.k-state {
  color: #d97706;
  background: rgba(217, 119, 6, 0.15);
}
.cx-holder-pct {
  font-weight: 600;
  color: var(--app-text);
  font-variant-numeric: tabular-nums;
  min-width: 52px;
  text-align: right;
}
.cx-summary {
  margin-top: 8px;
  padding: 7px 8px;
  background: var(--app-bg);
  border-radius: 6px;
  font-size: 12.5px;
  color: var(--app-text);
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 6px 14px;
}
.cx-summary b {
  font-weight: 700;
}
.cx-sum-key {
  color: var(--app-muted);
}
.cx-sum-note {
  color: var(--app-muted);
  font-size: 11px;
  width: 100%;
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
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
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
  padding: 3px 0;
  font-size: 13px;
}
.fund-row-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
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
.fund-tag {
  font-size: 11px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 999px;
  white-space: nowrap;
}
.fund-tag.s-ok {
  color: #16a34a;
  background: rgba(22, 163, 74, 0.12);
}
.fund-tag.s-high {
  color: #dc2626;
  background: rgba(220, 38, 38, 0.12);
}
.fund-tag.s-low {
  color: #d97706;
  background: rgba(217, 119, 6, 0.15);
}
.fund-row-note {
  color: var(--app-muted);
  font-size: 11px;
  line-height: 1.5;
  margin-top: 1px;
}
</style>
