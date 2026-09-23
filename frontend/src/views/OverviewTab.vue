<template>
  <div class="overview-page">
    <!-- 收盘后还没记快照：提示 + 补记入口（两个页面共用同一个组件）；全页只出现一次 -->
    <SnapshotReminder />

    <!-- ① 今天：今天赚了多少 + 本月/今年 + 要不要动手 -->
    <section class="ov-section" data-section="today">
      <div class="ov-section-head">
        <h2 class="ov-section-title"><CalendarDays :size="14" :stroke-width="2" />① 今天</h2>
        <span class="ov-section-hint">先看今天赚没赚，再看账本</span>
      </div>

      <div class="overview-metrics">
        <div class="ov-metric main">
          <div class="ov-metric-label"><TrendingUp :size="13" :stroke-width="2" />今日盈亏</div>
          <div class="ov-metric-value" :class="todayPnlTone" :title="todayPnlTitle">{{ todayPnlText }}</div>
          <div class="ov-metric-sub">
            <span v-if="todayPnlPctText" :class="todayPnlTone">{{ todayPnlPctText }}</span>
            <span v-if="todayPnlPctText"> · </span>{{ todayPnlNote }}
          </div>
        </div>
        <div class="ov-metric">
          <div class="ov-metric-label"><CalendarDays :size="13" :stroke-width="2" />本月</div>
          <div class="ov-metric-value" :class="windowTone(monthWindow)" :title="windowTitle(monthWindow)">{{ windowGainText(monthWindow) }}</div>
          <div class="ov-metric-sub">{{ windowSubText(monthWindow) }}</div>
        </div>
        <div class="ov-metric">
          <div class="ov-metric-label"><Sun :size="13" :stroke-width="2" />今年</div>
          <div class="ov-metric-value" :class="windowTone(ytdWindow)" :title="windowTitle(ytdWindow)">{{ windowGainText(ytdWindow) }}</div>
          <div class="ov-metric-sub">{{ windowSubText(ytdWindow) }}</div>
        </div>
      </div>

      <div class="ov-todo">
        <div class="ov-todo-head">
          <span class="ov-todo-title"><ListChecks :size="14" :stroke-width="2" />待办</span>
          <span class="ov-todo-count">{{ todoItems.length ? `${todoItems.length} 项要动手` : '全部就绪' }}</span>
        </div>
        <div v-if="!todoItems.length" class="ov-todo-empty">今天没有待办</div>
        <ul v-else class="ov-todo-list">
          <li v-for="item in todoItems" :key="item.key">
            <button type="button" class="ov-todo-item" @click="item.run()">
              <span class="ov-todo-ico" :class="item.tone">
                <TriangleAlert v-if="item.tone === 'warn'" :size="14" :stroke-width="2" />
                <Info v-else :size="14" :stroke-width="2" />
              </span>
              <span class="ov-todo-text">
                <strong>{{ item.title }}</strong>
                <small>{{ item.hint }}</small>
              </span>
              <span class="ov-todo-go">{{ item.action }}<ArrowUpRight :size="13" :stroke-width="2" /></span>
            </button>
          </li>
        </ul>
      </div>
    </section>

    <!-- ② 资产与仓位：账本口径（已入账）；「当日参考」只作盘中参考，放本段末尾 -->
    <section class="ov-section" data-section="assets">
      <div class="ov-section-head">
        <h2 class="ov-section-title"><Coins :size="14" :stroke-width="2" />② 资产与仓位</h2>
        <span class="ov-section-hint">账本口径（已入账）</span>
      </div>

      <div class="overview-metrics">
        <div class="ov-metric main">
          <div class="ov-metric-label"><Coins :size="13" :stroke-width="2" />总资产</div>
          <div class="ov-metric-value" :title="formatMoney(dashboard.total_assets)">{{ formatMoney(dashboard.total_assets) }}</div>
          <div class="ov-metric-sub">市值 + 现金 + 存款 + 在途 · {{ holdingsCount }} 只持仓</div>
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
        <div class="ov-metric">
          <div class="ov-metric-label"><Gauge :size="13" :stroke-width="2" />权益 / 防御占比</div>
          <div class="ov-metric-value">{{ equityPctText }} / {{ defensivePctText }}</div>
          <div class="ov-metric-sub">结构口径，目标和偏离见「结构与目标」</div>
        </div>
        <div class="ov-metric ref">
          <div class="ov-metric-label"><Activity :size="13" :stroke-width="2" />当日参考</div>
          <div class="ov-metric-value" :class="todayContrib >= 0 ? 'up' : 'down'" :title="formatMoney(todayContrib, 2, true)">{{ formatMoney(todayContrib, 2, true) }}</div>
          <div class="ov-metric-sub">盘中粗估，不入账</div>
        </div>
      </div>
    </section>

    <!-- ③ 明细与入口：曲线 + 持仓速览 + 快捷入口 + 同步/备份状态 -->
    <section class="ov-section" data-section="detail">
      <div class="ov-section-head">
        <h2 class="ov-section-title"><Layers :size="14" :stroke-width="2" />③ 明细与入口</h2>
        <span class="ov-section-hint">趋势、持仓与同步状态</span>
      </div>

      <div class="overview-main">
        <div class="ov-stack">
          <aside class="mix-card">
            <div class="mix-head">
              <div class="mix-title"><Activity :size="14" :stroke-width="2" />近半月资产</div>
              <div class="mix-chip">{{ weekChipText }}</div>
            </div>
            <div class="mix-total" :title="formatMoney(dashboard.total_assets)">{{ formatMoney(dashboard.total_assets) }}</div>
            <div class="mix-delta" :class="weekDeltaClass">
              <span class="mix-delta-main">{{ weekDeltaText }}</span>
              <span class="mix-delta-sub">{{ weekDeltaSubText }}</span>
            </div>
            <div id="overviewWeekChart" class="mix-chart" aria-label="近半月总资产曲线"></div>
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
              aria-label="持仓速览"
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
      </div>

      <div class="overview-status">
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
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, watch } from 'vue';
import {
  Activity,
  ArrowUpRight,
  CalendarDays,
  Camera,
  CheckCircle2,
  Coins,
  Compass,
  Gauge,
  HardDrive,
  Info,
  Landmark,
  Layers,
  ListChecks,
  PenLine,
  Radar,
  Sun,
  TrendingUp,
  TriangleAlert,
  Zap,
} from 'lucide-vue-next';
import SnapshotReminder from '../components/SnapshotReminder.vue';
import { useAppCtx } from '../composables/useAppCtx.js';
import { formatPercent, todayLocalIso } from '../utils/index.js';

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
  // 收益分析模块的口径：总览第一段「今天 / 本月 / 今年」直接复用，避免两页算法不一致。
  // 今日盈亏用 perfTodayPnl（今天已有正式快照时照样给数）；perfTodayRow 是给
  // 收益分析的「每日收益」表补一行用的，那个今天有快照时会返回 null，首页不能用。
  perfSummary,
  perfTodayPnl,
  perfWindowCards,
  perfLatestSnapshotDate,
} = useAppCtx();

