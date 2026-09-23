<template>
  <PageShell
    title="收益分析"
  >
    <template #actions>
        <el-tag :type="perfSummary?.xirr_status === 'ok' ? 'success' : (hasPerfFlows ? 'info' : 'warning')" size="small">
          {{ perfSummary?.xirr_status === 'ok' ? '年化已算' : (hasPerfFlows ? (perfSummary?.xirr_message || '年化暂不可用') : '外部流水未录入') }}
        </el-tag>
        <el-button size="small" @click="fetchPerformance" :loading="perfLoading">刷新</el-button>
      
    </template>

    <!-- 加载骨架 -->
    <div v-if="perfLoading && !perfSummary" class="sk-metrics" aria-hidden="true">
      <div v-for="i in 4" :key="'sk'+i" class="sk-block sk-metric"></div>
    </div>

    <!-- 时间轴收益尺：今天/本月/今年/近一年/开仓至今 -->
    <div class="perf-window-strip" :class="{ 'is-loading': perfLoading && !perfSummary }">
      <div
        v-for="w in perfWindowCards"
        :key="w.key"
        class="perf-window-card"
        :class="[w.active ? 'is-active' : '', 'is-' + w.tone, { 'is-disabled': w.disabled }]"
        @click="!w.disabled && selectPerfWindow(w.key)"
      >
        <div class="perf-window-label">{{ w.label }}</div>
        <div class="perf-window-gain">{{ w.gain != null ? formatMoney(w.gain, 0, true) : '—' }}</div>
        <div class="perf-window-pct">{{ w.gainPct != null ? formatPercent(w.gainPct, 1) : '无快照' }}</div>
        <div v-if="w.stale" class="perf-window-stale">基准 {{ (w.baseDate || '').slice(5) }}（{{ w.staleDays }} 天前）</div>
      </div>
    </div>

    <!-- 每日收益：逐日盈亏（已剔除转入/转出） -->
    <el-card shadow="never" class="perf-daily-card">
      <div class="perf-daily-head">
        <div>
          <div class="perf-section-title">每日收益</div>
          <div class="perf-contrib-sub">按每日快照逐日计算，已剔除转入/转出；<span v-if="perfLatestSnapshotDate">最近一次快照 {{ perfLatestSnapshotDate }}</span><span v-else>还没有任何快照</span></div>
        </div>
        <div class="perf-daily-actions">
          <el-radio-group v-model="dailyRange" size="small">
            <el-radio-button :value="30">近30天</el-radio-button>
            <el-radio-button :value="90">近90天</el-radio-button>
            <el-radio-button :value="0">全部</el-radio-button>
          </el-radio-group>
          <el-button v-if="!todaySnapshotDone" size="small" :loading="dailySnapshotSaving" @click="onCreateTodaySnapshot">记录今日快照</el-button>
        </div>
      </div>

      <el-alert
        v-if="!perfDailyRows.length"
        type="info"
        show-icon
        :closable="false"
        title="还没有可比较的两天快照"
        description="每日收益要连续两天的快照才算得出来。点上面的「记录今日快照」，或让服务器每天定时跑一次快照任务。"
      />

      <template v-else>
        <div class="ledger-metrics cols-4" style="margin-bottom:10px;">
          <MetricCard
            label="近30天累计"
            :value="formatMoney(perfDailyStats.total, 2, true)"
            :tone="perfDailyStats.total >= 0 ? 'up' : 'down'"
          />
          <MetricCard label="涨 / 跌 天数" :value="`${perfDailyStats.upDays} / ${perfDailyStats.downDays}`" />
          <MetricCard label="最好一天" :value="dailyBestText" tone="up" />
          <MetricCard label="最差一天" :value="dailyWorstText" tone="down" />
        </div>

        <div id="dailyPnlChart" class="perf-daily-chart"></div>

        <el-table :data="dailyTableRows" size="small" stripe max-height="320" style="margin-top:10px;" aria-label="每日收益">
          <el-table-column label="日期" width="140">
            <template #default="s">
              <span>{{ s.row.date }}</span>
              <el-tag v-if="s.row.isToday" size="small" style="margin-left: 6px;">实时</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="当日盈亏" width="140" align="right">
            <template #default="s">
              <span :class="s.row.change >= 0 ? 'perf-up' : 'perf-down'">{{ formatMoney(s.row.change, 2, true) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="当日涨跌" width="110" align="right">
            <template #default="s">
              <span :class="s.row.change >= 0 ? 'perf-up' : 'perf-down'">
                {{ s.row.pct != null ? formatPercent(s.row.pct, 2) : '—' }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="期末总资产" align="right">
            <template #default="s">{{ formatMoney(s.row.assets) }}</template>
          </el-table-column>
          <el-table-column label="间隔" width="100" align="center">
            <template #default="s">
              <el-tooltip
                v-if="s.row.isToday"
                :content="s.row.stale
                  ? `基准快照是 ${s.row.baseDate}，这一行实际跨了 ${s.row.daysGap} 天`
                  : `基准是 ${s.row.baseDate || '上一交易日'} 的收盘快照，收盘后再写成正式快照`"
                placement="top"
              >
                <el-tag size="small" :type="s.row.stale ? 'warning' : 'success'">未收盘</el-tag>
              </el-tooltip>
              <el-tag v-else-if="s.row.isGap" size="small" type="warning">{{ s.row.daysGap }}天</el-tag>
              <span v-else class="perf-contrib-sub">1天</span>
            </template>
          </el-table-column>
          <el-table-column label="价格" width="180" align="center">
            <template #default="s">
              <el-tooltip
                v-if="s.row.priceStale"
                :content="`这天的快照按 ${s.row.priceDate || '早先'} 的价格计算，不是当天价`"
                placement="top"
              >
                <el-tag size="small" type="warning">价格未更新</el-tag>
              </el-tooltip>
              <el-tag v-if="s.row.unpricedCount" size="small" type="info">缺价 {{ s.row.unpricedCount }} 只</el-tag>
              <span v-if="!s.row.priceStale && !s.row.unpricedCount" class="perf-contrib-sub">—</span>
            </template>
          </el-table-column>
        </el-table>
      </template>
    </el-card>

    <!-- 未录流水强提示 -->
    <el-alert
      v-if="!hasPerfFlows"
      type="warning"
      show-icon
      :closable="false"
      class="perf-flow-alert"
      title="外部资金流水未录入"
    >
      <template #default>
        <div style="margin-top:6px;">
          <el-button size="small" type="warning" @click="scrollToFlows">去录流水</el-button>
          <el-button size="small" :loading="perfSuggestLoading" @click="onLoadFlowSuggest">从银证生成建议</el-button>
        </div>
      </template>
    </el-alert>

    <!-- 一句话故事 -->
    <el-card v-if="perfStory?.headline" shadow="never" class="perf-story-card" style="margin-bottom: 14px;">
      <div class="perf-story-head">
        <div class="perf-story-headline" :class="'is-' + (perfStory.tone || 'neutral')">{{ perfStory.headline }}</div>
        <el-tag :type="perfStoryToneType" size="small">{{ perfStory.as_of_date || '今日' }}</el-tag>
      </div>
      <!-- 故事聚焦组合层面，个股详细贡献已移至「组合归因与风险」卡片和「持仓明细」 -->
    </el-card>

    <!-- 普通人核心指标（3 张最重要） -->
    <div class="ledger-metrics cols-3" style="margin-bottom: 8px;">
      <MetricCard
        v-for="m in perfPrimaryCards"
        :key="m.label"
        :label="m.label"
        :value="m.value"
        :color="m.color"
        :main="!!m.main"
        :title="m.value"
      />
    </div>

    <!-- 辅助小信息 -->
    <div class="ledger-metrics cols-2" style="margin-bottom: 12px;">
      <MetricCard
        v-for="m in perfSecondaryCards"
        :key="m.label"
        :label="m.label"
        :value="m.value"
        :color="m.color"
        secondary
        :title="m.value"
      />
    </div>

        <!-- 组合风险（精简 3 张核心） -->
    <el-card shadow="never" style="margin-bottom: 14px;">
      <div style="margin-bottom:8px;">
        <div class="perf-contrib-title">风险一览</div>
        <div class="perf-contrib-sub">最大回撤 = 历史最高点到最低点的跌幅；年化波动 = 日常波动幅度。</div>
      </div>

      <div class="ledger-metrics cols-3" style="margin-bottom:8px;">
        <MetricCard
          label="最大回撤"
          :value="((perfRiskMetrics?.maxDrawdownPct) || 0) + '%'"
          :tone="(perfRiskMetrics?.maxDrawdown || 0) > 0.05 ? 'down' : 'neutral'"
        />
        <MetricCard
          v-if="perfSummary?.underwater"
          label="当前离峰值"
          :value="(perfSummary.underwater.underwater_pct || 0) + '%'"
          :tone="(perfSummary.underwater.underwater_pct || 0) > 5 ? 'down' : 'neutral'"
        />
        <MetricCard
          label="年化波动"
          :value="(perfRiskMetrics?.approxVol) != null ? (perfRiskMetrics.approxVol) + '%' : '—'"
          :tone="(perfRiskMetrics?.approxVol || 0) > 15 ? 'down' : 'neutral'"
        />
      </div>
      </el-card>

      <!-- 流水 -->
    <el-card id="perf-flow-section" shadow="never" style="margin-bottom: 14px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;gap:12px;flex-wrap:wrap;">
        <div>
          <div class="perf-section-title">组合资金流水（外部投入/取出）</div>
          <div class="perf-contrib-sub">仅记录组合外部投入/取出；买卖、银证互转不在此记录。</div>
        </div>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
          <el-button size="small" @click="onLoadFlowSuggest" :loading="perfSuggestLoading">从银证生成建议</el-button>
          <el-tag size="small">共 {{ perfFlows.length }} 笔</el-tag>
        </div>
      </div>
      <div v-if="perfFlowSuggestions.length" class="perf-suggest-box" style="margin-bottom:12px;">
        <div class="perf-contrib-sub" style="margin-bottom:8px;">建议草稿</div>
        <el-table :data="perfFlowSuggestions" size="small" stripe aria-label="资金流水建议草稿">
          <el-table-column prop="date" label="日期" width="110" />
          <el-table-column prop="flow_type" label="类型" width="70" />
          <el-table-column label="金额" width="120" align="right">
            <template #default="s">{{ formatMoney(s.row.amount) }}</template>
          </el-table-column>
          <el-table-column prop="remark" label="说明" min-width="180" show-overflow-tooltip />
          <el-table-column label="操作" width="90">
            <template #default="s">
              <el-button type="primary" link size="small" :loading="perfSuggestionApplying" @click="onApplyPerfFlowSuggestion(s.row)">记入</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <el-form :inline="true" size="small" style="margin-bottom: 12px;">
        <el-form-item label="日期">
          <el-date-picker v-model="perfFlowForm.date" type="date" value-format="YYYY-MM-DD" style="width:140px;" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="perfFlowForm.flow_type" style="width:90px;">
            <el-option label="投入" value="投入" />
            <el-option label="取出" value="取出" />
          </el-select>
        </el-form-item>
        <el-form-item label="金额">
          <el-input-number v-model="perfFlowForm.amount" :min="0" :step="10000" style="width:140px;" />
        </el-form-item>
        <el-form-item label="来源">
          <el-input v-model="perfFlowForm.source" placeholder="银行卡/工资" style="width:100px;" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="perfFlowForm.remark" style="width:120px;" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="perfFlowSaving" @click="onSavePerfFlow">{{ perfFlowEditId ? '保存' : '新增' }}</el-button>
          <el-button v-if="perfFlowEditId" @click="cancelPerfFlowEdit">取消</el-button>
        </el-form-item>
      </el-form>
      <el-table :data="perfFlows" stripe size="small" style="width:100%;" aria-label="组合资金流水">
        <el-table-column prop="date" label="日期" width="110" />
        <el-table-column prop="flow_type" label="类型" width="70">
          <template #default="s">
            <el-tag :type="s.row.flow_type === '投入' ? 'danger' : 'success'" size="small">{{ s.row.flow_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="金额" width="130" align="right">
          <template #default="s">{{ formatMoney(s.row.amount) }}</template>
        </el-table-column>
        <el-table-column prop="source" label="来源" width="100" />
        <el-table-column prop="remark" label="备注" min-width="120" />
        <el-table-column label="操作" width="140" align="center">
          <template #default="s">
            <el-button type="primary" size="small" text @click="startPerfFlowEdit(s.row)">编辑</el-button>
            <el-button type="danger" size="small" text :loading="perfFlowDeleting === s.row.id" :disabled="perfFlowDeleting !== null" @click="onDeletePerfFlow(s.row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

  </PageShell>
</template>

<script setup>
import PageShell from '../components/PageShell.vue';
import MetricCard from '../components/MetricCard.vue';
import { ref, computed, onMounted, watch } from 'vue';
import { ElMessageBox } from 'element-plus';
import { useAppCtx } from '../composables/useAppCtx.js';
import { formatPercent } from '../utils/index.js';

const {
  formatMoney, pct,
  perfSummary, perfTimeline, perfContribution, perfFlows, perfStory, perfLoading, perfFlowForm,
  hasPerfFlows, perfStoryToneType,
  perfPrimaryCards, perfSecondaryCards,
  fetchPerformance, addPerfFlow, updatePerfFlow, deletePerfFlow,
  loadPerfFlowSuggestions, applyPerfFlowSuggestion,
  showTransactions, goTab,
  // 新专业指标
  perfRiskMetrics,
  perfContributionSummary,
  // 时间轴收益尺
  perfWindowCards,
  selectPerfWindow,
  // 每日收益
  perfDailyRows,
  perfDailyStats,
  perfLatestSnapshotDate,
  perfTodayRow,
  todaySnapshotDone,
  createSnapshot,
} = useAppCtx();

const perfFlowSuggestions = ref([]);
const perfSuggestLoading = ref(false);
const perfFlowEditId = ref(null);
const perfFlowSaving = ref(false);
const perfFlowDeleting = ref(null);
const perfSuggestionApplying = ref(false);

// === 每日收益 ===
const dailyRange = ref(30);
const dailySnapshotSaving = ref(false);

/** 展示用：图表按日期升序，表格按日期降序 */
const dailyRowsForRange = computed(() => {
  const all = perfDailyRows.value || [];
  return dailyRange.value > 0 ? all.slice(0, dailyRange.value) : all;
});
const dailyTodayRow = computed(() => {
  const row = perfTodayRow.value;
  return row ? { ...row, isToday: true } : null;
});
const dailyTableRows = computed(() => {
  const rows = dailyRowsForRange.value.map((row) => ({
    ...row,
    ...(priceFlagsByDate.value[String(row.date)] || {}),
  }));
  // 快照一天才写一条，列表天然只到昨天；把"今日（未收盘）"补在最前面，
  // 否则用户打开收益分析看不到今天赚了多少。
  return dailyTodayRow.value ? [dailyTodayRow.value, ...rows] : rows;
});
const dailyChartRows = computed(() => {
  const asc = [...dailyRowsForRange.value].reverse();
  return dailyTodayRow.value ? [...asc, dailyTodayRow.value] : asc;
});
// timeline 里每行的价格新鲜度（后端新增字段 price_stale / price_date / unpriced_count）。
// buildDailyPnlRows 不搬这几个字段，所以按日期在这里补上。
const priceFlagsByDate = computed(() => {
  const map = {};
  for (const r of perfTimeline.value || []) {
    if (!r) continue;
    map[String(r.date || '')] = {
      priceStale: Number(r.price_stale || 0) === 1 || r.price_stale === true,
      priceDate: r.price_date || null,
      unpricedCount: r.unpriced_count == null ? 0 : Number(r.unpriced_count),
    };
  }
  return map;
});

const dailyBestText = computed(() => {
  const b = perfDailyStats.value.best;
  return b ? `${b.date.slice(5)} ${formatMoney(b.change, 2, true)}` : '—';
});
const dailyWorstText = computed(() => {
  const w = perfDailyStats.value.worst;
  return w ? `${w.date.slice(5)} ${formatMoney(w.change, 2, true)}` : '—';
});

async function renderDailyChart() {
  const { renderDailyPnlChartView, waitForChartDom } = await import('../charts/index.js');
  // 卡片在"无快照"时是 v-else 分支，DOM 还没挂上就渲染会静默失败
  await waitForChartDom(['dailyPnlChart']);
  renderDailyPnlChartView(dailyChartRows.value);
}
/**
 * 记录今日快照。
 * 后端闸门：最新价不是今天的 → 409，detail 里带基准日期；用户确认后带 force 重记一次。
 * createSnapshot(force) 由 appCtx 提供（api 层的签名由他人负责）。
 */
async function postTodaySnapshot(force) {
  try {
    return await createSnapshot(force);
  } catch (e) {
    if (e?.response?.status !== 409) throw e;
    const detail = e?.response?.data?.detail || '最新价不是今天的价格，确认后仍要记录今天的快照吗？';
    try {
      await ElMessageBox.confirm(detail, '价格未更新', {
        type: 'warning',
        confirmButtonText: '仍要记录',
        cancelButtonText: '取消',
      });
    } catch (confirmErr) {
      if (confirmErr === 'cancel' || confirmErr === 'close') return undefined;
      throw confirmErr;
    }
    try {
      // 还没支持 force 的实现会再抛一次 409：这里不再弹第二次确认，错误提示交给模块
      return await createSnapshot(true);
    } catch (retryErr) {
      console.error('createSnapshot(force)', retryErr);
      return undefined;
    }
  }
}

async function onCreateTodaySnapshot() {
  if (dailySnapshotSaving.value) return;
  dailySnapshotSaving.value = true;
  try {
    await postTodaySnapshot(false);
    await fetchPerformance();
  } catch (e) {
    console.error('记录今日快照失败', e);
  } finally {
    dailySnapshotSaving.value = false;
  }
}

// 直接打开 /performance（书签、F5）时，main.js 里按 tab 触发的加载不会跑，
// 页面会一直是空的 —— 这里补一次首屏加载。
onMounted(async () => {
  if (!perfSummary.value) await fetchPerformance();
  await renderDailyChart();
});

watch(dailyChartRows, () => { renderDailyChart(); });

const latestCategoryAlloc = computed(() => {
  const rows = perfContribution.value || [];
  const buckets = { equity: 0, bond: 0, reit: 0 };
  for (const r of rows) {
    const cat = String(r?.category || "").toUpperCase();
    const mv = Number(r?.market_value || 0);
    if (cat.includes("REIT")) {
      buckets.reit += mv;
    } else if (cat.includes("债") || cat.includes("固收") || cat.includes("货币") || cat.includes("现金")) {
      buckets.bond += mv;
    } else {
      buckets.equity += mv;
    }
  }
  return {
    equity: buckets.equity,
    bond: buckets.bond,
    reit: buckets.reit,
    total: buckets.equity + buckets.bond + buckets.reit,
  };
});

const categorySummary = computed(() => {
  const contribList = perfStory.value?.category_contrib || [];
  const alloc = latestCategoryAlloc.value;
  const tot = alloc.total || 1;

  const cMap = {};
  contribList.forEach((c) => { cMap[c.name] = Number(c.amount || 0); });

  const order = ['权益', '债基', 'REITs'];
  return order.map((name) => {
    let allocAmt = 0;
    if (name === '权益') allocAmt = alloc.equity;
    else if (name === '债基') allocAmt = alloc.bond;
    else allocAmt = alloc.reit;

    const allocPct = tot > 0 ? (allocAmt / tot * 100) : 0;
    const contrib = cMap[name] || 0;
    return { name, allocAmt: Math.round(allocAmt), allocPct: Math.round(allocPct * 10) / 10, contrib };
  }).filter((x) => x.allocAmt > 0 || Math.abs(x.contrib) > 0.01);
});

const scrollToFlows = () => {
  const el = document.getElementById('perf-flow-section');
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
};

const startPerfFlowEdit = (row) => {
  if (!row) return;
  perfFlowEditId.value = row.id;
  perfFlowForm.value = {
    date: row.date,
    flow_type: row.flow_type || '投入',
    amount: Number(row.amount || 0),
    source: row.source || '',
    remark: row.remark || '',
  };
};

const cancelPerfFlowEdit = () => {
  perfFlowEditId.value = null;
};

const savePerfFlow = async () => {
  if (perfFlowEditId.value) {
    await updatePerfFlow(perfFlowEditId.value, { ...perfFlowForm.value });
    perfFlowEditId.value = null;
  } else {
    await addPerfFlow();
  }
};

// 防连点：保存/新增走同一个按钮，模块里只有 addPerfFlow 有内部标志（且不可见），
// updatePerfFlow 没有 —— 这里统一用本页的 ref 挡住。
async function onSavePerfFlow() {
  if (perfFlowSaving.value) return;
  perfFlowSaving.value = true;
  try {
    await savePerfFlow();
  } finally {
    perfFlowSaving.value = false;
  }
}

const onLoadFlowSuggest = async () => {
  if (perfSuggestLoading.value) return;
  perfSuggestLoading.value = true;
  try {
    const data = await loadPerfFlowSuggestions();
    perfFlowSuggestions.value = data?.drafts || [];
    scrollToFlows();
  } finally {
    perfSuggestLoading.value = false;
  }
};

const onContribRowClick = (row) => {
  if (!row?.code) return;
  if (typeof showTransactions === 'function') {
    showTransactions(row);
  } else if (typeof goTab === 'function') {
    goTab('holdings');
  }
};

// 删除流水 / 记入建议：模块里的 perfFlowSubmitting 未导出，in-flight 只能在本页兜住。
async function onDeletePerfFlow(id) {
  if (perfFlowDeleting.value !== null) return;
  perfFlowDeleting.value = id;
  try {
    await deletePerfFlow(id);
  } finally {
    perfFlowDeleting.value = null;
  }
}

async function onApplyPerfFlowSuggestion(row) {
  if (perfSuggestionApplying.value) return;
  perfSuggestionApplying.value = true;
  try {
    await applyPerfFlowSuggestion(row);
  } finally {
    perfSuggestionApplying.value = false;
  }
}
</script>

<style scoped>
.perf-flow-alert { margin-bottom: 14px; }

/* 每日收益 */
.perf-daily-card { margin-bottom: 14px; }
.perf-daily-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.perf-daily-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.perf-daily-chart { width: 100%; height: 260px; }
.perf-up { color: var(--app-up); font-variant-numeric: tabular-nums; }
.perf-down { color: var(--app-down); font-variant-numeric: tabular-nums; }
.perf-section-title {
  font-weight: 700;
  font-size: 16px;
  color: var(--app-text);
}
.perf-metric-card.is-secondary {
  background: color-mix(in srgb, var(--app-surface) 92%, var(--app-bg0));
}
.perf-cat-list { display: flex; flex-direction: column; gap: 14px; }
.perf-cat-row { display: grid; grid-template-columns: 72px 1fr 110px; gap: 10px; align-items: center; }
.perf-cat-name { font-size: 13px; color: var(--app-muted); }
.perf-cat-track {
  height: 18px;
  background: color-mix(in srgb, var(--app-border) 80%, var(--app-surface));
  border-radius: 999px;
  overflow: hidden;
}
.perf-cat-fill { height: 100%; border-radius: 999px; background: linear-gradient(90deg, var(--app-up), color-mix(in srgb, var(--app-up) 85%, #fff)); }
.perf-cat-fill.is-pos { background: linear-gradient(90deg, color-mix(in srgb, var(--app-up) 55%, transparent), var(--app-up)); }
.perf-cat-fill.is-neg { background: linear-gradient(90deg, color-mix(in srgb, var(--app-down) 55%, transparent), var(--app-down)); }
.perf-cat-amt { text-align: right; font-weight: 650; font-variant-numeric: tabular-nums; font-size: 13px; }
.perf-help-collapse { border: none; }
.perf-help-collapse :deep(.el-collapse-item__header) {
  font-weight: 600;
  color: var(--app-muted);
  border-radius: 10px;
  background: color-mix(in srgb, var(--app-surface) 90%, var(--app-bg0));
  padding: 0 12px;
  height: 44px;
  border: 1px solid var(--app-border);
}
.perf-help-collapse :deep(.el-collapse-item__wrap) { border: none; background: transparent; }
.perf-help-collapse :deep(.el-collapse-item__content) {
  padding: 12px 2px 4px;
  color: var(--app-text);
}
.perf-contrib-table { cursor: pointer; }

/* 时间轴收益尺 */
.perf-window-strip {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}
.perf-window-card {
  background: var(--app-surface, #fff);
  border: 1px solid var(--app-border, #e5e7eb);
  border-radius: 10px;
  padding: 10px 12px;
  cursor: pointer;
  transition: border-color .15s, box-shadow .15s, transform .12s;
  user-select: none;
}
.perf-window-card:hover { border-color: var(--app-primary, #409eff); transform: translateY(-1px); }
.perf-window-card.is-active {
  border-color: var(--app-primary, #409eff);
  box-shadow: 0 0 0 1px var(--app-primary, #409eff);
  background: color-mix(in srgb, var(--app-primary, #409eff) 7%, var(--app-surface, #fff));
}
.perf-window-card.is-disabled { cursor: default; opacity: .6; }
.perf-window-card.is-disabled:hover { border-color: var(--app-border, #e5e7eb); transform: none; }
.perf-window-label { font-size: 12px; color: var(--app-muted, #6b7280); margin-bottom: 4px; }
.perf-window-gain { font-size: 15px; font-weight: 700; color: var(--app-text, #111); }
.perf-window-card.is-up .perf-window-gain { color: var(--app-up, #e74c3c); }
.perf-window-card.is-down .perf-window-gain { color: var(--app-down, #07c160); }
.perf-window-pct { font-size: 12px; color: var(--app-soft, #9ca3af); margin-top: 2px; }
.perf-window-card.is-up .perf-window-pct { color: var(--app-up, #e74c3c); }
.perf-window-card.is-down .perf-window-pct { color: var(--app-down, #07c160); }
.perf-window-strip.is-loading { opacity: .5; pointer-events: none; }

@media (max-width: 640px) {
  .perf-window-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .perf-cat-row { grid-template-columns: 64px 1fr 90px; }
}
.perf-window-stale { font-size: 11px; color: var(--app-warn, #c98a2e); margin-top: 2px; }
</style>
