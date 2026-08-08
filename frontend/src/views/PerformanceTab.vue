<template>
  <PageShell
    title="收益分析"
    subtitle="先看整户赚没赚，再看谁贡献。数字和券商对不上时，多半是口径不同。"
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
        <div class="perf-window-gain">{{ w.gain != null ? (w.gain >= 0 ? '+' : '') + formatMoney(w.gain, 0, true) : '—' }}</div>
        <div class="perf-window-pct">{{ w.gainPct != null ? (w.gainPct >= 0 ? '+' : '') + w.gainPct.toFixed(1) + '%' : '无快照' }}</div>
      </div>
    </div>

    <!-- 未录流水强提示 -->
    <el-alert
      v-if="!hasPerfFlows"
      type="warning"
      show-icon
      :closable="false"
      class="perf-flow-alert"
      title="外部资金流水还没录：净投入、整户总收益、年化只当参考。点下方可跳到录入区，或从银证生成建议。"
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
        :plain="m.plain"
        :label="m.label"
        :value="m.value"
        :sub="m.sub"
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
        :plain="m.plain"
        :label="m.label"
        :value="m.value"
        :sub="m.sub"
        :color="m.color"
        secondary
        :title="m.value"
      />
    </div>

        <!-- 组合风险（精简 3 张核心） -->
    <el-card shadow="never" style="margin-bottom: 14px;">
      <div style="margin-bottom:8px;">
        <div class="perf-contrib-title">风险一览</div>
        <div class="perf-contrib-sub">最大回撤 = 历史最高点跌到最低点的跌幅。年化波动 = 平时上下抖多大。</div>
      </div>

      <div class="ledger-metrics cols-3" style="margin-bottom:8px;">
        <MetricCard
          label="最大回撤"
          :value="((perfRiskMetrics?.maxDrawdownPct) || 0) + '%'"
          :sub="(perfRiskMetrics?.peakDate) && (perfRiskMetrics?.troughDate) ? (perfRiskMetrics.peakDate + ' → ' + perfRiskMetrics.troughDate) : '基于历史快照'"
          :tone="(perfRiskMetrics?.maxDrawdown || 0) > 0.05 ? 'down' : 'neutral'"
        />
        <MetricCard
          v-if="perfSummary?.underwater"
          label="当前离峰值"
          :value="(perfSummary.underwater.underwater_pct || 0) + '%'"
          :sub="'峰值日 ' + (perfSummary.underwater.peak_date || '—')"
          :tone="(perfSummary.underwater.underwater_pct || 0) > 5 ? 'down' : 'neutral'"
        />
        <MetricCard
          label="年化波动"
          :value="(perfRiskMetrics?.approxVol) != null ? (perfRiskMetrics.approxVol) + '%' : '—'"
          sub="平时上下抖多大幅度"
          :tone="(perfRiskMetrics?.approxVol || 0) > 15 ? 'down' : 'neutral'"
        />
      </div>
      </el-card>

      <!-- 流水 -->
    <el-card id="perf-flow-section" shadow="never" style="margin-bottom: 14px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;gap:12px;flex-wrap:wrap;">
        <div>
          <div class="perf-section-title">组合资金流水（外部投入/取出）</div>
          <div class="perf-contrib-sub">只记塞进组合或从组合提走的钱。买卖、银证互转不要记这里。</div>
        </div>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
          <el-button size="small" @click="onLoadFlowSuggest" :loading="perfSuggestLoading">从银证生成建议</el-button>
          <el-tag size="small">共 {{ perfFlows.length }} 笔</el-tag>
        </div>
      </div>
      <div v-if="perfFlowSuggestions.length" class="perf-suggest-box" style="margin-bottom:12px;">
        <div class="perf-contrib-sub" style="margin-bottom:8px;">建议草稿（点「记入」才写入）</div>
        <el-table :data="perfFlowSuggestions" size="small" stripe>
          <el-table-column prop="date" label="日期" width="110" />
          <el-table-column prop="flow_type" label="类型" width="70" />
          <el-table-column label="金额" width="120" align="right">
            <template #default="s">{{ formatMoney(s.row.amount) }}</template>
          </el-table-column>
          <el-table-column prop="remark" label="说明" min-width="180" show-overflow-tooltip />
          <el-table-column label="操作" width="90">
            <template #default="s">
              <el-button type="primary" link size="small" @click="applyPerfFlowSuggestion(s.row)">记入</el-button>
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
          <el-button type="primary" @click="savePerfFlow">{{ perfFlowEditId ? '保存' : '新增' }}</el-button>
          <el-button v-if="perfFlowEditId" @click="cancelPerfFlowEdit">取消</el-button>
        </el-form-item>
      </el-form>
      <el-table :data="perfFlows" stripe size="small" style="width:100%;">
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
            <el-button type="danger" size="small" text @click="deletePerfFlow(s.row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 口径折叠 -->
    <el-collapse class="perf-help-collapse">
      <el-collapse-item title="怎么看 / 口径说明（备查）" name="help">
        <div class="perf-guide-grid" style="margin-bottom: 12px;">
          <div class="perf-guide-card" v-for="item in perfGuideSteps" :key="item.step">
            <div class="perf-guide-step">{{ item.step }}</div>
            <div class="perf-guide-body">
              <div class="perf-guide-title">{{ item.title }}</div>
              <div class="perf-guide-text">{{ item.text }}</div>
            </div>
          </div>
        </div>
        <el-table :data="perfLensRows" size="small" class="perf-lens-table" style="width: 100%; margin-bottom: 12px;">
          <el-table-column prop="name" label="口径" width="120" />
          <el-table-column prop="where" label="在哪里看" min-width="160" />
          <el-table-column prop="meaning" label="怎么算" min-width="200" />
          <el-table-column prop="goodFor" label="适合回答" min-width="200" />
          <el-table-column prop="notFor" label="不要拿它当" min-width="180" />
        </el-table>
        <el-descriptions :column="1" size="small" border>
          <el-descriptions-item label="累计净投入">投入合计 − 取出合计（仅组合外部资金）</el-descriptions-item>
          <el-descriptions-item label="累计总收益">当前总资产 − 累计净投入</el-descriptions-item>
          <el-descriptions-item label="XIRR 年化">外部现金流 + 当前总资产的资金加权年化</el-descriptions-item>
          <el-descriptions-item label="当前仓贡献">浮盈 + 分红；不含已卖出</el-descriptions-item>
          <el-descriptions-item label="全周期盈亏">接近券商累计；分红已在摊薄成本中</el-descriptions-item>
          <el-descriptions-item label="YTD">年初至今 = 当前总资产 − 年初快照 − 今年净投入变化</el-descriptions-item>
        </el-descriptions>
      </el-collapse-item>
    </el-collapse>
  </PageShell>
