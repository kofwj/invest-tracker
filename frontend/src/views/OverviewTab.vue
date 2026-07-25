<template>
  <div class="overview-page" @pointermove="onPointerMove">
    <div class="overview-header">
      <div>
        <div class="overview-kicker">
          <span class="overview-dot" />
          盘中粗估 · 不入账
        </div>
        <h3 class="overview-title">家底一眼清</h3>
        <div class="overview-subtitle">
          总资产、浮盈、现金存款与状态压成一屏；点持仓进明细。右侧是资产轨道示意。
        </div>
        <div class="overview-mix-tag">
          <Orbit :size="12" :stroke-width="2" />
          A 底 + B 曲线
        </div>
      </div>
      <div class="overview-actions">
        <button type="button" class="ov-btn" :disabled="marketLoading" @click="refreshOverview">
          <RefreshCw :size="14" :stroke-width="2" :class="{ spin: marketLoading }" />
          刷新
        </button>
        <button type="button" class="ov-btn" @click="goTab('holdings')">
          <Layers :size="14" :stroke-width="2" />
          持仓明细
        </button>
        <button type="button" class="ov-btn" @click="goTab('decision')">
          <Compass :size="14" :stroke-width="2" />
          今天该看
        </button>
        <button type="button" class="ov-btn primary" @click="goTab('transactions')">
          <PenLine :size="14" :stroke-width="2" />
          记交易
        </button>
      </div>
    </div>

    <section class="overview-hero">
      <div class="overview-hero-main">
        <div class="overview-metrics">
          <div class="ov-metric main">
            <div class="ov-metric-label"><Coins :size="13" :stroke-width="2" />总资产</div>
            <div class="ov-metric-value">{{ formatMoney(dashboard.total_assets) }}</div>
            <div class="ov-metric-sub">市值 + 现金 + 存款 + 在途 · {{ holdingsCount }} 只持仓</div>
          </div>
          <div class="ov-metric">
            <div class="ov-metric-label"><TrendingUp :size="13" :stroke-width="2" />持仓浮盈</div>
            <div class="ov-metric-value" :class="Number(dashboard.total_profit || 0) >= 0 ? 'up' : 'down'">
              {{ formatMoney(dashboard.total_profit, 2, true) }}
            </div>
            <div class="ov-metric-sub">账本当前仓口径</div>
          </div>
          <div class="ov-metric">
            <div class="ov-metric-label"><Activity :size="13" :stroke-width="2" />当日参考</div>
            <div class="ov-metric-value" :class="todayContrib >= 0 ? 'up' : 'down'">
              {{ formatMoney(todayContrib, 2, true) }}
            </div>
            <div class="ov-metric-sub">盘中粗估，不入账</div>
          </div>
          <div class="ov-metric">
            <div class="ov-metric-label"><Landmark :size="13" :stroke-width="2" />现金 + 存款</div>
            <div class="ov-metric-value">{{ formatMoney(cashAndBank) }}</div>
            <div class="ov-metric-sub">证券现金 {{ formatMoney(dashboard.securities_cash) }}</div>
          </div>
        </div>
      </div>

      <aside class="orbit-card">
        <div class="orbit-head">
          <div class="orbit-title">资产轨道</div>
          <div class="orbit-chip"><Orbit :size="12" :stroke-width="2" />示意动效</div>
        </div>
        <div ref="orbitStageRef" class="orbit-stage">
          <canvas ref="orbitCanvasRef" aria-hidden="true" />
          <div class="orbit-core">
            <div class="orbit-core-label">Total Assets</div>
            <div class="orbit-core-value">{{ formatMoney(dashboard.total_assets) }}</div>
            <div class="orbit-core-sub">节点权重按市值示意</div>
          </div>
        </div>
        <div class="orbit-meta">
          <div class="orbit-meta-box">
            <div class="l">权益仓位</div>
            <div class="v">{{ equityPctText }}</div>
          </div>
          <div class="orbit-meta-box">
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
              <span class="num-cell" :style="{ color: holdingFloatProfit(scope.row) >= 0 ? '#F56C6C' : '#67C23A' }">
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
              <strong>记交易</strong>
              <small>真仓纪律，草稿确认入账</small>
            </span>
          </button>
          <button type="button" class="ov-action" @click="goTab('transactions')">
            <span class="ov-action-ico"><Banknote :size="16" :stroke-width="2" /></span>
            <span>
              <strong>分红草稿</strong>
              <small>半自动入账，先核对</small>
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
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue';
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
  Orbit,
  PenLine,
  Radar,
  RefreshCw,
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
  marketLoading,
  refreshMarket,
  showTransactions,
  formatMoney,
  holdingFloatProfit,
  goTab,
  allocationSummary,
  portfolioExpectedReturn,
} = useAppCtx();

