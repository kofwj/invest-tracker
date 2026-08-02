<template>
  <PageShell
    title="收益分析"
    subtitle="先看整户赚没赚，再看谁贡献。数字和券商对不上时，多半是口径不同。"
  >
    <template #actions>

        <el-radio-group v-model="localTimelineRange" size="small" @change="onRangeChange">
          <el-radio-button value="ytd">今年</el-radio-button>
          <el-radio-button value="1y">近一年</el-radio-button>
          <el-radio-button value="all">全部</el-radio-button>
        </el-radio-group>
        <el-tag :type="perfSummary?.xirr_status === 'ok' ? 'success' : (hasPerfFlows ? 'info' : 'warning')" size="small">
          {{ perfSummary?.xirr_status === 'ok' ? '年化已算' : (hasPerfFlows ? (perfSummary?.xirr_message || '年化暂不可用') : '外部流水未录入') }}
        </el-tag>
        <el-button size="small" @click="fetchPerformance" :loading="perfLoading">刷新</el-button>
      
    </template>

    <!-- 加载骨架 -->
    <div v-if="perfLoading && !perfSummary" class="sk-metrics" aria-hidden="true">
      <div v-for="i in 4" :key="'sk'+i" class="sk-block sk-metric"></div>
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

        <!-- 大类结构 - 漂亮版 -->
    <el-card v-if="categorySummary.length" shadow="never" style="margin-bottom: 10px;">
      <div style="display:flex; justify-content:space-between; align-items:baseline; margin-bottom:6px;">
        <div class="perf-contrib-title">我现在钱是怎么分的</div>
        <div style="font-size:11px; color:var(--app-muted);">当前持仓占比 + 浮盈+分红</div>
      </div>

      <div class="perf-cat-list">
        <div v-for="c in categorySummary" :key="c.name" class="perf-cat-row">
          <div class="perf-cat-name">{{ c.name }}</div>

          <div class="perf-cat-alloc">
            <div class="perf-cat-track">
              <div class="perf-cat-fill" 
                   :style="{ width: Math.max(5, c.allocPct) + '%' }"></div>
            </div>
            <div class="alloc-meta">
              <span class="alloc-pct">{{ c.allocPct }}%</span>
              <span class="alloc-amt">{{ (c.allocAmt / 10000).toFixed(1) }}万</span>
            </div>
          </div>

          <div class="perf-cat-contrib">
            <div class="perf-cat-amt" :class="c.contrib >= 0 ? 'num-up' : 'num-down'">
              {{ formatMoney(c.contrib, 2, true) }}
            </div>
            <div class="contrib-sub">浮盈+分红</div>
          </div>
        </div>
      </div>
    </el-card>

    <!-- 大类资产走势 -->
    <el-card shadow="never" style="margin-bottom: 14px;">
      <template #header>
        <div style="display:flex; align-items:center; justify-content:space-between; gap:8px; flex-wrap:wrap;">
          <div>
            <div class="perf-contrib-title" style="margin-bottom:2px;">大类资产走势</div>
            <div class="perf-contrib-sub" style="margin:0;">权益 / 债基 / REITs</div>
          </div>
          <el-radio-group v-model="catTrendMode" size="small" @change="renderCategoryTrend">
            <el-radio-button value="value">市值</el-radio-button>
            <el-radio-button value="pct">占比</el-radio-button>
          </el-radio-group>
        </div>
      </template>
      <div id="categoryTrendChart" style="height: 260px;"></div>
    </el-card>

    <!-- 时间轴 -->
    <el-row :gutter="20" style="margin-bottom: 14px;" v-if="perfTimeline.length > 1">
      <el-col :span="24">
        <el-card shadow="never">
          <template #header>
            <div>
              <div class="perf-contrib-title">我的钱是怎么变的</div>
              <div class="perf-contrib-sub">蓝线 = 总资产　|　橙线 = 我累计净投入<br/>蓝线在橙线上方 = 整体赚钱</div>
            </div>
          </template>
          <div id="perfTimelineChart" style="height: 280px;"></div>
        </el-card>
      </el-col>
    </el-row>

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

      <el-collapse class="perf-advanced-collapse" style="margin-top: 8px;">
        <el-collapse-item title="更多指标（进阶）" name="advanced">
          <div style="font-size:12px;color:var(--app-muted);margin-bottom:10px;">想看细节再展开。</div>

          <div v-if="perfSummary?.twr != null" style="margin-bottom:8px; font-size:13px;">
            <strong>TWR（时间加权）{{ perfSummary.twr }}%</strong>
            <span style="color:var(--app-muted);"> —— 剥离你出金/入金时机，只看资产本身涨跌。</span>
          </div>

          <div v-if="perfSummary?.xirr != null && perfSummary?.twr != null" style="font-size:12px;color:var(--app-muted);margin-bottom:8px;">
            XIRR {{ perfSummary.xirr }}% vs TWR {{ perfSummary.twr }}% —— 差距反映现金流时机影响（正值通常意味着你在相对低位多投了）。
          </div>

          <div v-if="perfSummary?.rolling_returns && Object.keys(perfSummary.rolling_returns).length" style="margin-bottom:10px;">
            <div style="font-size:12px; color:var(--app-muted); margin-bottom:4px;">滚动收益率</div>
            <div style="display:flex; gap:14px; flex-wrap:wrap; font-size:13px;">
              <span v-for="(v, k) in perfSummary.rolling_returns" :key="k">
                <strong>{{ k }}</strong>: {{ v != null ? v + '%' : '—' }}
              </span>
            </div>
          </div>

          <div v-if="perfSummary?.monthly_stats" style="margin-bottom:8px; font-size:13px;">
            <span style="font-size:12px;color:var(--app-muted);">月度表现：</span>
            最好 {{ perfSummary.monthly_stats.best_month }}% ｜ 最差 {{ perfSummary.monthly_stats.worst_month }}%
            ｜ 平均 {{ perfSummary.monthly_stats.avg_monthly }}% ｜ 正收益月 {{ perfSummary.monthly_stats.positive_pct }}%
          </div>

          <div v-if="perfSummary?.dividend_contrib_pct != null" style="margin-bottom:8px; font-size:13px;">
            分红占浮盈+分红合计 <strong>{{ perfSummary.dividend_contrib_pct }}%</strong>
          </div>

          <div v-if="perfSummary?.sharpe != null" style="margin-bottom:8px; font-size:13px;">
            Sharpe {{ perfSummary.sharpe }} —— 每单位波动赚的超额（无风险利率≈2%）
          </div>

          <div v-if="perfSummary?.benchmark_relative && Object.keys(perfSummary.benchmark_relative).length" style="margin-bottom:8px; font-size:13px;">
            <span style="font-size:12px;color:var(--app-muted);">对比大盘：</span>
            <span v-for="(b, k) in perfSummary.benchmark_relative" :key="k" style="margin-right:10px;">
              {{ b.name }} 相对 {{ b.relative >= 0 ? '+' : '' }}{{ b.relative }}% (组合 {{ b.port_ret }}% / 基准 {{ b.bench_ret }}%)
            </span>
          </div>
        </el-collapse-item>
      </el-collapse>
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
  perfTimelineRange,
  fetchPerformance, setPerfTimelineRange, addPerfFlow, updatePerfFlow, deletePerfFlow,
  loadPerfFlowSuggestions, applyPerfFlowSuggestion,
  showTransactions, goTab,
  // 新专业指标
  perfRiskMetrics,
  perfContributionSummary,
} = useAppCtx();