</template>

<script setup>
import PageShell from '../components/PageShell.vue';
import MetricCard from '../components/MetricCard.vue';
import { ref, watch, computed } from 'vue';
import { useAppCtx } from '../composables/useAppCtx.js';

const {
  formatMoney, pct,
  perfSummary, perfTimeline, perfContribution, perfFlows, perfStory, perfLoading, perfFlowForm,
  hasPerfFlows, perfStoryToneType, perfGuideSteps, perfLensRows,
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
} = useAppCtx();

const perfFlowSuggestions = ref([]);
const perfSuggestLoading = ref(false);
const perfFlowEditId = ref(null);
const catTrendMode = ref('value');

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

const onLoadFlowSuggest = async () => {
  perfSuggestLoading.value = true;
  try {
    const data = await loadPerfFlowSuggestions();
    perfFlowSuggestions.value = data?.drafts || [];
    scrollToFlows();
  } finally {
    perfSuggestLoading.value = false;
  }
};


async function renderCategoryTrend() {
  if (!perfTimeline.value || perfTimeline.value.length < 1) return;
  try {
    const { renderCategoryTrendChartView, waitForChartDom } = await import('../charts/index.js');
    const ready = await waitForChartDom(['categoryTrendChart'], { timeoutMs: 1500 });
    if (!ready) return;
    await new Promise((r) => requestAnimationFrame(() => r()));
    renderCategoryTrendChartView(perfTimeline.value, catTrendMode.value);
  } catch (e) {
    // ignore if chart lib not ready
  }
}

// Auto-render category trend chart when timeline data is (re)loaded
watch(perfTimeline, () => {
  if (perfTimeline.value && perfTimeline.value.length >= 1) {
    requestAnimationFrame(() => {
      try { renderCategoryTrend(); } catch (_) {}
    });
  }
}, { deep: true });

const onContribRowClick = (row) => {
  if (!row?.code) return;
  if (typeof showTransactions === 'function') {
    showTransactions(row);
  } else if (typeof goTab === 'function') {
    goTab('holdings');
  }
};
</script>

<style scoped>
.perf-flow-alert { margin-bottom: 14px; }
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
</style>
