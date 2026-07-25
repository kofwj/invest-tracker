<template>
  <PageShell
    title="今天该看"
    subtitle="只读汇总：今日贡献、纪律、存款到期。详细看市场/纪律/存款页。"
  >
    <template #actions>
      <el-button size="small" :loading="marketLoading || disciplineLoading" @click="refreshDecision">刷新</el-button>
    </template>

    <div class="ledger-metrics cols-4">
      <MetricCard
        label="今日贡献粗估"
        :value="formatMoney(signals.today_contrib_estimate || 0, 2, true)"
        sub="现价涨跌% × 市值，非记账"
        :tone="Number(signals.today_contrib_estimate || 0) >= 0 ? 'up' : 'down'"
        main
      />
      <MetricCard
        label="组合涨跌粗估"
        :value="signals.portfolio_change_pct_estimate == null
          ? '—'
          : ((signals.portfolio_change_pct_estimate >= 0 ? '+' : '') + Number(signals.portfolio_change_pct_estimate).toFixed(2) + '%')"
        :sub="`投资市值 ${formatMoney(signals.total_market_value || 0)}`"
        :tone="Number(signals.portfolio_change_pct_estimate || 0) >= 0 ? 'up' : 'down'"
      />
      <MetricCard
        label="纪律破线"
        :value="String(breachCount)"
        :sub="summaryText || '暂无纪律摘要'"
        :tone="breachCount ? 'warn' : 'ok'"
      />
      <MetricCard
        label="存款 30 天内到期"
        :value="`${dueSoonCount} 笔`"
        :sub="`金额 ${formatMoney(dueSoonAmount)}`"
        :tone="dueSoonCount ? 'warn' : ''"
      />
    </div>

    <div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:12px;">
      <el-button size="small" @click="goTab('market')">去市场（指数 + 预警 + 自选）</el-button>
      <el-button size="small" @click="goTab('discipline')">去纪律详情</el-button>
      <el-button size="small" @click="goTab('deposits')">去存款详情</el-button>
      <el-button size="small" @click="goTab('performance')">去收益分析</el-button>
    </div>

    <el-alert
      :title="headline"
      type="info"
      show-icon
      :closable="false"
      style="margin-bottom: 8px;"
    />
  </PageShell>
</template>

<script setup>
import PageShell from '../components/PageShell.vue';
import MetricCard from '../components/MetricCard.vue';
import { computed, onMounted } from 'vue';
import { useAppCtx } from '../composables/useAppCtx.js';

const {
  goTab,
  marketSignals,
  marketLoading,
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

const headline = computed(() => {
  const parts = [];
  const sig = signals.value || {};
  if (sig.portfolio_vs_market) parts.push(sig.portfolio_vs_market);
  if (breachCount.value) parts.push(`纪律破线 ${breachCount.value} 条`);
  if (dueSoonCount.value) parts.push(`存款近 30 天到期 ${dueSoonCount.value} 笔`);
  return parts.length ? parts.join(' · ') : '先刷新：看贡献、纪律、存款到期，再决定要不要动手。';
});

async function refreshDecision() {
  await Promise.all([
    typeof refreshMarket === 'function' ? refreshMarket() : Promise.resolve(),
    typeof refreshDiscipline === 'function' ? refreshDiscipline() : Promise.resolve(),
  ]);
}

onMounted(() => {
  refreshDecision();
});
</script>

<style scoped>
.decision-card-title { font-weight: 600; color: var(--app-text); }
.decision-list { margin: 0; padding-left: 18px; color: var(--app-text); line-height: 1.55; }
.decision-empty { color: var(--app-muted); font-size: 13px; }
.decision-muted { margin-top: 8px; font-size: 12px; color: var(--app-muted); line-height: 1.45; }
</style>
