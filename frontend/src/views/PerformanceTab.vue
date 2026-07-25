<template>
  <div class="perf-page">
    <div class="perf-page-header">
      <div>
        <h3 class="perf-page-title">收益分析</h3>
        <div class="perf-page-subtitle">
          先看整户赚没赚，再看谁贡献。数字和券商对不上时，多半是口径不同。
        </div>
      </div>
      <div class="perf-page-actions">
        <el-radio-group v-model="localTimelineRange" size="small" @change="onRangeChange">
          <el-radio-button value="ytd">今年</el-radio-button>
          <el-radio-button value="1y">近一年</el-radio-button>
          <el-radio-button value="all">全部</el-radio-button>
        </el-radio-group>
        <el-tag :type="perfSummary?.xirr_status === 'ok' ? 'success' : (hasPerfFlows ? 'info' : 'warning')" size="small">
          {{ perfSummary?.xirr_status === 'ok' ? '年化已算' : (hasPerfFlows ? (perfSummary?.xirr_message || '年化暂不可用') : '外部流水未录入') }}
        </el-tag>
        <el-button size="small" @click="fetchPerformance" :loading="perfLoading">刷新</el-button>
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
      <div class="perf-story-cols" v-if="(perfStory.winners || []).length || (perfStory.losers || []).length">
        <div class="perf-story-col is-win" v-if="(perfStory.winners || []).length">
          <div class="perf-story-col-title">赚钱靠前</div>
          <div v-for="w in perfStory.winners" :key="'w'+w.code" class="perf-story-col-row">{{ w.text }}</div>
        </div>
        <div class="perf-story-col is-lose" v-if="(perfStory.losers || []).length">
          <div class="perf-story-col-title">拖累靠前</div>
          <div v-for="w in perfStory.losers" :key="'l'+w.code" class="perf-story-col-row">{{ w.text }}</div>
        </div>
      </div>
    </el-card>

    <!-- 主卡 4 -->
    <el-row :gutter="12" class="perf-cards-row" style="margin-bottom: 12px;">
      <el-col :xs="12" :sm="12" :md="6" v-for="m in perfPrimaryCards" :key="m.label">
        <el-card shadow="hover" class="perf-metric-card">
          <div class="perf-metric-plain">{{ m.plain }}</div>
          <div class="perf-metric-label">{{ m.label }}</div>
          <div class="perf-metric-value" :style="{ color: m.color || '#303133' }">{{ m.value }}</div>
          <div class="perf-metric-sub" :title="m.sub">{{ m.sub }}</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 次卡 3 -->
    <el-row :gutter="12" class="perf-cards-row" style="margin-bottom: 14px;">
      <el-col :xs="12" :sm="8" :md="8" v-for="m in perfSecondaryCards" :key="m.label">
        <el-card shadow="never" class="perf-metric-card is-secondary">
          <div class="perf-metric-plain">{{ m.plain }}</div>
          <div class="perf-metric-label">{{ m.label }}</div>
          <div class="perf-metric-value" :style="{ color: m.color || '#303133' }">{{ m.value }}</div>
          <div class="perf-metric-sub" :title="m.sub">{{ m.sub }}</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 大类贡献 -->
    <el-card v-if="perfCategoryBars.length" shadow="never" style="margin-bottom: 14px;">
      <div class="perf-contrib-title" style="margin-bottom: 10px;">大类贡献（当前仓）</div>
      <div class="perf-cat-list">
        <div v-for="c in perfCategoryBars" :key="c.name" class="perf-cat-row">
          <div class="perf-cat-name">{{ c.name }}</div>
          <div class="perf-cat-track">
            <div
              class="perf-cat-fill"
              :class="c.positive ? 'is-pos' : 'is-neg'"
              :style="{ width: c.widthPct + '%' }"
            ></div>
          </div>
          <div class="perf-cat-amt" :style="{ color: c.positive ? '#F56C6C' : '#67C23A' }">
            {{ formatMoney(c.amount, 2, true) }}
          </div>
        </div>
      </div>
    </el-card>

    <!-- 时间轴 -->
    <el-row :gutter="20" style="margin-bottom: 14px;" v-if="perfTimeline.length > 1">
      <el-col :span="24">
        <el-card shadow="never">
          <template #header>
            <div>
              <div class="perf-contrib-title">资产 vs 净投入</div>
              <div class="perf-contrib-sub">蓝线总资产，橙线累计净投入。资产在净投入上方表示整户赚钱。时间范围见页顶筛选。</div>
            </div>
          </template>
          <div id="perfTimelineChart" style="height: 280px;"></div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 贡献表 -->
    <el-card shadow="never" style="margin-bottom: 14px;">
      <div class="perf-contrib-toolbar">
        <div>
          <div class="perf-contrib-title">标的收益贡献</div>
          <div class="perf-contrib-sub">默认当前仓贡献；对账优先看全周期。点名称可看该标的交易。</div>
        </div>
        <div class="perf-contrib-controls">
          <el-tag size="small" type="info">共 {{ perfContribution.length }} 个</el-tag>
          <el-select v-model="perfContributionFilter" size="small" style="width: 110px;">
            <el-option label="全部" value="all" />
            <el-option label="正贡献" value="positive" />
            <el-option label="负贡献" value="negative" />
          </el-select>
          <el-select v-model="perfContributionSort" size="small" style="width: 140px;">
            <el-option label="当前仓贡献" value="contribution" />
            <el-option label="全周期盈亏" value="lifetime" />
            <el-option label="收益占比" value="share" />
            <el-option label="市值" value="market_value" />
          </el-select>
        </div>
      </div>
      <div class="perf-contrib-summary">
        <div class="perf-summary-pill is-positive">
          <div class="perf-summary-label">头号来源</div>
          <div class="perf-summary-main">{{ perfContributionHeadline.best?.name || '—' }}</div>
          <div class="perf-summary-sub">{{ perfContributionHeadline.best ? formatMoney(perfContributionHeadline.best.total_contribution, 2, true) : '暂无' }}</div>
        </div>
        <div class="perf-summary-pill is-negative">
          <div class="perf-summary-label">最大拖累</div>
          <div class="perf-summary-main">{{ perfContributionHeadline.worst?.name || '—' }}</div>
          <div class="perf-summary-sub">{{ perfContributionHeadline.worst ? formatMoney(perfContributionHeadline.worst.total_contribution, 2, true) : '暂无' }}</div>
        </div>
        <div class="perf-summary-pill is-neutral">
          <div class="perf-summary-label">结构</div>
          <div class="perf-summary-main">正 {{ perfContributionMix.positiveCount }} / 负 {{ perfContributionMix.negativeCount }}</div>
          <div class="perf-summary-sub">前 3 合计 {{ formatMoney(perfContributionMix.top3Contribution, 2, true) }}</div>
        </div>
      </div>
      <el-table
        :data="displayedPerfContribution"
        stripe
        size="small"
        class="perf-contrib-table data-table"
        style="width: 100%"
        @row-click="onContribRowClick"
      >
        <el-table-column label="标的" min-width="180" fixed="left">
          <template #default="s">
            <div class="perf-name-cell">
              <span class="perf-rank-badge" :class="{ 'perf-rank-top': s.$index < 3 }">{{ s.$index + 1 }}</span>
              <div class="perf-name-main">
                <div class="perf-name-title">{{ s.row.name }}</div>
                <div class="perf-name-code">{{ s.row.code }} · {{ s.row.category || '未分类' }}</div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="市值" min-width="110" align="right" header-align="right">
          <template #default="s">
            <div>{{ formatMoney(s.row.market_value) }}</div>
            <div class="perf-contrib-share">占比 {{ pct(s.row.market_value, perfSummary?.total_assets || 0) }}</div>
          </template>
        </el-table-column>
        <el-table-column label="当前仓贡献" min-width="130" align="right" header-align="right">
          <template #header>
            <el-tooltip content="浮盈 + 累计分红；只看当前仓" placement="top">
              <span>当前仓贡献</span>
            </el-tooltip>
          </template>
          <template #default="s">
            <div class="perf-contrib-value" :style="{ color: s.row.total_contribution >= 0 ? '#F56C6C' : '#67C23A' }">
              {{ formatMoney(s.row.total_contribution, 2, true) }}
            </div>
          </template>
        </el-table-column>
        <el-table-column label="全周期" min-width="120" align="right" header-align="right">
          <template #header>
            <el-tooltip content="接近券商累计盈亏" placement="top">
              <span>全周期</span>
            </el-tooltip>
          </template>
          <template #default="s">
            <span :style="{ color: (s.row.lifetime_profit || 0) >= 0 ? '#F56C6C' : '#67C23A' }">
              {{ formatMoney(s.row.lifetime_profit || 0, 2, true) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="强度" min-width="140">
          <template #default="s">
            <div class="perf-bar-track">
              <div class="perf-bar-fill" :style="contributionBarStyle(s.row.total_contribution)"></div>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 流水 -->
    <el-card id="perf-flow-section" shadow="never" style="margin-bottom: 14px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;gap:12px;flex-wrap:wrap;">
        <div>
          <div style="font-weight:700;font-size:16px;color:#303133;">组合资金流水（外部投入/取出）</div>
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
  </div>
</template>

<script setup>
import { ref, watch } from 'vue';
import { useAppCtx } from '../composables/useAppCtx.js';

const {
  formatMoney, pct,
  perfSummary, perfTimeline, perfContribution, perfFlows, perfStory, perfLoading, perfFlowForm,
  hasPerfFlows, perfStoryToneType, perfGuideSteps, perfLensRows,
  perfPrimaryCards, perfSecondaryCards, perfCategoryBars,
  displayedPerfContribution, perfContributionFilter, perfContributionSort,
  perfContributionHeadline, perfContributionMix, perfTimelineRange,
  fetchPerformance, setPerfTimelineRange, addPerfFlow, updatePerfFlow, deletePerfFlow,
  loadPerfFlowSuggestions, applyPerfFlowSuggestion, contributionBarStyle,
  showTransactions, goTab,
} = useAppCtx();

const perfFlowSuggestions = ref([]);
const perfSuggestLoading = ref(false);
const perfFlowEditId = ref(null);
const localTimelineRange = ref(perfTimelineRange?.value || 'all');

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
.perf-metric-card.is-secondary { background: #fafbfc; }
.perf-cat-list { display: flex; flex-direction: column; gap: 10px; }
.perf-cat-row { display: grid; grid-template-columns: 88px 1fr 110px; gap: 10px; align-items: center; }
.perf-cat-name { font-size: 13px; color: #606266; }
.perf-cat-track { height: 10px; background: #eef2f7; border-radius: 999px; overflow: hidden; }
.perf-cat-fill { height: 100%; border-radius: 999px; }
.perf-cat-fill.is-pos { background: linear-gradient(90deg, #f89898, #F56C6C); }
.perf-cat-fill.is-neg { background: linear-gradient(90deg, #95d475, #67C23A); }
.perf-cat-amt { text-align: right; font-weight: 650; font-variant-numeric: tabular-nums; font-size: 13px; }
.perf-help-collapse { border: none; }
.perf-help-collapse :deep(.el-collapse-item__header) {
  font-weight: 600;
  color: #606266;
  border-radius: 10px;
  background: #f8fafc;
  padding: 0 12px;
  height: 44px;
  border: 1px solid #ebeef5;
}
.perf-help-collapse :deep(.el-collapse-item__wrap) { border: none; background: transparent; }
.perf-help-collapse :deep(.el-collapse-item__content) { padding: 12px 2px 4px; }
.perf-contrib-table { cursor: pointer; }
@media (max-width: 640px) {
  .perf-cat-row { grid-template-columns: 72px 1fr 90px; }
}
</style>
