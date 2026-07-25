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
          <div class="mix-title"><Activity :size="14" :stroke-width="2" />近一周资产</div>
          <div class="mix-chip">{{ weekChipText }}</div>
        </div>
        <div class="mix-total" :title="formatMoney(dashboard.total_assets)">{{ formatMoney(dashboard.total_assets) }}</div>
        <div class="mix-delta" :class="weekDeltaClass">
          <span class="mix-delta-main">{{ weekDeltaText }}</span>
          <span class="mix-delta-sub">{{ weekDeltaSubText }}</span>
        </div>
        <div id="overviewWeekChart" class="mix-chart" aria-label="近一周总资产曲线"></div>
        <div class="mix-meta">
          <div class="mix-meta-box">
            <div class="l">期初</div>
            <div class="v" :title="formatMoney(weekStartAssets)">{{ formatMoney(weekStartAssets) }}</div>
          </div>
          <div class="mix-meta-box">
            <div class="l">最新</div>
            <div class="v" :title="formatMoney(weekEndAssets)">{{ formatMoney(weekEndAssets) }}</div>
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
        <div v-if="!holdingsPreview.length" class="empty-hint" style="margin-bottom: 8px;">
          <strong>还没有持仓速览</strong>
          <span>录交易或同步价后这里会出现前几只。也可直接去明细页。</span>
          <el-button size="small" type="primary" plain @click="goTab('holdings')">去持仓明细</el-button>
        </div>
        <el-table
          v-else
          :data="holdingsPreview"
          stripe
          size="small"
          class="holdings-table overview-holdings-table table-clickable"
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
              <span class="num-cell" :class="holdingFloatProfit(scope.row) >= 0 ? 'num-up' : 'num-down'">
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
import { computed, nextTick, onMounted, watch } from 'vue';
import {
  Activity,
  ArrowUpRight,
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
  Radar,
  TrendingUp,
  Zap,
} from 'lucide-vue-next';
import { useAppCtx } from '../composables/useAppCtx.js';
import { todayLocalIso } from '../utils/index.js';

const {
  dashboard,
  holdings,
  snapshots,
  maintenanceStatus,
  todaySnapshotDone,
  latestPriceStatusText,
  latestBackupText,
  pendingTransactions,
  goPendingTransactions,
  marketSignals,
  refreshMarket,
  fetchSnapshots,
  showTransactions,
  formatMoney,
  holdingFloatProfit,
  goTab,
  allocationSummary,
  portfolioExpectedReturn,
  resolvedTheme,
} = useAppCtx();

const WEEK_LOOKBACK_DAYS = 7;
const WEEK_MAX_POINTS = 8;

