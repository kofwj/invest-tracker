<template>
  <div class="decision-page">
    <div class="decision-header">
      <div>
        <h3 class="decision-title">今天该看</h3>
        <div class="decision-subtitle">
          只读汇总：今日贡献、价格预警、纪律破线、存款到期。不改账本、不下单。
        </div>
      </div>
      <div class="decision-actions">
        <el-button size="small" :loading="marketLoading || disciplineLoading" @click="refreshDecision">刷新</el-button>
        <el-button size="small" @click="goTab('market')">市场摘要</el-button>
        <el-button size="small" @click="goTab('discipline')">纪律</el-button>
        <el-button size="small" @click="goTab('deposits')">存款</el-button>
      </div>
    </div>

    <el-alert
      :title="headline"
      type="info"
      show-icon
      :closable="false"
      style="margin-bottom: 14px;"
    />

    <el-row :gutter="12" style="margin-bottom: 16px;">
      <el-col :xs="12" :sm="8" :md="6">
        <el-card shadow="hover" class="decision-metric">
          <div class="decision-metric-label">今日贡献粗估</div>
          <div class="decision-metric-value" :style="{ color: (signals.today_contrib_estimate || 0) >= 0 ? '#F56C6C' : '#67C23A' }">
            {{ formatMoney(signals.today_contrib_estimate || 0, 2, true) }}
          </div>
          <div class="decision-metric-sub">现价涨跌% × 市值，非记账</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="6">
        <el-card shadow="hover" class="decision-metric">
          <div class="decision-metric-label">组合涨跌粗估</div>
          <div class="decision-metric-value">
            {{ signals.portfolio_change_pct_estimate == null
              ? '—'
              : ((signals.portfolio_change_pct_estimate >= 0 ? '+' : '') + Number(signals.portfolio_change_pct_estimate).toFixed(2) + '%') }}
          </div>
          <div class="decision-metric-sub">投资市值 {{ formatMoney(signals.total_market_value || 0) }}</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="6">
        <el-card shadow="hover" class="decision-metric">
          <div class="decision-metric-label">纪律破线</div>
          <div class="decision-metric-value" :class="breachCount ? 'is-warn' : 'is-ok'">{{ breachCount }}</div>
          <div class="decision-metric-sub">{{ summaryText || '暂无纪律摘要' }}</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="6">
        <el-card shadow="hover" class="decision-metric">
          <div class="decision-metric-label">存款 30 天内到期</div>
          <div class="decision-metric-value" :class="dueSoonCount ? 'is-warn' : ''">{{ dueSoonCount }} 笔</div>
          <div class="decision-metric-sub">金额 {{ formatMoney(dueSoonAmount) }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="12">
      <el-col :xs="24" :md="12" style="margin-bottom: 12px;">
        <el-card shadow="never">
          <template #header>
            <div class="decision-card-title">今天看点</div>
          </template>
          <ul v-if="highlights && highlights.length" class="decision-list">
            <li v-for="(line, idx) in highlights" :key="'h' + idx">{{ line }}</li>
          </ul>
          <div v-else class="decision-empty">暂无看点，可先刷新市场摘要。</div>
          <div v-if="comparisons && comparisons.length" class="decision-muted">
            <div v-for="(c, i) in comparisons" :key="'c' + i">{{ c.text || c }}</div>
          </div>
        </el-card>
      </el-col>

      <el-col :xs="24" :md="12" style="margin-bottom: 12px;">
        <el-card shadow="never">
          <template #header>
            <div class="decision-card-title">价格预警（最近触发）</div>
          </template>
          <el-table v-if="alerts && alerts.length" :data="alerts.slice(0, 8)" size="small" stripe>
            <el-table-column prop="name" label="名称" min-width="100" />
            <el-table-column prop="code" label="代码" width="90" />
            <el-table-column label="说明" min-width="140">
              <template #default="scope">{{ scope.row.message || scope.row.condition || '—' }}</template>
            </el-table-column>
          </el-table>
          <div v-else class="decision-empty">暂无触发预警。</div>
          <div style="margin-top:8px;">
            <el-button size="small" type="warning" :loading="alertChecking" @click="() => checkAlerts(false)">立即检查预警</el-button>
          </div>
        </el-card>
      </el-col>

      <el-col :xs="24" :md="12" style="margin-bottom: 12px;">
        <el-card shadow="never">
          <template #header>
            <div class="decision-card-title">纪律破线</div>
          </template>
          <el-table v-if="breachList && breachList.length" :data="breachList.slice(0, 8)" size="small" stripe>
            <el-table-column label="规则" min-width="120">
              <template #default="scope">{{ scope.row.rule || scope.row.title || scope.row.code || '—' }}</template>
            </el-table-column>
            <el-table-column label="说明" min-width="180">
              <template #default="scope">{{ scope.row.message || scope.row.detail || scope.row.reason || '—' }}</template>
            </el-table-column>
          </el-table>
          <div v-else class="decision-empty">当前未见破线（或尚未刷新纪律报告）。</div>
        </el-card>
      </el-col>

      <el-col :xs="24" :md="12" style="margin-bottom: 12px;">
        <el-card shadow="never">
          <template #header>
            <div class="decision-card-title">存款到期（30 天内 / 已到期）</div>
          </template>
          <el-table v-if="dueSoonRows.length" :data="dueSoonRows" size="small" stripe>
            <el-table-column prop="bank_name" label="银行" min-width="100" />
            <el-table-column label="金额" min-width="100">
              <template #default="scope">{{ formatMoney(scope.row.amount) }}</template>
            </el-table-column>
            <el-table-column prop="due_date" label="到期日" width="110" />
            <el-table-column label="剩余" width="90">
              <template #default="scope">
                <span :style="{ color: Number(scope.row.daysLeft) < 0 ? '#E6A23C' : '#606266' }">
                  {{ scope.row.daysLeft == null ? '—' : (scope.row.daysLeft < 0 ? '已到期' : scope.row.daysLeft + '天') }}
                </span>
              </template>
            </el-table-column>
          </el-table>
          <div v-else class="decision-empty">30 天内无到期存款。</div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue';
import { useAppCtx } from '../composables/useAppCtx.js';

const {
  activeTab,
  tabGroup,
  marketSignals,
  marketHighlights,
  marketComparisons,
  marketLoading,
  triggeredAlerts,
  alertChecking,
  checkAlerts,
  refreshMarket,
  breaches,
  summaryText,
  disciplineLoading,
  refreshDiscipline,
  depositRows,
  formatMoney,
} = useAppCtx();

const breachCount = computed(() => {
  const list = breaches?.value ?? breaches ?? [];
  return Array.isArray(list) ? list.length : 0;
});

const dueSoonRows = computed(() => {
  const rows = depositRows?.value ?? depositRows ?? [];
  return (Array.isArray(rows) ? rows : [])
    .filter((d) => d.daysLeft !== null && d.daysLeft !== undefined && Number(d.daysLeft) <= 30)
    .slice()
    .sort((a, b) => Number(a.daysLeft) - Number(b.daysLeft))
    .slice(0, 12);
});

const dueSoonCount = computed(() => dueSoonRows.value.length);
const dueSoonAmount = computed(() => dueSoonRows.value.reduce((s, r) => s + Number(r.amount || 0), 0));

const signals = computed(() => marketSignals?.value ?? marketSignals ?? {});
const highlights = computed(() => marketHighlights?.value ?? marketHighlights ?? []);
const comparisons = computed(() => marketComparisons?.value ?? marketComparisons ?? []);
const alerts = computed(() => {
  const list = triggeredAlerts?.value ?? triggeredAlerts ?? [];
  return Array.isArray(list) ? list : [];
});
const breachList = computed(() => {
  const list = breaches?.value ?? breaches ?? [];
  return Array.isArray(list) ? list : [];
});

const headline = computed(() => {
  const parts = [];
  const sig = signals.value || {};
  if (sig.portfolio_vs_market) parts.push(sig.portfolio_vs_market);
  if (breachCount.value) parts.push(`纪律破线 ${breachCount.value} 条`);
  if (dueSoonCount.value) parts.push(`存款近 30 天到期 ${dueSoonCount.value} 笔`);
  if (alerts.value.length) parts.push(`预警触发 ${alerts.value.length} 条`);
  return parts.length ? parts.join(' · ') : '先刷新：看贡献、预警、纪律、存款到期，再决定要不要动手。';
});

async function refreshDecision() {
  await Promise.all([
    typeof refreshMarket === 'function' ? refreshMarket() : Promise.resolve(),
    typeof refreshDiscipline === 'function' ? refreshDiscipline() : Promise.resolve(),
  ]);
}

function goTab(name) {
  if (name === 'deposits') {
    tabGroup.value = 'daily';
  } else {
    tabGroup.value = 'analysis';
  }
  activeTab.value = name;
}

onMounted(() => {
  refreshDecision();
});
</script>

<style scoped>
.decision-page { padding: 4px 2px 16px; }
.decision-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.decision-title { margin: 0 0 4px; font-size: 18px; font-weight: 700; color: #1f2937; }
.decision-subtitle { font-size: 13px; color: #6b7280; line-height: 1.45; max-width: 640px; }
.decision-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.decision-metric { min-height: 108px; }
.decision-metric-label { font-size: 12px; color: #909399; }
.decision-metric-value { font-size: 22px; font-weight: 700; margin-top: 6px; color: #303133; word-break: break-all; }
.decision-metric-value.is-warn { color: #d97706; }
.decision-metric-value.is-ok { color: #16a34a; }
.decision-metric-sub { font-size: 12px; color: #909399; margin-top: 6px; line-height: 1.35; }
.decision-card-title { font-weight: 600; color: #303133; }
.decision-list { margin: 0; padding-left: 18px; color: #303133; line-height: 1.55; }
.decision-empty { color: #909399; font-size: 13px; }
.decision-muted { margin-top: 8px; font-size: 12px; color: #606266; line-height: 1.45; }
</style>
