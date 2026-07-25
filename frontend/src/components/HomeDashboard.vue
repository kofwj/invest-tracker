<template>
  <!-- 仅在「持仓明细」页展示，不全站常驻 -->
  <div class="holdings-overview">
    <div class="ledger-metrics cols-6">
      <MetricCard
        label="总资产"
        :value="formatMoney(dashboard.total_assets)"
        sub="市值 + 现金 + 存款 + 申购在途"
        main
      />
      <MetricCard
        label="投资账户市值"
        :value="formatMoney(dashboard.total_market_value)"
        sub="已确认持仓"
      />
      <MetricCard
        label="证券现金"
        :value="formatMoney(dashboard.securities_cash)"
        sub="交易自动联动"
      />
      <MetricCard
        label="银行存款"
        :value="formatMoney(dashboard.bank_balance)"
        sub="表内存款合计"
      />
      <MetricCard
        label="投资账户持仓浮盈"
        :value="formatMoney(dashboard.total_profit)"
        sub="普通成本当前仓；不含已卖出已实现"
        :tone="Number(dashboard.total_profit || 0) >= 0 ? 'up' : 'down'"
      />
      <MetricCard
        label="投资账户全周期盈亏"
        :value="formatMoney(dashboard.lifetime_profit)"
        sub="摊薄成本口径；接近券商累计盈亏"
        :tone="Number(dashboard.lifetime_profit || 0) >= 0 ? 'up' : 'down'"
      />
    </div>

    <div class="ledger-status-strip">
      <div class="ledger-status-card">
        <div class="ledger-status-label">最新价同步</div>
        <div class="ledger-status-main" :class="dashboard.price_stale ? 'is-warn' : ''">{{ latestPriceStatusText }}</div>
        <div class="ledger-status-sub">取持仓最新更新时间</div>
      </div>
      <div class="ledger-status-card">
        <div class="ledger-status-label">今日快照</div>
        <div class="ledger-status-main" :class="todaySnapshotDone ? 'is-ok' : 'is-warn'">{{ todaySnapshotDone ? '已记录' : '未记录' }}</div>
        <div class="ledger-status-sub">最新快照：{{ dashboard.latest_snapshot_date || '暂无' }}</div>
      </div>
      <div class="ledger-status-card">
        <div class="ledger-status-label">最近备份</div>
        <div class="ledger-status-main">{{ latestBackupText }}</div>
        <div class="ledger-status-sub">备份数：{{ maintenanceStatus.backup_count || 0 }}</div>
      </div>
    </div>

    <el-alert
      v-if="Number(dashboard.pending_purchase || 0) > 0"
      type="warning"
      show-icon
      :closable="false"
      class="mt-20"
    >
      <template #title>
        <span>
          当前有 {{ dashboard.pending_count || pendingTransactions.length || 0 }} 笔申购在途，金额 {{ formatMoney(dashboard.pending_purchase) }}。确认份额/净值后，请到交易管理把对应记录从“申购待确认”改为“买入”。
        </span>
        <el-button type="warning" link style="margin-left: 12px;" @click="goPendingTransactions">查看在途交易</el-button>
      </template>
    </el-alert>
  </div>
</template>

<script setup>
import MetricCard from './MetricCard.vue';
import { useAppCtx } from '../composables/useAppCtx.js';
const {
  dashboard,
  maintenanceStatus,
  todaySnapshotDone,
  latestPriceStatusText,
  latestBackupText,
  pendingTransactions,
  goPendingTransactions,
  formatMoney,
} = useAppCtx();
</script>