function isoDaysAgo(days) {
  const d = new Date(`${todayLocalIso()}T00:00:00`);
  d.setDate(d.getDate() - Number(days || 0));
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function normalizeSnapshotRows(list) {
  const rows = Array.isArray(list) ? list : [];
  const byDate = new Map();
  rows.forEach((r) => {
    const date = String(r?.date || '');
    if (!date) return;
    const prev = byDate.get(date);
    if (!prev || Number(r.id || 0) >= Number(prev.id || 0)) {
      byDate.set(date, {
        date,
        total_assets: Number(r.total_assets || 0),
        id: Number(r.id || 0),
        live: false,
      });
    }
  });
  return [...byDate.values()].sort((a, b) => String(a.date).localeCompare(String(b.date)));
}

/** 近一周快照；窗口内不足时回退最近若干条，避免总览空白 */
const weekSeriesMeta = computed(() => {
  const all = normalizeSnapshotRows(snapshots?.value ?? snapshots ?? []);
  const start = isoDaysAgo(WEEK_LOOKBACK_DAYS - 1);
  let rows = all.filter((r) => r.date >= start);
  let mode = 'week';

  // 近 7 天不足 2 点：用最近快照（最多 7 条）兜底，本地/断档时仍能看趋势
  if (rows.length < 2) {
    rows = all.slice(-WEEK_LOOKBACK_DAYS);
    mode = rows.length ? 'recent' : 'empty';
  }

  const today = todayLocalIso();
  const liveAssets = Number((dashboard?.value ?? dashboard)?.total_assets || 0);
  if (liveAssets > 0) {
    const existing = rows.find((r) => r.date === today);
    if (!existing) {
      rows = [...rows, { date: today, total_assets: liveAssets, id: 0, live: true }];
      if (mode === 'empty') mode = 'live';
    }
  }

  // 防止点过多挤在一起
  if (rows.length > WEEK_MAX_POINTS) {
    rows = rows.slice(-WEEK_MAX_POINTS);
  }

  return { rows, mode };
});

const weekSeries = computed(() => weekSeriesMeta.value.rows);

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

const expectedReturnText = computed(() => {
  const raw = portfolioExpectedReturn?.value ?? portfolioExpectedReturn ?? 0;
  return `${Number(raw || 0).toFixed(2)}%`;
});

const pendingCountText = computed(() => {
  const d = dashboard?.value ?? dashboard ?? {};
  const n = Number(d.pending_count || pendingTransactions?.value?.length || pendingTransactions?.length || 0);
  return `${n} 笔`;
});

const weekStartAssets = computed(() => {
  const rows = weekSeries.value;
  if (!rows.length) return Number((dashboard?.value ?? dashboard)?.total_assets || 0);
  return Number(rows[0].total_assets || 0);
});

const weekEndAssets = computed(() => {
  const rows = weekSeries.value;
  if (!rows.length) return Number((dashboard?.value ?? dashboard)?.total_assets || 0);
  return Number(rows[rows.length - 1].total_assets || 0);
});

const weekDelta = computed(() => weekEndAssets.value - weekStartAssets.value);

const weekDeltaPct = computed(() => {
  const base = weekStartAssets.value;
  if (!base) return null;
  return (weekDelta.value / base) * 100;
});

const weekDeltaClass = computed(() => {
  if (!weekSeries.value.length) return '';
  return weekDelta.value >= 0 ? 'up' : 'down';
});

const weekDeltaText = computed(() => {
  if (!weekSeries.value.length) return '暂无快照';
  return formatMoney(weekDelta.value, 2, true);
});

const weekDeltaSubText = computed(() => {
  if (!weekSeries.value.length) return '先记一条日快照';
  const pct = weekDeltaPct.value;
  const pctText = pct === null ? '' : ` · ${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`;
  const live = weekSeries.value.some((r) => r.live) ? ' · 含实时' : '';
  const mode = weekSeriesMeta.value.mode;
  const modeText = mode === 'recent' ? ' · 最近快照' : '';
  return `较 ${weekSeries.value[0]?.date || '期初'}${pctText}${live}${modeText}`;
});

const weekChipText = computed(() => {
  const n = weekSeries.value.length;
  if (!n) return '无数据';
  const mode = weekSeriesMeta.value.mode;
  if (mode === 'recent') return `最近 ${n} 点`;
  return `近一周 ${n} 点`;
});

async function paintWeekChart() {
  const { renderOverviewWeekChartView, waitForChartDom } = await import('../charts/index.js');
  const ready = await waitForChartDom(['overviewWeekChart'], { timeoutMs: 1800 });
  if (!ready) return;
  await nextTick();
  await new Promise((r) => requestAnimationFrame(() => r()));
  renderOverviewWeekChartView(weekSeries.value);
}

async function refreshOverview() {
  const jobs = [];
  if (typeof refreshMarket === 'function') jobs.push(refreshMarket());
  // 启动时 appInit 已拉快照；这里补一次，避免总览先进、快照还空
  if (typeof fetchSnapshots === 'function' && !(snapshots?.value?.length || snapshots?.length)) {
    jobs.push(fetchSnapshots());
  }
  if (jobs.length) await Promise.all(jobs);
  await paintWeekChart();
}

function onRowClick(row) {
  if (typeof showTransactions === 'function') showTransactions(row);
}

watch(weekSeries, () => {
  paintWeekChart();
}, { deep: true });

watch(() => resolvedTheme?.value ?? resolvedTheme, () => {
  paintWeekChart();
});

onMounted(() => {
  refreshOverview();
});
</script>

<style scoped>
/* 默认跟全局主题；夜间再加深，不再硬锁黑底 */
.overview-page {
  --ov-bg: var(--app-bg1);
  --ov-panel: var(--app-surface);
  --ov-border: var(--app-border);
  --ov-border-strong: color-mix(in srgb, var(--app-border) 65%, var(--app-muted));
  --ov-text: var(--app-text);
  --ov-text-2: color-mix(in srgb, var(--app-text) 84%, var(--app-muted));
  --ov-text-3: var(--app-muted);
  --ov-text-4: var(--app-soft);
  --ov-accent: var(--app-primary);
  --ov-accent-soft: var(--app-primary-soft);
  --ov-up: var(--app-up);
  --ov-down: var(--app-down);
  --ov-warn: var(--app-warn);
  --ov-ok: var(--app-ok);
  --ov-chip-bg: color-mix(in srgb, var(--app-surface) 88%, var(--app-bg0));
  --ov-metric-bg: var(--app-surface);
  --ov-metric-main-bg:
    linear-gradient(135deg, color-mix(in srgb, var(--app-primary) 12%, transparent), transparent 42%),
    linear-gradient(180deg, var(--app-surface), color-mix(in srgb, var(--app-surface) 92%, var(--app-bg0)));
  --ov-btn-bg: var(--app-header-btn-bg);
  --ov-btn-hover: var(--app-header-btn-hover);
  --ov-btn-text: var(--app-header-btn-text);
  margin: -4px -6px 0;
  padding: 10px 8px 18px;
  border-radius: 16px;
  color: var(--ov-text);
  background:
    radial-gradient(900px 420px at 12% -10%, color-mix(in srgb, var(--app-primary) 10%, transparent), transparent 55%),
    linear-gradient(180deg, var(--app-bg1) 0%, var(--app-bg0) 100%);
  font-feature-settings: "cv01", "ss03";
  transition: background 0.2s ease, color 0.2s ease;
}

:global(html.dark) .overview-page {
  --ov-bg: #08090a;
  --ov-panel: rgba(20, 25, 29, 0.96);
  --ov-border: rgba(255, 255, 255, 0.08);
  --ov-border-strong: rgba(255, 255, 255, 0.14);
  --ov-text: #f7f8f8;
  --ov-text-2: #c7ccd4;
  --ov-text-3: #8a8f98;
  --ov-text-4: #5f646c;
  --ov-chip-bg: rgba(255, 255, 255, 0.04);
  --ov-metric-bg: linear-gradient(180deg, rgba(255,255,255,0.035), rgba(255,255,255,0.015));
  --ov-metric-main-bg:
    linear-gradient(135deg, color-mix(in srgb, var(--app-primary) 18%, transparent), transparent 40%),
    linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.015));
  --ov-btn-bg: rgba(255, 255, 255, 0.03);
  --ov-btn-hover: rgba(255, 255, 255, 0.06);
  --ov-btn-text: #c7ccd4;
  background:
    radial-gradient(900px 420px at 12% -10%, color-mix(in srgb, var(--app-primary) 14%, transparent), transparent 55%),
    linear-gradient(180deg, #0b0c0e 0%, #08090a 100%);
}