const orbitStageRef = ref(null);
const orbitCanvasRef = ref(null);
let orbitRaf = 0;
let orbitRo = null;
let reducedMotion = false;

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

const equityPctText = computed(() => {
  const n = Number(summary.value.equityRatio || 0);
  return `${n.toFixed(1)}%`;
});

const defensivePctText = computed(() => {
  const n = Number(summary.value.defensiveRatio || 0);
  return `${n.toFixed(1)}%`;
});

const expectedReturnText = computed(() => {
  const raw = portfolioExpectedReturn?.value ?? portfolioExpectedReturn ?? 0;
  const n = Number(raw || 0);
  return `${n.toFixed(2)}%`;
});

const pendingCountText = computed(() => {
  const d = dashboard?.value ?? dashboard ?? {};
  const n = Number(d.pending_count || pendingTransactions?.value?.length || pendingTransactions?.length || 0);
  return `${n} 笔`;
});

const orbitWeights = computed(() => {
  const rows = holdingsPreview.value.slice(0, 7);
  if (!rows.length) return [1, 1, 1, 1, 1, 1, 1];
  const vals = rows.map((r) => Math.max(1, Number(r._mv || 0)));
  while (vals.length < 7) vals.push(Math.max(1, vals[vals.length - 1] || 1));
  return vals.slice(0, 7);
});

async function refreshOverview() {
  if (typeof refreshMarket === 'function') await refreshMarket();
}

function onRowClick(row) {
  if (typeof showTransactions === 'function') showTransactions(row);
}

function onPointerMove(e) {
  const page = e.currentTarget;
  if (!page) return;
  const rect = page.getBoundingClientRect();
  const x = ((e.clientX - rect.left) / Math.max(rect.width, 1)) * 100;
  const y = ((e.clientY - rect.top) / Math.max(rect.height, 1)) * 100;
  page.style.setProperty('--mx', `${x}%`);
  page.style.setProperty('--my', `${y}%`);
}

function resizeOrbit() {
  const canvas = orbitCanvasRef.value;
  const stage = orbitStageRef.value;
  if (!canvas || !stage) return null;
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;
  const rect = stage.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.floor(rect.width * dpr));
  canvas.height = Math.max(1, Math.floor(rect.height * dpr));
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, cw: rect.width, ch: rect.height };
}

function drawOrbitFrame(ts = 0) {
  const sized = resizeOrbit();
  if (!sized) return;
  const { ctx, cw, ch } = sized;
  const weights = orbitWeights.value;
  const maxW = Math.max(...weights, 1);
  const nodes = weights.map((w, i) => ({
    a: (Math.PI * 2 * i) / weights.length,
    r: 58 + (i % 3) * 15 + (w / maxW) * 10,
    s: 0.0032 + i * 0.00055,
    size: 2.4 + (w / maxW) * 1.8,
  }));

  ctx.clearRect(0, 0, cw, ch);
  const cx = cw / 2;
  const cy = ch / 2 + 4;

  for (let i = 0; i < 3; i++) {
    ctx.beginPath();
    ctx.ellipse(cx, cy, 74 + i * 22, 48 + i * 15, -0.32, 0, Math.PI * 2);
    ctx.strokeStyle = `rgba(247,248,248,${0.075 - i * 0.015})`;
    ctx.lineWidth = 1;
    ctx.stroke();
  }

  ctx.beginPath();
  ctx.moveTo(16, ch * 0.72);
  ctx.bezierCurveTo(cw * 0.25, ch * 0.62, cw * 0.45, ch * 0.78, cw * 0.7, ch * 0.42);
  ctx.bezierCurveTo(cw * 0.82, ch * 0.28, cw * 0.9, ch * 0.34, cw - 14, ch * 0.3);
  ctx.strokeStyle = 'rgba(139,138,255,0.35)';
  ctx.lineWidth = 1.6;
  ctx.stroke();

  nodes.forEach((n, i) => {
    const ang = n.a + (reducedMotion ? 0 : ts * n.s);
    const x = cx + Math.cos(ang) * n.r;
    const y = cy + Math.sin(ang) * (n.r * 0.62);
    const color = i % 3 === 0 ? '113,112,255' : i % 3 === 1 ? '87,242,229' : '214,255,63';
    const grad = ctx.createRadialGradient(x, y, 0, x, y, 16);
    grad.addColorStop(0, `rgba(${color},0.9)`);
    grad.addColorStop(1, `rgba(${color},0)`);
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(x, y, 14, 0, Math.PI * 2);
    ctx.fill();
    ctx.beginPath();
    ctx.arc(x, y, n.size, 0, Math.PI * 2);
    ctx.fillStyle = '#fff';
    ctx.fill();
  });
}

