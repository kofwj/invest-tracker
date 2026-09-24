<template>
  <div class="overview-page">
    <!-- 收盘后还没记快照：提示 + 补记入口（两个页面共用同一个组件）；全页只出现一次 -->
    <SnapshotReminder />

    <!-- ① 今天：今日盈亏 + 盘中粗估 + 最新价同步时间 / 右侧「要动手」 -->
    <section class="ov-section" data-section="today">
      <div class="ov-card pad">
        <div class="ov-today">
          <div class="ov-today-main">
            <p class="ov-eyebrow">今天 · 最近一个交易日</p>
            <div class="ov-lede-line">
              <span class="ov-lede num" :class="todayPnlTone" :title="todayPnlTitle">{{ todayPnlText }}</span>
              <span v-if="todayPnlPctText" class="ov-lede-meta num" :class="todayPnlTone">{{ todayPnlPctText }}</span>
              <span class="ov-lede-note">{{ todayPnlNote }}</span>
            </div>
            <div class="ov-hero-foot">
              <span class="ov-hero-ref" :title="`盘中估算，不入账 · ${formatMoney(todayContrib, 2, true)}`">
                盘中粗估 {{ formatMoney(todayContrib, 2, true) }}（不入账）
              </span>
              <span>最新价 {{ priceSyncText }} 同步</span>
            </div>
          </div>

          <div class="ov-today-side">
            <div v-if="todoItems.length" class="ov-todo-head">{{ todoItems.length }} 项要动手</div>
            <div v-if="!todoItems.length" class="ov-todo-empty">今天没有待办</div>
            <ul v-else class="ov-todo-list">
              <li v-for="item in todoItems" :key="item.key">
                <button type="button" class="ov-todo-item" @click="item.run()">
                  <span class="ov-todo-text">
                    <strong>{{ item.title }}</strong>
                    <small>{{ item.hint }}</small>
                  </span>
                  <span class="ov-todo-go">{{ item.action }}<ArrowUpRight :size="13" :stroke-width="2" /></span>
                </button>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </section>

    <!-- ② 资产：四个数字一行（发丝线分格）+ 持仓速览 -->
    <section class="ov-section" data-section="assets">
      <div class="ov-card">
        <div class="overview-metrics">
          <div class="ov-metric">
            <div class="ov-metric-label">现在总资产</div>
            <div class="ov-metric-value" :title="formatMoney(dash.total_assets)">{{ formatMoney(dash.total_assets) }}</div>
            <div class="ov-metric-sub">市值 {{ formatMoney(dash.total_market_value) }} + 现金存款 {{ formatMoney(cashAndBank) }}</div>
          </div>
          <div class="ov-metric">
            <div class="ov-metric-label">持仓浮盈</div>
            <div class="ov-metric-value" :class="profitTone" :title="formatMoney(dash.total_profit, 2, true)">
              {{ formatMoney(dash.total_profit, 2, true) }}
            </div>
            <div class="ov-metric-sub">{{ holdingsCount }} 只 · 含分红 {{ formatMoney(dividendSum) }}</div>
          </div>
          <div class="ov-metric">
            <div class="ov-metric-label">现金 + 存款</div>
            <div class="ov-metric-value" :title="formatMoney(cashAndBank)">{{ formatMoney(cashAndBank) }}</div>
            <div class="ov-metric-sub">银行 {{ formatMoney(dash.bank_balance) }} · 证券 {{ formatMoney(dash.securities_cash) }}</div>
          </div>
          <div class="ov-metric">
            <div class="ov-metric-label">权益 / 防御</div>
            <div class="ov-metric-value">{{ equityPctText }} / {{ defensivePctText }}</div>
            <div class="ov-metric-sub">市值口径 · 偏离见「结构与目标」</div>
          </div>
        </div>
      </div>

      <div class="ov-card pad">
        <div class="ov-card-head">
          <h2 class="ov-h2">持仓速览</h2>
          <span class="ov-note">{{ holdingsCount }} 只 · 按市值排序</span>
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
          <el-table-column label="分红" min-width="104" align="right" header-align="right">
            <template #default="scope">
              <span class="num-cell">{{ formatMoney(scope.row.total_dividend) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </section>

    <!-- ③ 组合脉搏 + 同步与备份：都不折叠，进页就能看见 -->
    <section class="ov-section" data-section="detail">
      <div class="ov-card pad">
        <div class="ov-card-head">
          <h2 class="ov-h2">组合脉搏</h2>
          <span class="ov-note">市值口径 · 结构目标见「结构与目标」</span>
        </div>
        <div class="ov-brief">
          <div>
            <div class="ov-brief-k">权益仓位</div>
            <div class="ov-brief-v num">{{ equityPctText }}</div>
          </div>
          <div>
            <div class="ov-brief-k">防御资产</div>
            <div class="ov-brief-v num">{{ defensivePctText }}</div>
          </div>
          <div>
            <div class="ov-brief-k">现金 + 存款占比</div>
            <div class="ov-brief-v num">{{ cashRatioText }}</div>
          </div>
          <div>
            <div class="ov-brief-k">在途申购</div>
            <div class="ov-brief-v num">{{ pendingCountText }}</div>
          </div>
          <div>
            <div class="ov-brief-k">持仓市值</div>
            <div class="ov-brief-v num">{{ formatMoney(dash.total_market_value) }}</div>
          </div>
          <div>
            <div class="ov-brief-k">持仓只数</div>
            <div class="ov-brief-v num">{{ holdingsCount }} 只</div>
          </div>
          <div>
            <div class="ov-brief-k">全周期盈亏</div>
            <div class="ov-brief-v num" :class="lifetimeTone" :title="formatMoney(dash.lifetime_profit, 2, true)">
              {{ formatMoney(dash.lifetime_profit, 2, true) }}
            </div>
          </div>
          <div>
            <div class="ov-brief-k">目标年化</div>
            <div class="ov-brief-v num">{{ expectedReturnText }}</div>
          </div>
        </div>
      </div>

      <div class="ov-card pad">
        <div class="ov-card-head">
          <h2 class="ov-h2">同步与备份</h2>
          <span class="ov-note">价格与快照的时效</span>
        </div>
        <div class="ov-brief">
          <div>
            <div class="ov-brief-k">最新价同步</div>
            <div class="ov-brief-v num" :title="latestPriceStatusText">{{ priceSyncText }}</div>
          </div>
          <div>
            <div class="ov-brief-k">价格时效</div>
            <div class="ov-brief-v num" :class="dash.price_stale ? 'warn' : ''">{{ priceAgeText }}</div>
          </div>
          <div>
            <div class="ov-brief-k">最近快照</div>
            <div class="ov-brief-v num">{{ dash.latest_snapshot_date || '—' }}</div>
          </div>
          <div>
            <div class="ov-brief-k">未定价 / 手动价</div>
            <div class="ov-brief-v num">{{ priceQualityText }}</div>
          </div>
          <div>
            <div class="ov-brief-k">最近备份</div>
            <div class="ov-brief-v num" :title="String(unwrap(maintenanceStatus)?.latest_backup || '')">{{ backupText }}</div>
          </div>
          <div>
            <div class="ov-brief-k">备份份数</div>
            <div class="ov-brief-v num">{{ backupCountText }}</div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue';
import { ArrowUpRight } from 'lucide-vue-next';
import SnapshotReminder from '../components/SnapshotReminder.vue';
import { useAppCtx } from '../composables/useAppCtx.js';
import { formatPercent } from '../utils/index.js';

const {
  dashboard,
  holdings,
  todaySnapshotDone,
  latestPriceStatusText,
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
  // 收益分析模块的口径：今日盈亏直接复用 perfTodayPnl（今天已有正式快照时照样给数）。
  // perfTodayRow 是给「每日收益」表补一行用的，今天有快照时会返回 null，首页不能用。
  perfSummary,
  perfTodayPnl,
  perfLatestSnapshotDate,
  // 人工对账记录：和快照明细（SnapshotPanel）用的是同一个 GET /snapshots/reconcile
  reconcileData,
  fetchReconcile,
  // 备份信息：原来挂在底部状态条上，状态条删掉后挪进「同步与备份」
  latestBackupText,
  backups,
  maintenanceStatus,
} = useAppCtx();

/** ref / computed / 裸值都兼容（测试里挂载这些 view 时 ctx 可能是裸值） */
const unwrap = (v) => (v && typeof v === 'object' && 'value' in v ? v.value : v);
const dash = computed(() => unwrap(dashboard) || {});
const snapshotDone = computed(() => !!unwrap(todaySnapshotDone));
/** performance 模块的今日盈亏口径（perfTodayPnl）；null = 拿不到今日口径（不估算） */
const perfToday = computed(() => unwrap(perfTodayPnl) || null);
/** 收益分析模块有没有拉到过数据（区分「没数」和「没加载」） */
const perfLoaded = computed(() => !!unwrap(perfSummary));

/** 百分比（默认一位小数）；取不到给「—」而不是 0 */
function pctText(value, digits = 1) {
  if (value === null || value === undefined || value === '') return '—';
  const n = Number(value);
  return Number.isFinite(n) ? `${n.toFixed(digits)}%` : '—';
}

const holdingsCount = computed(() => {
  const fromDash = dash.value.holdings_count;
  if (fromDash !== null && fromDash !== undefined && fromDash !== '') return Number(fromDash) || 0;
  const list = holdings?.value ?? holdings ?? [];
  return Array.isArray(list) ? list.length : 0;
});

/** 持仓速览：按市值降序（原型就是按市值排的） */
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

/** 累计分红（持仓表 total_dividend 之和）；没有持仓时给 null，显示「—」 */
const dividendSum = computed(() => {
  const list = holdings?.value ?? holdings ?? [];
  if (!Array.isArray(list) || !list.length) return null;
  return list.reduce((sum, row) => sum + Number(row?.total_dividend || 0), 0);
});

const todayContrib = computed(() => {
  const sig = marketSignals?.value ?? marketSignals ?? {};
  return Number(sig.today_contrib_estimate || 0);
});

const cashAndBank = computed(() => {
  const d = dash.value;
  return Number(d.securities_cash || 0) + Number(d.bank_balance || 0);
});

const summary = computed(() => allocationSummary?.value ?? allocationSummary ?? {});
const equityPctText = computed(() => pctText(summary.value.equityRatio));
const defensivePctText = computed(() => pctText(summary.value.defensiveRatio));

/** 「现金 + 存款」占总资产的比例 */
const cashRatioText = computed(() => {
  const total = Number(dash.value.total_assets || 0);
  if (!(total > 0)) return '—';
  return `${(cashAndBank.value / total * 100).toFixed(1)}%`;
});

const expectedReturnText = computed(() => {
  const raw = unwrap(portfolioExpectedReturn);
  if (raw === null || raw === undefined || raw === '') return '—';
  const n = Number(raw);
  return Number.isFinite(n) ? `${n.toFixed(2)}%` : '—';
});

const profitTone = computed(() => (Number(dash.value.total_profit || 0) >= 0 ? 'up' : 'down'));
const lifetimeTone = computed(() => (Number(dash.value.lifetime_profit || 0) >= 0 ? 'up' : 'down'));

const pendingCount = computed(() => {
  const d = dash.value;
  const fromDash = Number(d.pending_count || 0);
  if (fromDash) return fromDash;
  const rows = unwrap(pendingTransactions);
  return Array.isArray(rows) ? rows.length : 0;
});
const pendingCountText = computed(() => `${pendingCount.value} 笔`);

/** 最新一次成功同步价的时间：ISO → 「MM-DD HH:mm」（原型就是短格式） */
const priceSyncText = computed(() => {
  const d = dash.value;
  const raw = d.last_price_sync_at || d.latest_price_updated_at;
  if (!raw) return '—';
  const s = String(raw).replace('T', ' ');
  const m = s.match(/^\d{4}-(\d{2}-\d{2})[ ](\d{2}:\d{2})/);
  return m ? `${m[1]} ${m[2]}` : s.slice(0, 16);
});

/** 价格时效：几小时前 + 有没有过期（后端 price_age_hours / price_stale） */
const priceAgeText = computed(() => {
  const d = dash.value;
  const h = d.price_age_hours;
  const stale = !!d.price_stale;
  if (h === null || h === undefined || h === '' || !Number.isFinite(Number(h))) {
    return stale ? '已偏旧' : '—';
  }
  return `${Number(h).toFixed(1)} 小时前 · ${stale ? '已过期' : '未过期'}`;
});

/** 未定价 / 手动价 只数；两项都取不到给「—」 */
const priceQualityText = computed(() => {
  const d = dash.value;
  const unpriced = d.unpriced_count === null || d.unpriced_count === undefined ? null : Number(d.unpriced_count);
  let manual = null;
  if (d.manual_price_count !== null && d.manual_price_count !== undefined) manual = Number(d.manual_price_count);
  else if (Array.isArray(d.manual_price_codes)) manual = d.manual_price_codes.length;
  const fmt = (v) => (v === null || !Number.isFinite(v) ? '—' : `${v} 只`);
  return `${fmt(unpriced)} / ${fmt(manual)}`;
});

const maintenance = computed(() => unwrap(maintenanceStatus) || {});
/** 最近备份时间：ctx 没给就回落到 maintenanceStatus，再没有就「—」（不编成「暂无备份」） */
const backupText = computed(() => {
  const v = unwrap(latestBackupText);
  if (v != null && v !== '') return String(v);
  const at = maintenance.value.latest_backup_at;
  return at ? String(at).replace('T', ' ').slice(0, 16) : '—';
});
const backupCountText = computed(() => {
  const list = unwrap(backups);
  if (Array.isArray(list) && list.length) return `${list.length} 份`;
  const n = maintenance.value.backup_count;
  return n == null ? '—' : `${Number(n)} 份`;
});

// ------------------------------------------------------- ① 今天：盈亏口径
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

/** 人工对账记录；null/undefined = 还没录过 */
const reconcileRecord = computed(() => unwrap(reconcileData) || null);

/** 待办：只收「需要你动手」的事，每条都能点着跳到对应页面 */
const todoItems = computed(() => {
  const list = [];
  const d = dash.value;

  const pendingAmount = Number(d.pending_purchase || 0);
  if (pendingAmount > 0) {
    list.push({
      key: 'pending',
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
      title: `今日快照未记录（最新 ${d.latest_snapshot_date || '暂无'}）`,
      hint: '逐日收益靠它，补一条再收工',
      action: '去收益与快照',
      run: () => {
        // 资产快照页已并入「收益与快照」（快照明细在那里）
        if (typeof goTab === 'function') goTab('performance');
      },
    });
  }

  // 没有人工对账记录：账本和券商实际余额还没对齐过一次
  if (!reconcileRecord.value) {
    list.push({
      key: 'reconcile',
      title: '还没做过人工对账',
      hint: '每周对照券商实际余额录一次',
      action: '去对账',
      run: () => {
        // 人工对账表单在「收益与快照」页的快照明细里
        if (typeof goTab === 'function') goTab('performance');
      },
    });
  }

  if (d.price_stale) {
    const priceText = unwrap(latestPriceStatusText) || '同步一次最新价';
    list.push({
      key: 'price',
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

async function refreshOverview() {
  const jobs = [];
  if (typeof refreshMarket === 'function') jobs.push(refreshMarket());
  // 人工对账记录只在快照明细那条链路上拉过；总览先进时要补一次，否则待办会误报「还没做过」
  if (typeof fetchReconcile === 'function' && !reconcileRecord.value) jobs.push(fetchReconcile());
  if (jobs.length) await Promise.all(jobs);
}

function onRowClick(row) {
  if (typeof showTransactions === 'function') showTransactions(row);
}

onMounted(() => {
  refreshOverview();
});
</script>

<style scoped>
/* 视觉语言照 docs/design/prototype/overview.html：页底色由 body 给，这里只排卡片。
   卡片 = surface + 1px border + 16 圆角 + 极淡阴影；卡内分区一律用发丝线，不再卡片套卡片。 */
.overview-page {
  color: var(--app-text);
  font-feature-settings: "cv01", "ss03";
}

/* 数字一律等宽 + tabular-nums */
.num {
  font-family: ui-monospace, "SF Mono", Menlo, Consolas, "Roboto Mono", monospace;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
}

.ov-section { margin-bottom: 22px; }
.ov-section:last-child { margin-bottom: 0; }

.ov-card {
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: 16px;
  box-shadow: var(--app-shadow-sm);
  overflow: hidden;
}
.ov-card.pad { padding: 20px 22px; }

.ov-btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 34px;
  padding: 0 12px;
  border-radius: 8px;
  border: 1px solid var(--app-border);
  background: var(--app-header-btn-bg);
  color: var(--app-header-btn-text);
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease, transform 0.15s ease;
}
.ov-btn:hover {
  background: var(--app-header-btn-hover);
  border-color: color-mix(in srgb, var(--app-border) 65%, var(--app-muted));
}
.ov-btn:active { transform: translateY(1px); }
.ov-btn.compact { height: 30px; padding: 0 10px; }

.up { color: var(--app-up); }
.down { color: var(--app-down); }
.warn { color: var(--app-warn); }

/* ① 今天：左右两栏，窄屏上下堆叠 */
.ov-today {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 24px;
  align-items: start;
}
.ov-today-main { min-width: 0; }
.ov-today-side {
  min-width: 0;
  border-left: 1px solid var(--app-hairline);
  padding-left: 24px;
}
.ov-eyebrow {
  margin: 0 0 10px;
  font-size: 12px;
  font-weight: 600;
  color: var(--app-soft);
}
.ov-lede-line {
  display: flex;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
}
.ov-lede {
  font-size: 34px;
  line-height: 1.15;
  font-weight: 700;
  letter-spacing: -0.02em;
}
.ov-lede-meta { font-size: 13px; font-weight: 500; color: var(--app-muted); }
.ov-lede-note { font-size: 13px; font-weight: 500; color: var(--app-muted); }
.ov-hero-foot {
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
  margin-top: 12px;
  font-size: 12px;
  color: var(--app-soft);
}
.ov-hero-ref { white-space: nowrap; }

/* 待办：一行一条，能点就跳 */
.ov-todo-head {
  font-size: 12px;
  font-weight: 600;
  color: var(--app-warn);
  margin-bottom: 10px;
}
.ov-todo-empty { font-size: 13px; color: var(--app-soft); }
.ov-todo-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 8px;
}
.ov-todo-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 13px;
  border-radius: 10px;
  border: 1px solid transparent;
  background: var(--app-warn-soft);
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.15s ease, transform 0.15s ease;
}
.ov-todo-item:hover {
  border-color: color-mix(in srgb, var(--app-warn) 40%, transparent);
}
.ov-todo-text { min-width: 0; flex: 1 1 auto; }
.ov-todo-text strong {
  display: block;
  font-size: 13.5px;
  font-weight: 600;
  color: var(--app-text);
}
.ov-todo-text small {
  display: block;
  margin-top: 2px;
  font-size: 12px;
  color: var(--app-muted);
}
.ov-todo-go {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--app-warn);
  white-space: nowrap;
}

/* 卡片头：h2 + 说明 + 右侧动作 */
.ov-card-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 14px;
}
.ov-h2 { margin: 0; font-size: 15px; font-weight: 650; color: var(--app-text); }
.ov-note { font-size: 12px; color: var(--app-soft); margin-right: auto; }

/* ② 资产：四个数字一行，发丝线分格 */
.overview-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}
[data-section="assets"] .overview-metrics { grid-template-columns: repeat(4, minmax(0, 1fr)); }
.ov-metric { padding: 18px 22px; min-width: 0; }
.ov-metric-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--app-muted);
  margin-bottom: 7px;
}
.ov-metric-value {
  font-family: ui-monospace, "SF Mono", Menlo, Consolas, "Roboto Mono", monospace;
  font-size: 21px;
  font-weight: 650;
  letter-spacing: -0.03em;
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ov-metric-sub {
  margin-top: 5px;
  font-size: 12px;
  color: var(--app-soft);
}

/* 持仓速览表：跟着卡片底色走，边框用发丝线 */
.overview-holdings-table {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: transparent;
  --el-table-row-hover-bg-color: color-mix(in srgb, var(--app-bg0) 45%, transparent);
  --el-table-border-color: var(--app-hairline);
  --el-table-text-color: var(--app-text);
  --el-table-header-text-color: var(--app-muted);
  background: transparent !important;
  color: var(--app-text);
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
.overview-holdings-table :deep(.asset-cell-name) { color: var(--app-text); }
.overview-holdings-table :deep(.asset-cell-code) { color: var(--app-soft); }
.overview-holdings-table :deep(.num-cell) { color: var(--app-text); }
.overview-holdings-table :deep(.el-table__empty-text) { color: var(--app-soft); }

/* ③ 组合脉搏 / 同步与备份：4 列 × 2 行 / 1 行 */
.ov-brief {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}
.ov-brief-k {
  font-size: 12px;
  color: var(--app-muted);
  margin-bottom: 5px;
}
.ov-brief-v {
  font-size: 16px;
  font-weight: 640;
  color: var(--app-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 窄屏：卡片内栏位塌成一列，发丝线不能留在行尾 */
@media (max-width: 1100px) {
  /* 必须用和桌面同样的 [data-section=…] 选择器：否则特异性更低、覆盖不掉上面的规则 */
  [data-section="assets"] .overview-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  [data-section="assets"] .ov-metric:nth-child(odd) { border-left: 0; }
  [data-section="assets"] .ov-metric:nth-child(n + 3) { border-top: 1px solid var(--app-hairline); }
  .ov-today { grid-template-columns: minmax(0, 1fr); }
  .ov-today-side {
    border-left: 0;
    padding-left: 0;
    border-top: 1px solid var(--app-hairline);
    padding-top: 18px;
  }
  .ov-brief { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 640px) {
  [data-section="assets"] .overview-metrics { grid-template-columns: minmax(0, 1fr); }
  /* 单列时每格只在顶部留一条发丝线，左侧分隔线全部去掉（否则会挂在行首） */
  [data-section="assets"] .ov-metric + .ov-metric {
    border-left: 0;
    border-top: 1px solid var(--app-hairline);
  }
  .ov-lede { font-size: 28px; }
  .ov-metric { padding: 14px 18px; }
  .ov-card.pad { padding: 16px 18px; }
}
@media (prefers-reduced-motion: reduce) {
  .ov-btn,
  .ov-todo-item { transition: none; }
}

/* empty hint on overview */
.overview-page :deep(.empty-hint) {
  background: color-mix(in srgb, var(--app-surface) 88%, var(--app-bg0));
  border-color: var(--app-border);
  color: var(--app-muted);
}
.overview-page :deep(.empty-hint strong) { color: var(--app-text); }
</style>