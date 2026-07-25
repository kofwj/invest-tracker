<template>
  <div class="overview-page">
    <section class="overview-hero">
      <div class="overview-metrics">
        <div class="ov-metric main">
          <div class="ov-metric-label"><Coins :size="13" :stroke-width="2" />总资产</div>
          <div class="ov-metric-value" :title="formatMoney(dashboard.total_assets)">{{ formatMoney(dashboard.total_assets) }}</div>
          <div class="ov-metric-sub">市值 + 现金 + 存款 + 在途 · {{ holdingsCount }} 只持仓</div>
        </div>
        <div class="ov-metric">
          <div class="ov-metric-label"><Activity :size="13" :stroke-width="2" />当日参考</div>
          <div class="ov-metric-value" :class="todayContrib >= 0 ? 'up' : 'down'" :title="formatMoney(todayContrib, 2, true)">{{ formatMoney(todayContrib, 2, true) }}</div>
          <div class="ov-metric-sub">盘中粗估，不入账</div>
        </div>
        <div class="ov-metric">
          <div class="ov-metric-label"><TrendingUp :size="13" :stroke-width="2" />持仓浮盈</div>
          <div class="ov-metric-value" :class="Number(dashboard.total_profit || 0) >= 0 ? 'up' : 'down'" :title="formatMoney(dashboard.total_profit, 2, true)">{{ formatMoney(dashboard.total_profit, 2, true) }}</div>
          <div class="ov-metric-sub">账本当前仓口径</div>
        </div>
        <div class="ov-metric">
          <div class="ov-metric-label"><Landmark :size="13" :stroke-width="2" />现金 + 存款</div>
          <div class="ov-metric-value" :title="formatMoney(cashAndBank)">{{ formatMoney(cashAndBank) }}</div>
          <div class="ov-metric-sub">证券现金 {{ formatMoney(dashboard.securities_cash) }}</div>
        </div>
      </div>

      <aside class="mix-card">
        <div class="mix-head">
          <div class="mix-title"><PieChart :size="14" :stroke-width="2" />资产构成</div>
          <div class="mix-chip">静态示意</div>
        </div>
        <div class="mix-total">{{ formatMoney(dashboard.total_assets) }}</div>
        <div class="mix-bars" aria-label="资产构成">
          <div class="mix-bar equity" :style="{ width: barWidth(summary.equityRatio) }" />
          <div class="mix-bar fixed" :style="{ width: barWidth(fixedPct) }" />
          <div class="mix-bar deposit" :style="{ width: barWidth(depositPct) }" />
        </div>
        <div class="mix-legend">
          <div class="mix-item">
            <span class="dot equity" />
            <div>
              <div class="l">权益</div>
              <div class="v">{{ equityPctText }}</div>
            </div>
          </div>
          <div class="mix-item">
            <span class="dot fixed" />
            <div>
              <div class="l">固收</div>
              <div class="v">{{ fixedPctText }}</div>
            </div>
          </div>
          <div class="mix-item">
            <span class="dot deposit" />
            <div>
              <div class="l">存款现金</div>
              <div class="v">{{ depositPctText }}</div>
            </div>
          </div>
        </div>
        <div class="mix-meta">
          <div class="mix-meta-box">
            <div class="l">防御资产</div>
            <div class="v">{{ defensivePctText }}</div>
          </div>
          <div class="mix-meta-box">
            <div class="l">目标年化</div>
            <div class="v">{{ expectedReturnText }}</div>
          </div>
        </div>
      </aside>
    </section>

    <section class="overview-status">
      <div class="ov-status">
        <div class="ov-status-ico" :class="dashboard.price_stale ? 'warn' : 'ok'">
          <CheckCircle2 v-if="!dashboard.price_stale" :size="15" :stroke-width="2" />
          <Radar v-else :size="15" :stroke-width="2" />
        </div>
        <div>
          <h4>最新价同步</h4>
          <p :class="dashboard.price_stale ? 'is-warn' : ''">{{ latestPriceStatusText }}</p>
        </div>
      </div>
      <div class="ov-status">
        <div class="ov-status-ico" :class="todaySnapshotDone ? 'ok' : 'warn'">
          <Camera :size="15" :stroke-width="2" />
        </div>
        <div>
          <h4>今日快照</h4>
          <p :class="todaySnapshotDone ? 'is-ok' : 'is-warn'">
            {{ todaySnapshotDone ? '已记录' : '未记录' }} · {{ dashboard.latest_snapshot_date || '暂无' }}
          </p>
        </div>
      </div>
      <div class="ov-status">
        <div class="ov-status-ico ok">
          <HardDrive :size="15" :stroke-width="2" />
        </div>
        <div>
          <h4>最近备份</h4>
          <p>{{ latestBackupText }} · {{ maintenanceStatus.backup_count || 0 }} 份</p>
        </div>
      </div>
    </section>

    <div v-if="Number(dashboard.pending_purchase || 0) > 0" class="overview-pending">
      <Info :size="14" :stroke-width="2" />
      <span>
        当前有 {{ dashboard.pending_count || pendingTransactions.length || 0 }} 笔申购在途，金额
        {{ formatMoney(dashboard.pending_purchase) }}。
      </span>
      <button type="button" class="ov-link" @click="goPendingTransactions">查看在途</button>
    </div>

    <section class="overview-main">
      <div class="ov-card">
        <div class="ov-card-head">
          <h3><Layers :size="15" :stroke-width="2" />持仓速览</h3>
          <button type="button" class="ov-btn compact" @click="goTab('holdings')">
            <ArrowUpRight :size="14" :stroke-width="2" />
            全部明细
          </button>
        </div>
        <el-table
          :data="holdingsPreview"
          stripe
          size="small"
          class="holdings-table overview-holdings-table"
          style="width: 100%"
          empty-text="暂无持仓"
          @row-click="onRowClick"
        >
          <el-table-column label="标的" min-width="168" fixed="left" align="left" header-align="left">
            <template #default="scope">
              <div class="asset-cell">
                <div class="asset-cell-name">{{ scope.row.name }}</div>
                <div class="asset-cell-code">{{ scope.row.code }} · {{ scope.row.category || '未分类' }}</div>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="最新价" min-width="96" align="right" header-align="right">
            <template #default="scope">
              <span class="num-cell">{{ formatMoney(scope.row.last_price, 4) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="市值" min-width="112" align="right" header-align="right">
            <template #default="scope">
              <span class="num-cell">{{ formatMoney(Number(scope.row.quantity || 0) * Number(scope.row.last_price || 0)) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="持仓浮盈" min-width="112" align="right" header-align="right">
            <template #default="scope">
              <span class="num-cell" :style="{ color: holdingFloatProfit(scope.row) >= 0 ? 'var(--ov-up)' : 'var(--ov-down)' }">
                {{ formatMoney(holdingFloatProfit(scope.row), 2, true) }}
              </span>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div class="overview-side">
        <div class="ov-card padded">
          <h3 class="side-title"><Zap :size="14" :stroke-width="2" />今天可做</h3>
          <button type="button" class="ov-action" @click="goTab('decision')">
            <span class="ov-action-ico"><Compass :size="16" :stroke-width="2" /></span>
            <span>
              <strong>今天该看</strong>
              <small>市场信号 + 纪律提醒</small>
            </span>
          </button>
          <button type="button" class="ov-action" @click="goTab('transactions')">
            <span class="ov-action-ico"><PenLine :size="16" :stroke-width="2" /></span>
            <span>
              <strong>交易 / 分红草稿</strong>
              <small>真仓纪律，草稿确认入账</small>
            </span>
          </button>
        </div>

        <div class="ov-card padded">
          <h3 class="side-title"><Gauge :size="14" :stroke-width="2" />组合脉搏</h3>
          <div class="ov-pulse"><span>权益仓位</span><b>{{ equityPctText }}</b></div>
          <div class="ov-pulse"><span>防御资产</span><b>{{ defensivePctText }}</b></div>
          <div class="ov-pulse"><span>持仓市值</span><b>{{ formatMoney(dashboard.total_market_value) }}</b></div>
          <div class="ov-pulse"><span>在途申购</span><b>{{ pendingCountText }}</b></div>
          <div class="ov-pulse"><span>目标年化</span><b>{{ expectedReturnText }}</b></div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue';
import {
  Activity,
  ArrowUpRight,
  Banknote,
  Camera,
  CheckCircle2,
  Coins,
  Compass,
  Gauge,
  HardDrive,
  Info,
  Landmark,
  Layers,
  PenLine,
  PieChart,
  Radar,
  TrendingUp,
  Zap,
} from 'lucide-vue-next';
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
  refreshMarket,
  showTransactions,
  formatMoney,
  holdingFloatProfit,
  goTab,
  allocationSummary,
  portfolioExpectedReturn,
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

const summary = computed(() => allocationSummary?.value ?? allocationSummary ?? {});

const equityPctText = computed(() => `${Number(summary.value.equityRatio || 0).toFixed(1)}%`);
const defensivePctText = computed(() => `${Number(summary.value.defensiveRatio || 0).toFixed(1)}%`);

const fixedPct = computed(() => {
  const total = Number(summary.value.total || 0);
  const amount = Number(summary.value.fixedAmount || 0);
  return total > 0 ? (amount / total) * 100 : 0;
});
const depositPct = computed(() => {
  const total = Number(summary.value.total || 0);
  const amount = Number(summary.value.depositAmount || 0);
  return total > 0 ? (amount / total) * 100 : 0;
});
const fixedPctText = computed(() => `${Number(fixedPct.value || 0).toFixed(1)}%`);
const depositPctText = computed(() => `${Number(depositPct.value || 0).toFixed(1)}%`);

const expectedReturnText = computed(() => {
  const raw = portfolioExpectedReturn?.value ?? portfolioExpectedReturn ?? 0;
  return `${Number(raw || 0).toFixed(2)}%`;
});

const pendingCountText = computed(() => {
  const d = dashboard?.value ?? dashboard ?? {};
  const n = Number(d.pending_count || pendingTransactions?.value?.length || pendingTransactions?.length || 0);
  return `${n} 笔`;
});

function barWidth(pctVal) {
  const n = Math.max(0, Number(pctVal || 0));
  return `${Math.min(100, n)}%`;
}

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
.overview-page {
  --ov-bg: var(--app-overview-bg, #08090a);
  --ov-panel: var(--app-overview-panel, rgba(15, 16, 17, 0.92));
  --ov-border: var(--app-overview-border, rgba(255, 255, 255, 0.08));
  --ov-border-strong: var(--app-overview-border-strong, rgba(255, 255, 255, 0.14));
  --ov-text: var(--app-overview-text, #f7f8f8);
  --ov-text-2: var(--app-overview-text-2, #c7ccd4);
  --ov-text-3: var(--app-overview-text-3, #8a8f98);
  --ov-text-4: var(--app-overview-text-4, #5f646c);
  --ov-accent: var(--app-primary, #7170ff);
  --ov-accent-soft: var(--app-primary-soft, rgba(113, 112, 255, 0.14));
  --ov-up: #f56c6c;
  --ov-down: #67c23a;
  --ov-warn: #f59e0b;
  --ov-ok: #10b981;
  margin: -4px -6px 0;
  padding: 10px 8px 18px;
  border-radius: 16px;
  color: var(--ov-text);
  background: var(--app-overview-surface,
    linear-gradient(180deg, #0b0c0e 0%, #08090a 100%));
  font-feature-settings: "cv01", "ss03";
}

.ov-btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 34px;
  padding: 0 12px;
  border-radius: 8px;
  border: 1px solid var(--ov-border);
  background: rgba(255, 255, 255, 0.03);
  color: var(--ov-text-2);
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease, transform 0.15s ease;
}
.ov-btn:hover {
  background: rgba(255, 255, 255, 0.06);
  border-color: var(--ov-border-strong);
}
.ov-btn:active { transform: translateY(1px); }
.ov-btn:disabled { opacity: 0.6; cursor: default; }
.ov-btn.primary {
  background: var(--ov-accent);
  border-color: transparent;
  color: #fff;
  box-shadow: 0 8px 24px color-mix(in srgb, var(--ov-accent) 28%, transparent);
}
.ov-btn.compact { height: 30px; padding: 0 10px; }
.ov-btn .spin { animation: ov-spin 1s linear infinite; }

.overview-hero {
  display: grid;
  grid-template-columns: 1.35fr 0.95fr;
  gap: 14px;
}
.overview-metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}
.ov-metric {
  padding: 16px;
  border-radius: 12px;
  background: var(--app-overview-metric-bg, linear-gradient(180deg, rgba(255,255,255,0.035), rgba(255,255,255,0.015)));
  border: 1px solid var(--ov-border);
  min-height: 108px;
}
.ov-metric.main {
  grid-column: 1 / -1;
  background:
    linear-gradient(135deg, rgba(113,112,255,0.12), transparent 40%),
    linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.015));
}
.ov-metric-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--ov-text-3);
  font-weight: 600;
}
.ov-metric-value {
  margin-top: 10px;
  font-family: "SF Mono", "Menlo", "Consolas", "Roboto Mono", ui-monospace, monospace;
  font-size: clamp(18px, 2.1vw, 26px);
  font-weight: 500;
  letter-spacing: -0.03em;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.2;
}
.ov-metric.main .ov-metric-value {
  font-size: clamp(28px, 3.6vw, 40px);
  white-space: nowrap;
}
.ov-metric-sub { margin-top: 6px; font-size: 12px; color: var(--ov-text-4); }
.up { color: var(--ov-up); }
.down { color: var(--ov-down); }

.mix-card {
  border: 1px solid var(--ov-border);
  background: var(--ov-panel);
  border-radius: 16px;
  padding: 16px 18px;
  min-height: 280px;
  display: flex;
  flex-direction: column;
}
.mix-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.mix-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--ov-text-2);
}
.mix-chip {
  height: 26px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid var(--ov-border);
  background: rgba(127, 127, 127, 0.08);
  color: var(--ov-text-3);
  font-size: 11px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
}
.mix-total {
  margin-top: 14px;
  font-family: "SF Mono", "Menlo", "Consolas", ui-monospace, monospace;
  font-size: clamp(24px, 2.8vw, 32px);
  letter-spacing: -0.04em;
  font-variant-numeric: tabular-nums;
}
.mix-bars {
  margin-top: 16px;
  display: flex;
  height: 12px;
  border-radius: 999px;
  overflow: hidden;
  background: rgba(127, 127, 127, 0.12);
}
.mix-bar { height: 100%; min-width: 0; }
.mix-bar.equity { background: #7170ff; }
.mix-bar.fixed { background: #57b0f2; }
.mix-bar.deposit { background: #10b981; }
.mix-legend {
  margin-top: 16px;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}
.mix-item {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}
.mix-item .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-top: 5px;
  flex: 0 0 auto;
}
.mix-item .dot.equity { background: #7170ff; }
.mix-item .dot.fixed { background: #57b0f2; }
.mix-item .dot.deposit { background: #10b981; }
.mix-item .l { font-size: 11px; color: var(--ov-text-4); }
.mix-item .v {
  margin-top: 2px;
  font-family: "SF Mono", "Menlo", "Consolas", ui-monospace, monospace;
  font-size: 14px;
  letter-spacing: -0.02em;
}
.mix-meta {
  margin-top: auto;
  padding-top: 16px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.mix-meta-box {
  padding: 12px;
  border-radius: 10px;
  background: rgba(127, 127, 127, 0.08);
  border: 1px solid var(--ov-border);
}
.mix-meta-box .l { font-size: 11px; color: var(--ov-text-4); }
.mix-meta-box .v {
  margin-top: 4px;
  font-family: "SF Mono", "Menlo", "Consolas", ui-monospace, monospace;
  font-size: 16px;
  letter-spacing: -0.02em;
}

.overview-status {
  margin-top: 14px;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}
.ov-status {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 14px 16px;
  border-radius: 12px;
  border: 1px solid var(--ov-border);
  background: rgba(127, 127, 127, 0.05);
}
.ov-status-ico {
  width: 32px;
  height: 32px;
  border-radius: 9px;
  display: grid;
  place-items: center;
  background: rgba(127, 127, 127, 0.08);
  border: 1px solid var(--ov-border);
  color: var(--ov-text-2);
  flex: 0 0 auto;
}
.ov-status-ico.ok {
  background: rgba(16, 185, 129, 0.12);
  border-color: rgba(16, 185, 129, 0.25);
  color: var(--ov-ok);
}
.ov-status-ico.warn {
  background: rgba(245, 158, 11, 0.12);
  border-color: rgba(245, 158, 11, 0.25);
  color: var(--ov-warn);
}
.ov-status h4 { margin: 0; font-size: 13px; font-weight: 600; }
.ov-status p { margin: 3px 0 0; font-size: 12px; color: var(--ov-text-4); }
.ov-status p.is-ok { color: var(--ov-ok); }
.ov-status p.is-warn { color: var(--ov-warn); }

.overview-pending {
  margin-top: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgba(245, 158, 11, 0.28);
  background: rgba(245, 158, 11, 0.08);
  color: #c9872c;
  font-size: 13px;
}
.ov-link {
  border: 0;
  background: transparent;
  color: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  text-decoration: underline;
}

.overview-main {
  margin-top: 14px;
  display: grid;
  grid-template-columns: 1.6fr 0.9fr;
  gap: 14px;
}
.overview-side {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.ov-card {
  border: 1px solid var(--ov-border);
  background: var(--ov-panel);
  border-radius: 16px;
  overflow: hidden;
}
.ov-card.padded { padding: 16px 18px; }
.ov-card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 16px 10px;
  border-bottom: 1px solid var(--ov-border);
}
.ov-card-head h3,
.side-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--ov-text-2);
}
.side-title { margin-bottom: 12px; }

.overview-holdings-table {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: rgba(127, 127, 127, 0.04);
  --el-table-row-hover-bg-color: rgba(127, 127, 127, 0.08);
  --el-table-border-color: var(--ov-border);
  --el-table-text-color: var(--ov-text-2);
  --el-table-header-text-color: var(--ov-text-4);
  background: transparent !important;
  color: var(--ov-text-2);
}
.overview-holdings-table :deep(.el-table__inner-wrapper::before),
.overview-holdings-table :deep(.el-table__border-left-patch) {
  background: transparent;
}
.overview-holdings-table :deep(th.el-table__cell),
.overview-holdings-table :deep(td.el-table__cell) {
  background: transparent !important;
}
.overview-holdings-table :deep(.el-table__cell) {
  padding-top: 8px;
  padding-bottom: 8px;
}
.overview-holdings-table :deep(.asset-cell-name) { color: var(--ov-text); }
.overview-holdings-table :deep(.asset-cell-code) { color: var(--ov-text-4); }
.overview-holdings-table :deep(.num-cell) { color: var(--ov-text-2); }
.overview-holdings-table :deep(.el-table__empty-text) { color: var(--ov-text-4); }

.ov-action {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px;
  margin-bottom: 8px;
  border-radius: 12px;
  border: 1px solid var(--ov-border);
  background: rgba(127, 127, 127, 0.04);
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease, transform 0.15s ease;
}
.ov-action:hover {
  background: rgba(127, 127, 127, 0.08);
  border-color: var(--ov-border-strong);
  transform: translateY(-1px);
}
.ov-action-ico {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  display: grid;
  place-items: center;
  background: var(--ov-accent-soft);
  color: var(--ov-accent);
  flex: 0 0 auto;
}
.ov-action strong {
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: var(--ov-text);
}
.ov-action small {
  display: block;
  margin-top: 2px;
  font-size: 11.5px;
  color: var(--ov-text-4);
}
.ov-pulse {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: baseline;
  padding: 10px 0;
  border-bottom: 1px solid var(--ov-border);
  font-size: 12.5px;
  color: var(--ov-text-3);
}
.ov-pulse:last-child { border-bottom: 0; padding-bottom: 0; }
.ov-pulse b {
  font-family: "SF Mono", "Menlo", "Consolas", ui-monospace, monospace;
  font-size: 12.5px;
  font-weight: 500;
  color: var(--ov-text-2);
}

@keyframes ov-spin {
  to { transform: rotate(360deg); }
}

@media (max-width: 1100px) {
  .overview-hero,
  .overview-main,
  .overview-status { grid-template-columns: 1fr; }
  .overview-metrics { grid-template-columns: 1fr 1fr; }
  .ov-metric.main { grid-column: 1 / -1; }
}
@media (max-width: 640px) {
  .overview-metrics,
  .mix-legend { grid-template-columns: 1fr; }
  .overview-page { margin: 0; padding: 4px 0 12px; }
}
@media (prefers-reduced-motion: reduce) {
  .ov-btn .spin { animation: none; }
  .ov-action { transition: none; }
}

/* 白天模式：总览也跟浅色，不再硬锁黑底 */
:global(html:not(.dark)) .overview-page {
  --ov-bg: #f7f8fa;
  --ov-panel: #ffffff;
  --ov-border: #e8edf3;
  --ov-border-strong: #d5dbe5;
  --ov-text: #1f2937;
  --ov-text-2: #374151;
  --ov-text-3: #6b7280;
  --ov-text-4: #9ca3af;
  --ov-accent: #4f46e5;
  --ov-accent-soft: #eef2ff;
  background:
    radial-gradient(900px 420px at 12% -10%, rgba(79, 70, 229, 0.08), transparent 55%),
    linear-gradient(180deg, #fbfcfe 0%, #f3f5f9 100%);
}
:global(html:not(.dark)) .ov-btn {
  background: #fff;
  color: #374151;
}
:global(html:not(.dark)) .ov-btn.primary {
  background: #4f46e5;
  color: #fff;
}
:global(html:not(.dark)) .ov-metric {
  background: #fff;
}
:global(html:not(.dark)) .ov-metric.main {
  background: linear-gradient(135deg, #eef2ff 0%, #ffffff 55%, #f0fdf4 100%);
}
:global(html:not(.dark)) .overview-pending {
  color: #b45309;
}
</style>