function orbitLoop(ts) {
  drawOrbitFrame(ts);
  if (!reducedMotion) orbitRaf = requestAnimationFrame(orbitLoop);
}

function startOrbit() {
  stopOrbit();
  reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  drawOrbitFrame(0);
  if (!reducedMotion) orbitRaf = requestAnimationFrame(orbitLoop);
  if (typeof ResizeObserver !== 'undefined' && orbitStageRef.value) {
    orbitRo = new ResizeObserver(() => drawOrbitFrame(performance.now()));
    orbitRo.observe(orbitStageRef.value);
  }
}

function stopOrbit() {
  if (orbitRaf) cancelAnimationFrame(orbitRaf);
  orbitRaf = 0;
  if (orbitRo) {
    orbitRo.disconnect();
    orbitRo = null;
  }
}

watch(orbitWeights, () => {
  drawOrbitFrame(performance.now());
});

onMounted(async () => {
  refreshOverview();
  await nextTick();
  startOrbit();
});

onUnmounted(() => {
  stopOrbit();
});
</script>

<style scoped>
.overview-page {
  --ov-bg: #08090a;
  --ov-panel: rgba(15, 16, 17, 0.92);
  --ov-border: rgba(255, 255, 255, 0.08);
  --ov-border-strong: rgba(255, 255, 255, 0.14);
  --ov-text: #f7f8f8;
  --ov-text-2: #c7ccd4;
  --ov-text-3: #8a8f98;
  --ov-text-4: #5f646c;
  --ov-accent: #7170ff;
  --ov-accent-soft: rgba(113, 112, 255, 0.14);
  --ov-up: #f56c6c;
  --ov-down: #67c23a;
  --ov-warn: #f59e0b;
  --ov-ok: #10b981;
  --mx: 18%;
  --my: 8%;
  margin: -4px -6px 0;
  padding: 10px 8px 18px;
  border-radius: 16px;
  color: var(--ov-text);
  background:
    radial-gradient(900px 480px at var(--mx) var(--my), rgba(113, 112, 255, 0.14), transparent 52%),
    radial-gradient(700px 420px at 88% 8%, rgba(87, 242, 229, 0.07), transparent 48%),
    radial-gradient(760px 420px at 70% 100%, rgba(214, 255, 63, 0.05), transparent 50%),
    linear-gradient(180deg, #0b0c0e 0%, var(--ov-bg) 100%);
  font-feature-settings: "cv01", "ss03";
}

.overview-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 14px;
  flex-wrap: wrap;
  margin-bottom: 18px;
}
.overview-kicker {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--ov-text-3);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.overview-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--ov-ok);
  box-shadow: 0 0 0 4px rgba(16, 185, 129, 0.15);
}
.overview-title {
  margin: 10px 0 0;
  font-size: clamp(28px, 4vw, 40px);
  font-weight: 600;
  letter-spacing: -0.04em;
  line-height: 1.05;
  color: var(--ov-text);
}
.overview-subtitle {
  margin-top: 8px;
  font-size: 13px;
  color: var(--ov-text-3);
  line-height: 1.55;
  max-width: 520px;
}
.overview-mix-tag {
  margin-top: 12px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid rgba(214, 255, 63, 0.22);
  background: rgba(214, 255, 63, 0.08);
  color: #e8ff9a;
  font-size: 11px;
  font-weight: 600;
}
.overview-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
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
  box-shadow: 0 8px 24px rgba(113, 112, 255, 0.28);
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
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.035), rgba(255, 255, 255, 0.015));
  border: 1px solid var(--ov-border);
  min-height: 108px;
}
.ov-metric.main {
  grid-column: 1 / -1;
  background:
    linear-gradient(135deg, rgba(113, 112, 255, 0.12), transparent 40%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.04), rgba(255, 255, 255, 0.015));
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
  font-size: 28px;
  font-weight: 500;
  letter-spacing: -0.03em;
  font-variant-numeric: tabular-nums;
}
.ov-metric.main .ov-metric-value { font-size: clamp(30px, 4vw, 40px); }
.ov-metric-sub { margin-top: 6px; font-size: 12px; color: var(--ov-text-4); }
.up { color: var(--ov-up); }
.down { color: var(--ov-down); }

