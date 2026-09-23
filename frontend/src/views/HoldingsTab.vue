<template>
  <PageShell>
    <template #actions>
      <el-button type="warning" plain :loading="trailingSyncing" @click="onSyncTrailingReturns">
        同步近一年收益率
      </el-button>
    </template>
    <HomeDashboard />
    <el-alert
      title="近一年标的收益率 = 标的自身过去一年价格/净值涨跌；不是你的账户实际持有收益。持仓浮盈只看当前仓；全周期盈亏含历史买卖，接近券商累计盈亏。"
      type="info"
      show-icon
      :closable="false"
      class="holdings-toolbar-alert"
      style="margin-bottom: 12px;"
    />
    <div v-if="!holdings || !holdings.length" class="empty-hint" style="margin-bottom: 12px;">
      <strong>当前没有持仓</strong>
      <span>去交易页录入买入，或先同步价格核对。空仓时这里保持干净。</span>
      <el-button size="small" type="primary" plain @click="goTab('transactions')">去交易</el-button>
    </div>
    <el-table v-else :data="holdings" stripe size="small" class="holdings-table table-clickable" style="width: 100%" @row-click="showTransactions" aria-label="持仓明细">
      <el-table-column label="标的" min-width="148" fixed="left" align="left" header-align="left">
        <template #default="scope">
          <div class="asset-cell">
            <div class="asset-cell-name">{{ scope.row.name }}</div>
            <div class="asset-cell-code">{{ scope.row.code }} · {{ scope.row.category || '未分类' }}</div>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="数量" min-width="96" align="right" header-align="right">
        <template #default="scope"><span class="num-cell">{{ Number(scope.row.quantity || 0).toLocaleString('zh-CN') }}</span></template>
      </el-table-column>
      <el-table-column label="普通成本" min-width="96" align="right" header-align="right">
        <template #header>
          <el-tooltip content="普通成本：剩余持仓按平均成本结转后的买入成本，不扣历史卖出回款。" placement="top">
            <span>普通成本</span>
          </el-tooltip>
        </template>
        <template #default="scope"><span class="num-cell">{{ formatMoney(scope.row.avg_cost, 4) }}</span></template>
      </el-table-column>
      <el-table-column label="摊薄成本" min-width="96" align="right" header-align="right">
        <template #header>
          <el-tooltip content="券商口径：累计买入成本 - 卖出回款 - 累计分红，再除以剩余持仓；可能为负。" placement="top">
            <span>摊薄成本</span>
          </el-tooltip>
        </template>
        <template #default="scope">
          <span class="num-cell" :class="Number(scope.row.diluted_cost || 0) < 0 ? 'num-down' : ''">{{ formatMoney(scope.row.diluted_cost, 4) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="最新价" min-width="118" align="right" header-align="right">
        <template #default="scope">
          <span class="num-cell">{{ formatMoney(scope.row.last_price, 4) }}</span>
          <el-tooltip v-if="isManualPrice(scope.row.code)" content="价格是手动填的，还没被真实行情覆盖" placement="top">
            <el-tag size="small" type="warning" class="manual-price-tag">人工价</el-tag>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="市值" min-width="110" align="right" header-align="right">
        <template #default="scope"><span class="num-cell">{{ formatMoney(scope.row.quantity * scope.row.last_price) }}</span></template>
      </el-table-column>
      <el-table-column label="持仓浮盈" min-width="108" align="right" header-align="right">
        <template #header>
          <el-tooltip content="持仓浮盈 = (最新价 − 普通成本) × 数量 + 累计分红；只看当前剩余持仓，不含历史卖出已实现盈亏。" placement="top">
            <span>持仓浮盈</span>
          </el-tooltip>
        </template>
        <template #default="scope">
          <span class="num-cell" :class="(holdingFloatProfit(scope.row) >= 0 ) ? 'num-up' : 'num-down'">
            {{ formatMoney(holdingFloatProfit(scope.row), 2, true) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="全周期盈亏" min-width="108" align="right" header-align="right">
        <template #header>
          <el-tooltip content="全周期盈亏 ≈ (最新价 − 摊薄成本) × 数量；含历史买卖已实现与分红摊薄，接近券商「累计盈亏」。" placement="top">
            <span>全周期盈亏</span>
          </el-tooltip>
        </template>
        <template #default="scope">
          <span class="num-cell" :class="(holdingLifetimeProfit(scope.row) >= 0 ) ? 'num-up' : 'num-down'">
            {{ formatMoney(holdingLifetimeProfit(scope.row), 2, true) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="浮盈率" min-width="84" align="right" header-align="right">
        <template #header>
          <el-tooltip content="持仓浮盈 / (普通成本 × 数量)" placement="top">
            <span>浮盈率</span>
          </el-tooltip>
        </template>
        <template #default="scope">
          <span class="num-cell" :class="(holdingFloatProfitRate(scope.row) ?? 0) >= 0 ? 'num-up' : 'num-down'">
            {{ holdingFloatProfitRate(scope.row) === null ? '—' : formatPercent(holdingFloatProfitRate(scope.row)) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="全周期收益率" min-width="100" align="right" header-align="right">
        <template #header>
          <el-tooltip content="全周期盈亏 / (摊薄成本 × 数量)；净投入≤0 时不展示。" placement="top">
            <span>全周期收益率</span>
          </el-tooltip>
        </template>
        <template #default="scope">
          <span class="num-cell" :class="(holdingLifetimeProfitRate(scope.row) ?? 0) >= 0 ? 'num-up' : 'num-down'">
            {{ holdingLifetimeProfitRate(scope.row) === null ? '—' : formatPercent(holdingLifetimeProfitRate(scope.row)) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="预计年化" width="88" align="right" header-align="right">
        <template #default="scope">
          <el-button link class="num-cell" title="点击修改预期年化收益" @click.stop="openExpectedReturnDialog(scope.row)">{{ scope.row.expected_return == null ? '—' : formatPercent(scope.row.expected_return, 1) }}</el-button>
        </template>
      </el-table-column>
      <el-table-column label="近一年" width="88" align="right" header-align="right">
        <template #header>
          <el-tooltip content="标的自身过去一年价格/净值回溯收益，不等于你的账户实际持有收益。" placement="top">
            <span>近一年</span>
          </el-tooltip>
        </template>
        <template #default="scope">
          <el-tooltip :content="scope.row.trailing_return_1y_source || '暂无数据，请同步近一年收益率'" placement="top">
            <span class="num-cell" :class="(Number(scope.row.trailing_return_1y || 0) >= 0 ) ? 'num-up' : 'num-down'">
              {{ formatPercent(scope.row.trailing_return_1y) }}
            </span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="130" align="center" header-align="center" fixed="right">
        <template #default="scope">
          <el-button type="warning" link @click.stop="openHoldingCorrectionDialog(scope.row)">校正</el-button>
          <el-button type="primary" link :loading="priceEditing" @click.stop="onChangePrice(scope.row)">改价</el-button>
        </template>
      </el-table-column>
    </el-table>

  </PageShell>
</template>

<script setup>
import { computed, ref } from 'vue';
import PageShell from '../components/PageShell.vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import api from '../api/index.js';
import { useAppCtx } from '../composables/useAppCtx.js';
import HomeDashboard from '../components/HomeDashboard.vue';

const {
  holdings,
  dashboard,
  showTransactions,
  openExpectedReturnDialog,
  openHoldingCorrectionDialog,
  formatMoney,
  formatPercent,
  holdingFloatProfit,
  holdingLifetimeProfit,
  holdingFloatProfitRate,
  holdingLifetimeProfitRate,
  trailingSyncing,
  syncTrailingReturns,
  fetchData,
  goTab,
} = useAppCtx();

// 同步近一年收益率走 POST /sync-trailing-returns：模块里的 trailingSyncing 一开头就置位，
// 这里补一个入口判断，避免同一 tick 连点发两次请求（同时弹出两个全屏 loading）。
function onSyncTrailingReturns() {
  if (trailingSyncing.value) return;
  return syncTrailingReturns();
}

// 手动改价：PUT /holdings/{code}/price。数据源全挂时人工兜底 —— 后端会把
// 「价格同步时间」一起刷成现在，所以快照闸门会放行。priceEditing 用来挡连点。
const priceEditing = ref(false);

async function onChangePrice(row) {
  if (priceEditing.value) return;
  priceEditing.value = true;
  try {
    const { value } = await ElMessageBox.prompt('填写最新价（元）', '手动改价', {
      inputPattern: /^\s*\d+(\.\d+)?\s*$/,
      inputErrorMessage: '请输入正数',
    });
    const price = Number(value);
    await api.setHoldingPrice(row.code, price);
    ElMessage.success(`已更新为 ${price}`);
    await fetchData();
  } catch (e) {
    // 用户取消不算失败，其余（400 校验 / 404 / 网络）都要把后端 detail 透出来
    if (e === 'cancel' || e === 'close') return;
    ElMessage.error(e?.response?.data?.detail || e?.message);
  } finally {
    priceEditing.value = false;
  }
}

// 人工价徽标：GET /dashboard 的 manual_price_codes 是当前人工价的代码数组
const manualPriceCodes = computed(() => {
  const dash = dashboard?.value ?? dashboard;
  return Array.isArray(dash?.manual_price_codes) ? dash.manual_price_codes : [];
});

function isManualPrice(code) {
  return manualPriceCodes.value.includes(code);
}
</script>

<style scoped>
.holdings-toolbar {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin: 14px 0 12px;
  flex-wrap: wrap;
}
.holdings-toolbar-alert {
  flex: 1;
  min-width: 240px;
  margin: 0 !important;
}
.manual-price-tag {
  margin-left: 6px;
}
</style>