.ov-btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 34px;
  padding: 0 12px;
  border-radius: 8px;
  border: 1px solid var(--ov-border);
  background: var(--ov-btn-bg);
  color: var(--ov-btn-text);
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease, transform 0.15s ease;
}
.ov-btn:hover {
  background: var(--ov-btn-hover);
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
  background: var(--ov-metric-bg);
  border: 1px solid var(--ov-border);
  min-height: 108px;
}
.ov-metric.main {
  grid-column: 1 / -1;
  background: var(--ov-metric-main-bg);
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
  font-size: clamp(26px, 3.2vw, 36px);
  white-space: normal;
  overflow: visible;
  text-overflow: clip;
  word-break: break-all;
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
  background: var(--ov-chip-bg);
  color: var(--ov-text-3);
  font-size: 11px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
}
.mix-total {
  margin-top: 12px;
  font-family: "SF Mono", "Menlo", "Consolas", ui-monospace, monospace;
  font-size: clamp(22px, 2.6vw, 30px);
  letter-spacing: -0.04em;
  font-variant-numeric: tabular-nums;
  line-height: 1.15;
  word-break: break-all;
}
.mix-delta {
  margin-top: 6px;
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 8px;
  min-height: 22px;
}
.mix-delta-main {
  font-family: "SF Mono", "Menlo", "Consolas", ui-monospace, monospace;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
}
.mix-delta-sub {
  font-size: 11.5px;
  color: var(--ov-text-4);
}
.mix-delta.up .mix-delta-main { color: var(--ov-up); }
.mix-delta.down .mix-delta-main { color: var(--ov-down); }
.mix-chart {
  margin-top: 8px;
  flex: 1 1 auto;
  min-height: 148px;
  width: 100%;
}
.mix-meta {
  margin-top: 8px;
  padding-top: 12px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.mix-meta-box {
  padding: 10px 12px;
  border-radius: 10px;
  background: var(--ov-chip-bg);
  border: 1px solid var(--ov-border);
  min-width: 0;
}
.mix-meta-box .l { font-size: 11px; color: var(--ov-text-4); }
.mix-meta-box .v {
  margin-top: 4px;
  font-family: "SF Mono", "Menlo", "Consolas", ui-monospace, monospace;
  font-size: 14px;
  letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
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
  background: var(--ov-chip-bg);
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
  border: 1px solid color-mix(in srgb, var(--ov-warn) 30%, var(--ov-border));
  background: var(--app-warn-soft);
  color: var(--ov-warn);
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
  background: var(--ov-chip-bg);
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease, transform 0.15s ease;
}
.ov-action:hover {
  background: color-mix(in srgb, var(--ov-chip-bg) 70%, var(--ov-accent-soft));
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
  .overview-metrics { grid-template-columns: 1fr; }
  .overview-page { margin: 0; padding: 4px 0 12px; }
  .mix-chart { min-height: 132px; }
}
@media (prefers-reduced-motion: reduce) {
  .ov-btn .spin { animation: none; }
  .ov-action { transition: none; }
}

/* empty hint on overview */
.overview-page :deep(.empty-hint) {
  background: var(--ov-chip-bg);
  border-color: var(--ov-border);
  color: var(--ov-text-3);
}
.overview-page :deep(.empty-hint strong) { color: var(--ov-text); }
</style>
