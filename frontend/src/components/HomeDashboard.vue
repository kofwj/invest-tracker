<template>
  <!-- 仅在「持仓明细」页展示，不全站常驻 -->
  <div class="holdings-overview">
    <div class="ledger-metrics cols-4">
      <MetricCard
        label="总资产"
        :value="formatMoney(dashboard.total_assets)"
        main
        :title="formatMoney(dashboard.total_assets)" 
      />
      <MetricCard
        label="持仓浮盈"
        :value="formatMoney(dashboard.total_profit)"
        :tone="Number(dashboard.total_profit || 0) >= 0 ? 'up' : 'down'"
      />
      <MetricCard
        label="全周期盈亏"
        :value="formatMoney(dashboard.lifetime_profit)"
        :tone="Number(dashboard.lifetime_profit || 0) >= 0 ? 'up' : 'down'"
      />
      <MetricCard
        label="现金 + 存款"
        :value="formatMoney(Number(dashboard.securities_cash || 0) + Number(dashboard.bank_balance || 0))"
      />
    </div>

    <div class="ledger-status-strip">
      <div class="ledger-status-card">
        <div class="ledger-status-label">最新价同步</div>
        <div class="ledger-status-main" :class="dashboard.price_stale ? 'is-warn' : ''">{{ latestPriceStatusText }}</div>
      </div>
      <div class="ledger-status-card">
        <div class="ledger-status-label">今日快照</div>
        <div class="ledger-status-main" :class="todaySnapshotDone ? 'is-ok' : 'is-warn'">{{ todaySnapshotDone ? '已记录' : '未记录' }}</div>
      </div>
      <div class="ledger-status-card">
        <div class="ledger-status-label">最近备份</div>
        <div class="ledger-status-main">{{ latestBackupText }}</div>
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
          当前有 {{ dashboard.pending_count || pendingTransactions.length || 0 }} 笔申购在途，金额 {{ formatMoney(dashboard.pending_purchase) }}。
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