/** ref / computed / 裸值都兼容（测试里挂载这些 view 时 ctx 可能是裸值） */
const unwrap = (v) => (v && typeof v === 'object' && 'value' in v ? v.value : v);
const dash = computed(() => unwrap(dashboard) || {});
const snapshotDone = computed(() => !!unwrap(todaySnapshotDone));
const perfWindows = computed(() => {
  const list = unwrap(perfWindowCards);
  return Array.isArray(list) ? list : [];
});
/** performance 模块的今日盈亏口径（perfTodayPnl）；null = 拿不到今日口径（不估算） */
const perfToday = computed(() => unwrap(perfTodayPnl) || null);

/** 收益分析模块有没有拉到过数据（区分「没数」和「没加载」） */
const perfLoaded = computed(() => !!unwrap(perfSummary));
const TREND_LOOKBACK_DAYS = 15;
const TREND_MAX_POINTS = 16;

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

/** 近半月快照；窗口内不足时回退最近若干条，避免总览空白 */
const weekSeriesMeta = computed(() => {
  const all = normalizeSnapshotRows(snapshots?.value ?? snapshots ?? []);
  const start = isoDaysAgo(TREND_LOOKBACK_DAYS - 1);
  let rows = all.filter((r) => r.date >= start);
  let mode = 'week';

  // 近半月快照不足 2 点：用最近快照（最多 15 条左右）兜底，本地/断档时仍能看趋势
  if (rows.length < 2) {
    rows = all.slice(-TREND_LOOKBACK_DAYS);
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
  if (rows.length > TREND_MAX_POINTS) {
    rows = rows.slice(-TREND_MAX_POINTS);
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

const pendingCount = computed(() => {
  const d = dash.value;
  const fromDash = Number(d.pending_count || 0);
  if (fromDash) return fromDash;
  const rows = unwrap(pendingTransactions);
  return Array.isArray(rows) ? rows.length : 0;
});

const pendingCountText = computed(() => `${pendingCount.value} 笔`);

// ------------------------------------------------------- ① 今天：盈亏窗口
const monthWindow = computed(() => perfWindows.value.find((w) => w && w.key === 'month') || null);
const ytdWindow = computed(() => perfWindows.value.find((w) => w && w.key === 'ytd') || null);

function windowGainText(w) {
  return w && w.gain != null ? formatMoney(w.gain, 2, true) : '—';
}
function windowTone(w) {
  if (!w) return '';
  if (w.tone === 'up' || w.tone === 'down') return w.tone;
  if (w.gainPct != null) return Number(w.gainPct) >= 0 ? 'up' : 'down';
  if (w.gain != null) return Number(w.gain) >= 0 ? 'up' : 'down';
  return '';
}
function windowSubText(w) {
  if (!w) return '收益窗口未加载';
  if (w.gain == null) return '暂无快照基准';
  const pctText = w.gainPct != null ? formatPercent(Number(w.gainPct), 2) : '无涨跌幅基准';
  const staleText = w.stale && w.baseDate ? ` · 基准 ${w.baseDate}（${w.staleDays} 天前）` : '';
  return `${pctText}${staleText}`;
}
function windowTitle(w) {
  if (!w) return '收益窗口未加载';
  return `${w.label || '窗口'}：${w.gain != null ? formatMoney(w.gain, 2, true) : '无数据'}`;
}

const todayPnlTone = computed(() => {
  const row = perfToday.value;
  if (!row || row.change == null) return '';
  return Number(row.change) >= 0 ? 'up' : 'down';
});
/** 拿不到今日窗口就显示「—」并说明原因，绝不自己估算 */
const todayPnlText = computed(() => {
  const row = perfToday.value;
  if (!row || row.change == null) return '—';
  return formatMoney(row.change, 2, true);
});
const todayPnlPctText = computed(() => {
  const row = perfToday.value;
  if (!row || row.change == null || row.pct == null) return '';
  return formatPercent(Number(row.pct), 2);
});
const todayPnlTitle = computed(() => {
  const row = perfToday.value;
  if (!row || row.change == null) return '没有可用的今日口径（不估算）';
  const pctText = row.pct != null ? ` · ${formatPercent(Number(row.pct), 2)}` : '';
  return `今日盈亏 ${formatMoney(row.change, 2, true)}${pctText}`;
});
const todayPnlNote = computed(() => {
  const row = perfToday.value;
  if (row && row.change != null) {
    if (row.stale && row.daysGap != null && row.baseDate) {
      return `基准 ${row.baseDate}（跨 ${row.daysGap} 天，不一定是上一交易日）`;
    }
    if (row.closed) return row.prevDate ? `已收盘 · 较 ${row.prevDate}` : '已收盘 · 今日快照';
    return row.baseDate ? `盘中口径 · 基准 ${row.baseDate}` : '未收盘，盘中口径';
  }
  // 没数时先说清是哪一种「没有」，别让用户以为是零
  if (!perfLoaded.value) return '收益数据未加载，进「收益分析」就有数';
  const latest = unwrap(perfLatestSnapshotDate);
  if (snapshotDone.value) {
    return latest ? `今日快照已记录（${latest}）` : '今日快照已记录';
  }
  return '拿不到今日口径（快照断档），不估算';
});

/** 待办：只收「需要你动手」的事，每条都能点着跳到对应页面 */
const todoItems = computed(() => {
  const list = [];
  const d = dash.value;

  const pendingAmount = Number(d.pending_purchase || 0);
  if (pendingAmount > 0) {
    list.push({
      key: 'pending',
      tone: 'warn',
      title: `${pendingCount.value} 笔申购在途，金额 ${formatMoney(pendingAmount)}`,
      hint: '成交后记得确认入账',
      action: '查看在途',
      run: () => {
        if (typeof goPendingTransactions === 'function') goPendingTransactions();
        else if (typeof goTab === 'function') goTab('transactions');
      },
    });
  }

  if (!snapshotDone.value) {
    list.push({
      key: 'snapshot',
      tone: 'warn',
      title: `今日快照未记录（最新 ${d.latest_snapshot_date || '暂无'}）`,
      hint: '逐日收益靠它，补一条再收工',
      action: '去收益与快照',
      run: () => {
        // 资产快照页已并入「收益与快照」（快照明细在那里）
        if (typeof goTab === 'function') goTab('performance');
      },
    });
  }

  if (d.price_stale) {
    const priceText = unwrap(latestPriceStatusText) || '同步一次最新价';
    list.push({
      key: 'price',
      tone: 'warn',
      title: `最新价偏旧：${priceText}`,
      hint: '同步后持仓浮盈才是今天的',
      action: '去持仓明细',
      run: () => {
        if (typeof goTab === 'function') goTab('holdings');
      },
    });
  }

  return list;
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
  const pctText = pct === null ? '' : ` · ${formatPercent(pct, 2)}`;
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
  return `近半月 ${n} 点`;
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

/* 三段式页头：① 今天 / ② 资产与仓位 / ③ 明细与入口 */
.ov-section { margin-top: 14px; }
.ov-section:first-of-type { margin-top: 0; }
.ov-section-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px 12px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.ov-section-title {
  margin: 0;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 14px;
  font-weight: 700;
  color: var(--ov-text-2);
  letter-spacing: -0.01em;
}
.ov-section-hint { font-size: 12px; color: var(--ov-text-4); }
/* 卡片数各段不同（「今天」3 张、「资产与仓位」5 张），窗口宽度也一直在变，
   所以用 auto-fit 让列数自适应 —— 原来写死 3 列 + 主卡独占一整行，
   结果是两段的行尾都会空出格子（今天空 1 格、资产空 2 格），而且主卡占满
   1240px 只放一个数字，纵向很浪费。 */
.overview-metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 12px;
}
.ov-metric {
  padding: 14px 16px;
  border-radius: 12px;
  background: var(--ov-metric-bg);
  border: 1px solid var(--ov-border);
  min-height: 96px;
}
/* 列数按「这一段有几张卡」定，保证行行填满：
   ① 今天 = 主卡(占 2 轨) + 本月 + 今年 = 4 轨
   ② 资产与仓位 = 主卡(占 2 轨) + 浮盈 + 现金 + 占比 = 5 轨（参考卡单独整行） */
[data-section="today"] .overview-metrics { grid-template-columns: repeat(4, minmax(0, 1fr)); }
[data-section="assets"] .overview-metrics { grid-template-columns: repeat(5, minmax(0, 1fr)); }

.ov-metric.main {
  /* 比同排宽一倍（视觉上仍是主角），但不再独占整行 */
  grid-column: span 2;
  background: var(--ov-metric-main-bg);
}
/* 盘中参考：虚线 + 弱化，避免和账本口径混着看；口径不同，单独占一行 */
.ov-metric.ref {
  grid-column: 1 / -1;
  border-style: dashed;
  background: color-mix(in srgb, var(--ov-chip-bg) 70%, transparent);
}
.ov-metric.ref .ov-metric-value { font-size: clamp(17px, 1.9vw, 22px); }
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

/* 待办：一行一条，能点就跳 */
.ov-todo {
  margin-top: 12px;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid var(--ov-border);
  background: var(--ov-panel);
}
.ov-todo-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}
.ov-todo-title {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 13px;
  font-weight: 600;
  color: var(--ov-text-2);
}
.ov-todo-count { font-size: 11.5px; color: var(--ov-text-4); }
.ov-todo-empty { margin-top: 8px; font-size: 12.5px; color: var(--ov-text-4); }
.ov-todo-list {
  list-style: none;
  margin: 10px 0 0;
  padding: 0;
  display: grid;
  gap: 8px;
}
.ov-todo-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid var(--ov-border);
  background: var(--ov-chip-bg);
  color: inherit;
  font-family: inherit;
  text-align: left;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease, transform 0.15s ease;
}
.ov-todo-item:hover {
  background: color-mix(in srgb, var(--ov-chip-bg) 70%, var(--ov-accent-soft));
  border-color: var(--ov-border-strong);
  transform: translateY(-1px);
}
.ov-todo-ico {
  width: 30px;
  height: 30px;
  border-radius: 9px;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  background: rgba(127, 127, 127, 0.08);
  border: 1px solid var(--ov-border);
  color: var(--ov-text-2);
}
.ov-todo-ico.warn {
  background: rgba(245, 158, 11, 0.12);
  border-color: rgba(245, 158, 11, 0.25);
  color: var(--ov-warn);
}
.ov-todo-text { min-width: 0; flex: 1 1 auto; }
.ov-todo-text strong {
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: var(--ov-text);
}
.ov-todo-text small {
  display: block;
  margin-top: 2px;
  font-size: 11.5px;
  color: var(--ov-text-4);
}
.ov-todo-go {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 600;
  color: var(--ov-accent);
}

.overview-main {
  margin-top: 14px;
  display: grid;
  grid-template-columns: 1.6fr 0.9fr;
  gap: 14px;
}
.ov-stack,
.overview-side {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
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
  .overview-main,
  .overview-status { grid-template-columns: 1fr; }
  /* 必须用和上面同样的 [data-section=…] 选择器：否则特异性更低、覆盖不掉桌面规则 */
  [data-section="today"] .overview-metrics,
  [data-section="assets"] .overview-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .ov-metric.main { grid-column: 1 / -1; }
}
@media (max-width: 640px) {
  [data-section="today"] .overview-metrics,
  [data-section="assets"] .overview-metrics { grid-template-columns: 1fr; }
  /* 单列时主卡不能再跨 2 轨，否则会撑出一个隐式列、整段错位 */
  .ov-metric.main { grid-column: auto; }
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
