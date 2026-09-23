<template>
  <!--
    本组件由「收益与快照」页（PerformanceTab.vue）渲染。
    原「资产快照」页已在分析组收敛时并入该页：PageShell 外壳去掉（标题交给宿主的页头），
    资产走势折线图按决策 D4 删除（与「每日收益」柱状图同源，重复）；只保留资产结构饼图。
  -->
  <div class="snapshot-panel">
    <div class="snapshot-toolbar">
      <el-date-picker
        v-model="snapshotRange"
        type="daterange"
        range-separator="至"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        value-format="YYYY-MM-DD"
        @change="fetchSnapshots"
        style="width: 300px"
      ></el-date-picker>
      <el-button type="primary" @click="onCreateSnapshot" :loading="snapshotLoading">记录/更新今日快照</el-button>
      <el-button @click="exportSnapshots">导出快照</el-button>
      <el-button type="warning" plain :loading="compacting" @click="onCompactSnapshots">压缩历史快照</el-button>
    </div>

    <el-alert
      v-if="snapshotSummary?.day_over_day_anomaly?.text"
      :title="snapshotSummary.day_over_day_anomaly.text"
      type="warning"
      show-icon
      :closable="false"
      style="margin-bottom: 16px;"
    ></el-alert>
    <el-alert
      title="重复点击今天的快照会更新当天记录，不再因为已存在而丢掉最新价格/现金数据。"
      type="info"
      show-icon
      :closable="false"
      style="margin-bottom: 16px;"
    ></el-alert>

    <el-card shadow="never" header="人工对账（实盘核对）" style="margin-bottom: 18px;">
      <div class="reconcile-grid">
        <div v-if="reconcileData" class="reconcile-result">
          <div class="reconcile-line">
            <span class="reconcile-label">实盘总资产</span>
            <span class="num-cell">{{ formatMoney(reconcileData.manual_total_assets) }}</span>
          </div>
          <div v-if="reconcileData.calculated_total_assets != null" class="reconcile-line">
            <span class="reconcile-label">当日计算快照</span>
            <span class="num-cell">{{ formatMoney(reconcileData.calculated_total_assets) }}</span>
          </div>
          <div v-if="reconcileData.gap != null" class="reconcile-line">
            <span class="reconcile-label">误差</span>
            <span class="num-cell" :class="Math.abs(reconcileData.gap) < 50 ? 'num-up' : 'num-down'">
              {{ formatMoney(reconcileData.gap, 2, true) }}（{{ reconcileData.gap_pct }}%）
            </span>
          </div>
          <div v-if="reconcileData.date" class="reconcile-line reconcile-muted">最近记录：{{ reconcileData.date }}</div>
        </div>
        <div v-else class="reconcile-empty">还没有人工对账记录。每周对照券商/银行实际余额录一次，用误差锁死账本。</div>
      </div>
      <el-form :model="reconcileForm" label-width="110px" style="margin-top: 12px;">
        <div class="reconcile-form-row">
          <el-form-item label="日期">
            <el-date-picker v-model="reconcileForm.date" type="date" value-format="YYYY-MM-DD" style="width: 100%"></el-date-picker>
          </el-form-item>
          <el-form-item label="实盘总资产">
            <el-input-number v-model="reconcileForm.amount" :precision="2" :controls="false" class="wide-number-input" placeholder="券商+银行实际总额"></el-input-number>
          </el-form-item>
          <el-form-item label="备注">
            <el-input v-model="reconcileForm.note" placeholder="可选" clearable></el-input>
          </el-form-item>
        </div>
        <el-form-item>
          <el-button type="warning" plain :loading="reconcileSaving" @click="saveReconcile">保存实盘对账</el-button>
          <span style="color: var(--app-muted); font-size: 12px;">留最近一次，重复录同一天会覆盖。</span>
        </el-form-item>
      </el-form>
    </el-card>

    <div class="ledger-metrics cols-4">
      <MetricCard
        v-for="(m, idx) in snapshotMetrics"
        :key="m.key"
        :label="m.label"
        :value="m.value"
        :color="m.color"
        :main="idx === 0"
      />
    </div>

    <div class="snapshot-insights" v-if="snapshotInsights.length">
      <div class="snapshot-pill is-blue">
        <div class="snapshot-pill-label">最新快照锚点</div>
        <div class="snapshot-pill-main">{{ snapshotInsights[0]?.main || '—' }}</div>
        <div class="snapshot-pill-sub">{{ snapshotInsights[0]?.sub || '暂无快照数据' }}</div>
      </div>
      <div class="snapshot-pill is-orange">
        <div class="snapshot-pill-label">区间波动焦点</div>
        <div class="snapshot-pill-main">{{ snapshotInsights[1]?.main || '—' }}</div>
        <div class="snapshot-pill-sub">{{ snapshotInsights[1]?.sub || '至少需要两条快照' }}</div>
      </div>
      <div class="snapshot-pill is-green">
        <div class="snapshot-pill-label">当前防守缓冲</div>
        <div class="snapshot-pill-main">{{ snapshotInsights[2]?.main || '—' }}</div>
        <div class="snapshot-pill-sub">{{ snapshotInsights[2]?.sub || '暂无数据' }}</div>
      </div>
    </div>

    <el-card shadow="never" header="当前资产结构" style="margin-bottom: 18px;">
      <div id="snapshotStructureChart" class="snapshot-chart"></div>
    </el-card>

    <el-card shadow="never" header="区间变化明细" style="margin-bottom: 18px;">
      <el-table :data="snapshotChangeRows" stripe size="small" class="snapshot-table" style="width: 100%" empty-text="至少需要两条快照，或选择包含两条以上记录的日期范围" aria-label="区间变化明细">
        <el-table-column prop="label" label="项目" width="120" align="left" header-align="left"></el-table-column>
        <el-table-column label="期初" min-width="120" align="right" header-align="right">
          <template #default="scope"><span class="num-cell">{{ formatMoney(scope.row.start) }}</span></template>
        </el-table-column>
        <el-table-column label="期末" min-width="120" align="right" header-align="right">
          <template #default="scope"><span class="num-cell">{{ formatMoney(scope.row.end) }}</span></template>
        </el-table-column>
        <el-table-column label="变化额" min-width="120" align="right" header-align="right">
          <template #default="scope">
            <span class="num-cell" :class="(scope.row.change >= 0 ) ? 'num-up' : 'num-down'">{{ formatMoney(scope.row.change, 2, true) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变化率" width="100" align="right" header-align="right">
          <template #default="scope">
            <span class="num-cell" :class="(scope.row.change >= 0 ) ? 'num-up' : 'num-down'">{{ scope.row.change_pct === null ? '—' : formatPercent(scope.row.change_pct, 2) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" header="快照历史记录">
      <el-table :data="snapshots" stripe size="small" class="snapshot-table" style="width: 100%" empty-text="暂无快照记录" aria-label="快照历史记录">
        <el-table-column prop="date" label="日期" width="108" sortable align="left" header-align="left" fixed="left"></el-table-column>
        <el-table-column label="总资产" min-width="120" align="right" header-align="right">
          <template #default="scope"><span class="num-cell">{{ formatMoney(scope.row.total_assets) }}</span></template>
        </el-table-column>
        <el-table-column label="投资市值" min-width="120" align="right" header-align="right">
          <template #default="scope"><span class="num-cell">{{ formatMoney(scope.row.total_market_value) }}</span></template>
        </el-table-column>
        <el-table-column label="银行存款" min-width="110" align="right" header-align="right">
          <template #default="scope"><span class="num-cell">{{ formatMoney(scope.row.bank_balance) }}</span></template>
        </el-table-column>
        <el-table-column label="证券现金" min-width="100" align="right" header-align="right">
          <template #default="scope"><span class="num-cell">{{ formatMoney(scope.row.securities_cash) }}</span></template>
        </el-table-column>
        <el-table-column label="申购在途" min-width="100" align="right" header-align="right">
          <template #default="scope"><span class="num-cell">{{ formatMoney(scope.row.pending_purchase || 0) }}</span></template>
        </el-table-column>
        <el-table-column label="持仓浮盈" min-width="110" align="right" header-align="right">
          <template #header>
            <el-tooltip content="快照时点的投资账户持仓浮盈（普通成本口径），不含历史已实现。" placement="top">
              <span>持仓浮盈</span>
            </el-tooltip>
          </template>
          <template #default="scope">
            <span class="num-cell" :class="(scope.row.total_profit >= 0 ) ? 'num-up' : 'num-down'">
              {{ formatMoney(scope.row.total_profit, 2, true) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="全周期盈亏" min-width="110" align="right" header-align="right">
          <template #header>
            <el-tooltip content="快照时点的全周期盈亏（摊薄成本口径，接近券商累计）。旧快照可能为 0。" placement="top">
              <span>全周期盈亏</span>
            </el-tooltip>
          </template>
          <template #default="scope">
            <span class="num-cell" :class="((scope.row.lifetime_profit || 0) >= 0 ) ? 'num-up' : 'num-down'">
              {{ formatMoney(scope.row.lifetime_profit || 0, 2, true) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="投资占比" width="88" align="right" header-align="right">
          <template #default="scope"><span class="num-cell">{{ pct(scope.row.total_market_value, scope.row.total_assets) }}</span></template>
        </el-table-column>
        <el-table-column label="现金+存款+在途" min-width="128" align="right" header-align="right">
          <template #default="scope"><span class="num-cell">{{ formatMoney((scope.row.bank_balance || 0) + (scope.row.securities_cash || 0) + (scope.row.pending_purchase || 0)) }}</span></template>
        </el-table-column>
        <el-table-column prop="holdings_count" label="持仓" width="68" align="right" header-align="right"></el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import MetricCard from '../components/MetricCard.vue';
import { ref } from 'vue';
import { ElMessageBox } from 'element-plus';
import { useAppCtx } from '../composables/useAppCtx.js';
import { formatPercent } from '../utils/index.js';

// 快照/对账相关的 ctx 键在真实 App 根 provide 里都有；这里仍然给出空值兜底，
// 因为宿主 PerformanceTab 的轻量测试 ctx 可能不带这些键，缺一个就会在渲染期抛错。
const {
  snapshots = ref([]),
  snapshotRange = ref([]),
  snapshotMetrics = ref([]),
  snapshotChangeRows = ref([]),
  snapshotInsights = ref([]),
  snapshotSummary = ref(null),
  snapshotLoading,
  reconcileData,
  reconcileForm = ref({ date: '', amount: 0, note: '' }),
  reconcileSaving,
  createSnapshot,
  fetchSnapshots,
  exportSnapshots,
  compactSnapshots,
  saveReconcile,
  formatMoney,
  pct,
} = useAppCtx();

// 写操作防连点。快照用模块里现成的 snapshotLoading（模块内的 createSnapshot 会把它置位），
// 压缩快照模块里没有标志，本组件用一个本地 ref。
const compacting = ref(false);

/**
 * 记录/更新今日快照。
 *
 * 后端在「最新价不是今天的」时候会返回 409（模块会把 409 继续往外抛，
 * 不会自己吞掉），这里必须接住：否则就是一个 unhandled rejection，
 * 用户只会看到「点了没反应」。
 */
async function onCreateSnapshot() {
  if (snapshotLoading?.value) return;
  const post = async (force) => {
    try {
      await createSnapshot(force);
      return true;
    } catch (e) {
      if (e?.response?.status !== 409) throw e;
      try {
        await ElMessageBox.confirm(
          e.response.data?.detail || '最新价不是今天的，现在记录会让这天的收益失真。',
          '价格未更新',
          { confirmButtonText: '强制记录', cancelButtonText: '取消', type: 'warning' },
        );
      } catch {
        return false; // 用户取消
      }
      await createSnapshot(true);
      return true;
    }
  };
  await post(false).catch((err) => console.error('createSnapshot', err));
}

async function onCompactSnapshots() {
  if (compacting.value) return;
  compacting.value = true;
  try {
    await compactSnapshots();
  } finally {
    compacting.value = false;
  }
}
</script>

<style scoped>
.snapshot-panel { display: block; }
.reconcile-form-row { display: flex; gap: 20px; flex-wrap: wrap; }
.reconcile-form-row > :deep(.el-form-item) { flex: 1 1 220px; min-width: 0; margin-bottom: 18px; }
/* 原 PageShell 的 #actions 槽位：日期范围 + 三个写操作按钮 */
.snapshot-toolbar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}
</style>
