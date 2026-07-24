<template>
  <div class="overview-page">
    <div class="overview-header">
      <div>
        <h3 class="overview-title">今日总览</h3>
        <div class="overview-subtitle">
          首页看家底与状态；点持仓可进明细。当日收益为盘中粗估，不入账。
        </div>
      </div>
      <div class="overview-actions">
        <el-button size="small" :loading="marketLoading" @click="refreshOverview">刷新</el-button>
        <el-button size="small" type="primary" plain @click="goTab('holdings')">持仓明细</el-button>
        <el-button size="small" plain @click="goTab('decision')">今天该看</el-button>
        <el-button size="small" plain @click="goTab('transactions')">记交易</el-button>
      </div>
    </div>

    <div class="top-stats overview-stats">
      <el-card shadow="hover" class="stat-card stat-main">
        <div class="stat-card-inner">
          <div class="stat-label">总资产</div>
          <div class="stat-value">{{ formatMoney(dashboard.total_assets) }}</div>
          <div class="stat-sub">市值 + 现金 + 存款 + 在途</div>
        </div>
      </el-card>
      <el-card shadow="hover" class="stat-card">
        <div class="stat-card-inner">
          <div class="stat-label">持仓数量</div>
          <div class="stat-value">{{ holdingsCount }}</div>
          <div class="stat-sub">已录入股票 / 基金 / ETF</div>
        </div>
      </el-card>
      <el-card shadow="hover" class="stat-card">
        <div class="stat-card-inner">
          <div class="stat-label">持仓市值</div>
          <div class="stat-value">{{ formatMoney(dashboard.total_market_value) }}</div>
          <div class="stat-sub">已确认持仓</div>
        </div>
      </el-card>
      <el-card shadow="hover" class="stat-card stat-profit">
        <div class="stat-card-inner">
          <div class="stat-label">持仓浮盈</div>
          <div class="stat-value" :style="{ color: (dashboard.total_profit || 0) >= 0 ? '#F56C6C' : '#67C23A' }">
            {{ formatMoney(dashboard.total_profit) }}
          </div>
          <div class="stat-sub">账本当前仓口径</div>
        </div>
      </el-card>
      <el-card shadow="hover" class="stat-card">
        <div class="stat-card-inner">
          <div class="stat-label">当日收益参考</div>
          <div class="stat-value" :style="{ color: todayContrib >= 0 ? '#F56C6C' : '#67C23A' }">
            {{ formatMoney(todayContrib, 2, true) }}
          </div>
          <div class="stat-sub">盘中粗估，不参与累计</div>
        </div>
      </el-card>
      <el-card shadow="hover" class="stat-card">
        <div class="stat-card-inner">
          <div class="stat-label">现金 + 存款</div>
          <div class="stat-value">{{ formatMoney(cashAndBank) }}</div>
          <div class="stat-sub">证券现金 {{ formatMoney(dashboard.securities_cash) }}</div>
        </div>
      </el-card>
    </div>

    <div class="home-status-strip" style="margin-top: 12px;">
      <el-card shadow="never" class="home-status-card">
        <div class="home-status-label">最新价同步</div>
        <div class="home-status-main" :class="dashboard.price_stale ? 'is-warn' : ''">{{ latestPriceStatusText }}</div>
        <div class="home-status-sub">取持仓最新更新时间</div>
      </el-card>
      <el-card shadow="never" class="home-status-card">
        <div class="home-status-label">今日快照</div>
        <div class="home-status-main" :class="todaySnapshotDone ? 'is-ok' : 'is-warn'">{{ todaySnapshotDone ? '已记录' : '未记录' }}</div>
        <div class="home-status-sub">最新快照：{{ dashboard.latest_snapshot_date || '暂无' }}</div>
      </el-card>
      <el-card shadow="never" class="home-status-card">
        <div class="home-status-label">最近备份</div>
        <div class="home-status-main">{{ latestBackupText }}</div>
        <div class="home-status-sub">备份数：{{ maintenanceStatus.backup_count || 0 }}</div>
      </el-card>
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

    <el-card shadow="never" class="overview-holdings-card" style="margin-top: 16px;">
      <template #header>
        <div class="overview-card-head">
          <span class="allocation-section-title">持仓列表</span>
          <el-button type="primary" link @click="goTab('holdings')">全部明细</el-button>
        </div>
      </template>
      <el-table
        :data="holdingsPreview"
        stripe
        class="holdings-table"
        style="width: 100%"
        empty-text="暂无持仓"
        @row-click="onRowClick"
      >
        <el-table-column prop="name" label="名称" min-width="120" fixed="left" />
        <el-table-column prop="code" label="代码" width="100" align="center" />
        <el-table-column prop="category" label="分类" width="90" align="center" />
        <el-table-column label="市值" min-width="110" align="right">
          <template #default="scope">
            <span class="nowrap-cell">{{ formatMoney(Number(scope.row.quantity || 0) * Number(scope.row.last_price || 0)) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="持仓浮盈" min-width="110" align="right">
          <template #default="scope">
            <span class="nowrap-cell" :style="{ color: holdingFloatProfit(scope.row) >= 0 ? '#F56C6C' : '#67C23A' }">
              {{ formatMoney(holdingFloatProfit(scope.row), 2, true) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="最新价" min-width="90" align="right">
          <template #default="scope">
            <span class="nowrap-cell">{{ formatMoney(scope.row.last_price, 4) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue';
import { useAppCtx } from '../composables/useAppCtx.js';

const {
  dashboard,
  holdings,
  maintenanceStatus,
  todaySnapshotDone,
  latestPriceStatusText,
  latestBackupText,
  pendingTransactions,
  goPendingTransactions,
  marketSignals,
  marketLoading,
  refreshMarket,
  showTransactions,
  formatMoney,
  holdingFloatProfit,
  goTab,
} = useAppCtx();

const holdingsCount = computed(() => {
  const list = holdings?.value ?? holdings ?? [];
  return Array.isArray(list) ? list.length : 0;
});

const holdingsPreview = computed(() => {
  const list = holdings?.value ?? holdings ?? [];
  if (!Array.isArray(list)) return [];
  return [...list]
    .map((r) => ({
      ...r,
      _mv: Number(r.quantity || 0) * Number(r.last_price || 0),
    }))
    .sort((a, b) => b._mv - a._mv)
    .slice(0, 12);
});

const todayContrib = computed(() => {
  const sig = marketSignals?.value ?? marketSignals ?? {};
  return Number(sig.today_contrib_estimate || 0);
});

const cashAndBank = computed(() => {
  const d = dashboard?.value ?? dashboard ?? {};
  return Number(d.securities_cash || 0) + Number(d.bank_balance || 0);
});

async function refreshOverview() {
  if (typeof refreshMarket === 'function') await refreshMarket();
}

function onRowClick(row) {
  if (typeof showTransactions === 'function') showTransactions(row);
}

onMounted(() => {
  refreshOverview();
});
</script>

<style scoped>
.overview-page { padding: 2px 0 12px; }
.overview-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}
.overview-title { margin: 0; font-size: 18px; font-weight: 700; color: #303133; }
.overview-subtitle { margin-top: 6px; font-size: 13px; color: #909399; line-height: 1.5; max-width: 640px; }
.overview-actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.overview-stats { grid-template-columns: 1.25fr repeat(5, 1fr); }
.overview-card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
@media (max-width: 1280px) {
  .overview-stats { grid-template-columns: repeat(3, 1fr); }
}
@media (max-width: 900px) {
  .overview-stats { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 640px) {
  .overview-stats { grid-template-columns: 1fr; }
}
</style>