const perfFlowSuggestions = ref([]);
const perfSuggestLoading = ref(false);
const perfFlowEditId = ref(null);
const localTimelineRange = ref(perfTimelineRange?.value || 'all');
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

watch(
  () => perfTimelineRange?.value,
  (v) => { if (v) localTimelineRange.value = v; },
);

const onRangeChange = (val) => {
  if (typeof setPerfTimelineRange === 'function') setPerfTimelineRange(val);
  else if (perfTimelineRange) {
    perfTimelineRange.value = val;
    fetchPerformance();
  }
};

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
.perf-advanced-collapse { border: none; }
.perf-advanced-collapse :deep(.el-collapse-item__header) {
  font-weight: 600;
  color: var(--app-muted);
  border-radius: 10px;
  background: color-mix(in srgb, var(--app-surface) 90%, var(--app-bg0));
  padding: 0 12px;
  height: 40px;
  border: 1px solid var(--app-border);
  font-size: 13px;
}
.perf-advanced-collapse :deep(.el-collapse-item__wrap) { border: none; background: transparent; }
.perf-advanced-collapse :deep(.el-collapse-item__content) {
  padding: 12px 2px 4px;
  color: var(--app-text);
}
@media (max-width: 640px) {
  .perf-cat-row { grid-template-columns: 64px 1fr 90px; }
}
</style>
