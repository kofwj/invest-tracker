<template>
  <!-- 仅在「持仓明细」页展示，不全站常驻 -->
  <div class="holdings-overview">
    <!-- 四个数：一行、发丝线分格（新版排版，与总览/收益页一致） -->
    <div class="app-stat-row cols-4">
      <div class="app-stat-cell">
        <div class="k">总资产</div>
        <div class="v" :title="formatMoney(dash.total_assets)">{{ formatMoney(dash.total_assets) }}</div>
      </div>
      <div class="app-stat-cell">
        <div class="k">持仓浮盈</div>
        <div class="v" :class="signTone(dash.total_profit)">{{ formatMoney(dash.total_profit) }}</div>
      </div>
      <div class="app-stat-cell">
        <div class="k">全周期盈亏</div>
        <div class="v" :class="signTone(dash.lifetime_profit)">{{ formatMoney(dash.lifetime_profit) }}</div>
      </div>
      <div class="app-stat-cell">
        <div class="k">现金 + 存款</div>
        <div class="v">{{ formatMoney(cashAndBank) }}</div>
      </div>
    </div>

    <!-- 这一页只留价格时效：今日快照 / 最近备份 都在总览的「同步与备份」里 -->
    <div class="price-line" :class="dash.price_stale ? 'is-warn' : ''">
      最新价 {{ latestPriceStatusText }}
    </div>

    <el-alert
      v-if="Number(dash.pending_purchase || 0) > 0"
      type="warning"
      show-icon
      :closable="false"
      class="mt-20"
    >
      <template #title>
        <span>
          当前有 {{ dash.pending_count || pendingTransactions.length || 0 }} 笔申购在途，金额 {{ formatMoney(dash.pending_purchase) }}。
        </span>
        <el-button type="warning" link style="margin-left: 12px;" @click="goPendingTransactions">查看在途交易</el-button>
      </template>
    </el-alert>
  </div>
</template>

<script setup>
import { computed } from 'vue';
import { useAppCtx } from '../composables/useAppCtx.js';

const {
  dashboard,
  latestPriceStatusText,
  pendingTransactions,
  goPendingTransactions,
  formatMoney,
} = useAppCtx();

/** ref / computed / 裸值都兼容（测试挂载时 ctx 可能给裸值） */
const unwrap = (v) => (v && typeof v === 'object' && 'value' in v ? v.value : v);
const dash = computed(() => unwrap(dashboard) || {});
const cashAndBank = computed(() => Number(dash.value.securities_cash || 0) + Number(dash.value.bank_balance || 0));

/** 涨跌配色：0 不上色，避免「没变化」被染成红或绿 */
const signTone = (v) => {
  const n = Number(v || 0);
  if (!n) return '';
  return n > 0 ? 'up' : 'down';
};
</script>

<style scoped>
/* 这一页专用的一点间距：状态简报与在途提示之间 */
/* 这一页只留价格时效（今日快照 / 最近备份 在总览的「同步与备份」里） */
.price-line { font-size: 12.5px; color: var(--app-soft); margin-bottom: 14px; }
.price-line.is-warn { color: var(--app-warn); }
</style>