.orbit-card {
  border: 1px solid var(--ov-border);
  background: var(--ov-panel);
  border-radius: 16px;
  padding: 14px;
  min-height: 320px;
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
}
.orbit-card::before {
  content: "";
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 30% 40%, rgba(113, 112, 255, 0.16), transparent 34%),
    radial-gradient(circle at 72% 28%, rgba(87, 242, 229, 0.1), transparent 28%),
    radial-gradient(circle at 55% 78%, rgba(214, 255, 63, 0.08), transparent 30%);
  pointer-events: none;
}
.orbit-head,
.orbit-stage,
.orbit-meta { position: relative; z-index: 1; }
.orbit-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.orbit-title { font-size: 13px; font-weight: 600; color: var(--ov-text-2); }
.orbit-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 26px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid var(--ov-border);
  background: rgba(255, 255, 255, 0.03);
  color: var(--ov-text-3);
  font-size: 11px;
  font-weight: 600;
}
.orbit-stage {
  position: relative;
  flex: 1;
  min-height: 210px;
  border-radius: 14px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.05);
  background: rgba(0, 0, 0, 0.22);
}
.orbit-stage canvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}
.orbit-core {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  text-align: center;
  pointer-events: none;
}
.orbit-core-label {
  font-family: "SF Mono", "Menlo", "Consolas", ui-monospace, monospace;
  font-size: 10px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: rgba(247, 248, 248, 0.48);
}
.orbit-core-value {
  margin-top: 8px;
  font-family: "SF Mono", "Menlo", "Consolas", ui-monospace, monospace;
  font-size: clamp(24px, 2.6vw, 32px);
  font-weight: 500;
  letter-spacing: -0.04em;
  font-variant-numeric: tabular-nums;
}
.orbit-core-sub {
  margin-top: 8px;
  font-size: 12px;
  color: rgba(247, 248, 248, 0.48);
}
.orbit-meta {
  margin-top: 12px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.orbit-meta-box {
  padding: 12px;
  border-radius: 10px;
  background: rgba(0, 0, 0, 0.28);
  border: 1px solid var(--ov-border);
}
.orbit-meta-box .l { font-size: 11px; color: var(--ov-text-4); }
.orbit-meta-box .v {
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
  background: rgba(255, 255, 255, 0.02);
}
.ov-status-ico {
  width: 32px;
  height: 32px;
  border-radius: 9px;
  display: grid;
  place-items: center;
  background: rgba(255, 255, 255, 0.04);
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
.ov-status h4 {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
}
.ov-status p {
  margin: 3px 0 0;
  font-size: 12px;
  color: var(--ov-text-4);
}
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
  color: #f6d9a6;
  font-size: 13px;
}
.ov-link {
  border: 0;
  background: transparent;
  color: #ffd089;
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
  --el-table-header-bg-color: rgba(255, 255, 255, 0.02);
  --el-table-row-hover-bg-color: rgba(255, 255, 255, 0.04);
  --el-table-border-color: rgba(255, 255, 255, 0.06);
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
  background: rgba(255, 255, 255, 0.02);
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease, transform 0.15s ease;
}
.ov-action:hover {
  background: rgba(255, 255, 255, 0.045);
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
  color: #a5a4ff;
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
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
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
}
@media (prefers-reduced-motion: reduce) {
  .ov-btn .spin { animation: none; }
  .ov-action { transition: none; }
}
</style>
