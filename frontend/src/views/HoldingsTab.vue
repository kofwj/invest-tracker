<template>
  <div class="holdings-tab">
    <HomeDashboard />
    <div class="holdings-toolbar">
      <el-alert
        title="近一年标的收益率 = 标的自身价格/净值涨跌，不是你账户实赚。持仓浮盈只看当前仓；全周期含历史买卖。"
        type="info"
        show-icon
        :closable="false"
        class="holdings-toolbar-alert"
      />
      <div class="holdings-toolbar-actions">
        <el-dropdown trigger="click" :hide-on-click="false">
          <el-button size="small">显示列</el-button>
          <template #dropdown>
            <el-dropdown-menu class="col-toggle-menu">
              <el-dropdown-item v-for="col in allToggleColumns" :key="col.key">
                <el-checkbox
                  :model-value="isVisible(col.key)"
                  @change="(v) => toggle(col.key, v)"
                >{{ col.label }}</el-checkbox>
              </el-dropdown-item>
              <el-dropdown-item divided @click="reset">恢复默认</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button type="warning" plain size="small" :loading="trailingSyncing" @click="syncTrailingReturns">
          同步近一年收益率
        </el-button>
      </div>
    </div>

    <!-- 桌面表 -->
    <div class="desktop-only table-scroll">
      <el-table
        :data="sortedHoldings"
        stripe
        size="small"
        class="holdings-table data-table"
        style="width: 100%"
        :default-sort="{ prop: 'market_value', order: 'descending' }"
        @row-click="showTransactions"
        @sort-change="onSortChange"
      >
        <el-table-column label="标的" min-width="148" fixed="left" align="left" header-align="left">
          <template #default="{ row }">
            <div class="asset-cell">
              <div class="asset-name">{{ row.name }}</div>
              <div class="asset-code">{{ row.code }}</div>
            </div>
          </template>
        </el-table-column>

        <el-table-column
          v-if="isVisible('category')"
          prop="category"
          label="分类"
          width="88"
          align="left"
          header-align="left"
        >
          <template #default="{ row }">
            <el-tag size="small" effect="plain" :type="categoryTagType(row.category)">{{ row.category || '—' }}</el-tag>
          </template>
        </el-table-column>

        <el-table-column
          v-if="isVisible('quantity')"
          prop="quantity"
          label="数量"
          min-width="96"
          align="right"
          header-align="right"
          sortable="custom"
        >
          <template #default="{ row }"><span class="num-cell">{{ formatQty(row.quantity) }}</span></template>
        </el-table-column>

        <el-table-column
          v-if="isVisible('avg_cost')"
          label="成本"
          min-width="92"
          align="right"
          header-align="right"
        >
          <template #header>
            <el-tooltip content="普通成本：剩余持仓均价，不扣历史卖出回款。" placement="top">
              <span>成本</span>
            </el-tooltip>
          </template>
          <template #default="{ row }"><span class="num-cell">{{ formatMoney(row.avg_cost, 4) }}</span></template>
        </el-table-column>

        <el-table-column
          v-if="isVisible('diluted_cost')"
          label="摊薄成本"
          min-width="96"
          align="right"
          header-align="right"
        >
          <template #header>
            <el-tooltip content="券商口径：累计买入 − 卖出回款 − 分红，再除以剩余数量；可能为负。" placement="top">
              <span>摊薄成本</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="num-cell" :style="{ color: Number(row.diluted_cost || 0) < 0 ? '#67C23A' : '' }">
              {{ formatMoney(row.diluted_cost, 4) }}
            </span>
          </template>
        </el-table-column>

        <el-table-column
          v-if="isVisible('last_price')"
          label="现价"
          min-width="88"
          align="right"
          header-align="right"
        >
          <template #default="{ row }"><span class="num-cell">{{ formatMoney(row.last_price, 4) }}</span></template>
        </el-table-column>

        <el-table-column
          v-if="isVisible('market_value')"
          prop="market_value"
          label="市值"
          min-width="110"
          align="right"
          header-align="right"
          sortable="custom"
        >
          <template #default="{ row }"><span class="num-cell">{{ formatMoney(row.quantity * row.last_price) }}</span></template>
        </el-table-column>

        <el-table-column
          v-if="isVisible('float_profit')"
          prop="float_profit"
          label="持仓浮盈"
          min-width="108"
          align="right"
          header-align="right"
          sortable="custom"
        >
          <template #header>
            <el-tooltip content="(现价 − 成本) × 数量 + 累计分红；只看当前仓。" placement="top">
              <span>持仓浮盈</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="num-cell" :style="{ color: pnlColor(holdingFloatProfit(row)) }">
              {{ formatMoney(holdingFloatProfit(row), 2, true) }}
            </span>
          </template>
        </el-table-column>

        <el-table-column
          v-if="isVisible('float_rate')"
          prop="float_rate"
          label="浮盈率"
          min-width="84"
          align="right"
          header-align="right"
          sortable="custom"
        >
          <template #default="{ row }">
            <span class="num-cell" :style="{ color: pnlColor(holdingFloatProfitRate(row) ?? 0) }">
              {{ holdingFloatProfitRate(row) === null ? '—' : formatPercent(holdingFloatProfitRate(row)) }}
            </span>
          </template>
        </el-table-column>

        <el-table-column
          v-if="isVisible('lifetime_profit')"
          prop="lifetime_profit"
          label="全周期"
          min-width="108"
          align="right"
          header-align="right"
          sortable="custom"
        >
          <template #header>
            <el-tooltip content="含历史买卖与分红摊薄，接近券商累计盈亏。" placement="top">
              <span>全周期</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="num-cell" :style="{ color: pnlColor(holdingLifetimeProfit(row)) }">
              {{ formatMoney(holdingLifetimeProfit(row), 2, true) }}
            </span>
          </template>
        </el-table-column>

        <el-table-column
          v-if="isVisible('lifetime_rate')"
          label="全周期率"
          min-width="92"
          align="right"
          header-align="right"
        >
          <template #default="{ row }">
            <span class="num-cell" :style="{ color: pnlColor(holdingLifetimeProfitRate(row) ?? 0) }">
              {{ holdingLifetimeProfitRate(row) === null ? '—' : formatPercent(holdingLifetimeProfitRate(row)) }}
            </span>
          </template>
        </el-table-column>

        <el-table-column
          v-if="isVisible('expected_return')"
          label="预计年化"
          width="92"
          align="right"
          header-align="right"
        >
          <template #default="{ row }">
            <span class="num-cell">{{ row.expected_return == null ? '—' : Number(row.expected_return).toFixed(1) + '%' }}</span>
          </template>
        </el-table-column>

        <el-table-column
          v-if="isVisible('trailing_1y')"
          label="近一年"
          width="92"
          align="right"
          header-align="right"
        >
          <template #header>
            <el-tooltip content="标的自身过去一年价格/净值回溯，不等于账户实赚。" placement="top">
              <span>近一年</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip :content="row.trailing_return_1y_source || '暂无数据，请同步近一年收益率'" placement="top">
              <span class="num-cell" :style="{ color: pnlColor(row.trailing_return_1y) }">
                {{ formatPercent(row.trailing_return_1y) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="72" align="center" header-align="center" fixed="right">
          <template #default="{ row }">
            <div @click.stop>
              <el-dropdown trigger="click">
                <el-button type="primary" link size="small">更多</el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item @click="openExpectedReturnDialog(row)">设预计年化</el-dropdown-item>
                    <el-dropdown-item @click="openHoldingCorrectionDialog(row)">校正持仓</el-dropdown-item>
                    <el-dropdown-item @click="openHoldingCorrectionHistory(row)">校正记录</el-dropdown-item>
                    <el-dropdown-item divided @click="openLocalUzi(row)">UZI 分析</el-dropdown-item>
                    <el-dropdown-item @click="showTransactions(row)">看交易</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 手机卡片 -->
    <div class="mobile-only holdings-cards">
      <div
        v-for="row in sortedHoldings"
        :key="row.code"
        class="holding-card"
        @click="showTransactions(row)"
      >
        <div class="holding-card-head">
          <div>
            <div class="asset-name">{{ row.name }}</div>
            <div class="asset-code">{{ row.code }} · {{ row.category || '未分类' }}</div>
          </div>
          <div class="holding-card-mv num-cell">{{ formatMoney(row.quantity * row.last_price) }}</div>
        </div>
        <div class="holding-card-grid">
          <div>
            <div class="meta-label">数量</div>
            <div class="num-cell">{{ formatQty(row.quantity) }}</div>
          </div>
          <div>
            <div class="meta-label">成本 / 现价</div>
            <div class="num-cell">{{ formatMoney(row.avg_cost, 4) }} / {{ formatMoney(row.last_price, 4) }}</div>
          </div>
          <div>
            <div class="meta-label">持仓浮盈</div>
            <div class="num-cell" :style="{ color: pnlColor(holdingFloatProfit(row)) }">
              {{ formatMoney(holdingFloatProfit(row), 2, true) }}
              <span class="meta-sub">{{ holdingFloatProfitRate(row) === null ? '' : formatPercent(holdingFloatProfitRate(row)) }}</span>
            </div>
          </div>
          <div v-if="isVisible('lifetime_profit')">
            <div class="meta-label">全周期</div>
            <div class="num-cell" :style="{ color: pnlColor(holdingLifetimeProfit(row)) }">
              {{ formatMoney(holdingLifetimeProfit(row), 2, true) }}
            </div>
          </div>
        </div>
        <div class="holding-card-ops" @click.stop>
          <el-button size="small" link type="primary" @click="openHoldingCorrectionDialog(row)">校正</el-button>
          <el-button size="small" link type="success" @click="openLocalUzi(row)">UZI</el-button>
          <el-button size="small" link @click="showTransactions(row)">交易</el-button>
        </div>
      </div>
      <div v-if="!sortedHoldings.length" class="empty-cards">暂无持仓</div>
    </div>

    <!-- UZI 弹窗 -->
    <el-dialog
      v-model="uziDialog.visible"
      title="UZI 深度分析提示"
      width="860px"
      top="6vh"
      append-to-body
      destroy-on-close
    >
      <div v-if="uziDialog.row">
        <el-alert
          title="只读分析：不改持仓、不下单、不自动入账。复制提示词后，在本机 Hermes 粘贴执行 UZI-Skill。"
          type="warning"
          show-icon
          :closable="false"
          style="margin-bottom:12px;"
        />

        <div style="margin-bottom:10px; color:#606266;">
          <strong>{{ uziDialog.row.name }}</strong> ({{ uziDialog.row.code }})
          <span style="margin-left:12px;">深度：</span>
          <el-radio-group v-model="uziDialog.depth" size="small" style="margin-left:6px;" @change="rebuildUziPrompt">
            <el-radio-button value="lite">lite</el-radio-button>
            <el-radio-button value="medium">medium（推荐）</el-radio-button>
            <el-radio-button value="deep">deep</el-radio-button>
          </el-radio-group>
        </div>

        <div style="margin-bottom:10px;">
          <div style="font-size:13px; color:#606266; margin-bottom:6px;">问题模板（点一下换侧重点）</div>
          <el-space wrap>
            <el-button
              v-for="t in uziTemplates"
              :key="t.key"
              size="small"
              :type="uziDialog.focus === t.key ? 'primary' : 'default'"
              @click="applyFocus(t.key)"
            >{{ t.label }}</el-button>
          </el-space>
        </div>

        <el-input
          v-model="uziDialog.prompt"
          type="textarea"
          :rows="14"
          readonly
          class="uzi-prompt-box"
        />

        <div style="margin-top:12px;">
          <div style="font-size:13px; color:#606266; margin-bottom:6px;">本机备忘（仅浏览器本地）</div>
          <el-input v-model="uziDialog.note" type="textarea" :rows="3" placeholder="可选：写下你的判断，会塞进提示词" />
          <div style="margin-top:6px;">
            <el-button size="small" type="primary" plain @click="saveNote">保存备忘</el-button>
            <span style="margin-left:8px; font-size:12px; color:#909399;">换电脑/清缓存会丢，重要结论请另存</span>
          </div>
        </div>
      </div>

      <template #footer>
        <el-button @click="uziDialog.visible = false">关闭</el-button>
        <el-button type="primary" @click="copyLocalUziPrompt">复制提示词</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { useAppCtx } from '../composables/useAppCtx.js';
import { createUziAnalysisHelper, UZI_FOCUS_TEMPLATES } from '../modules/uziAnalysis.js';
import { useTableColumns, categoryTagType, pnlColor } from '../composables/useTableColumns.js';
import HomeDashboard from '../components/HomeDashboard.vue';

const {
  holdings,
  dashboard,
  showTransactions,
  openExpectedReturnDialog,
  openHoldingCorrectionDialog,
  openHoldingCorrectionHistory,
  formatMoney,
  formatPercent,
  holdingFloatProfit,
  holdingLifetimeProfit,
  holdingFloatProfitRate,
  holdingLifetimeProfitRate,
  trailingSyncing,
  syncTrailingReturns,
} = useAppCtx();

const HOLDING_COLS = [
  { key: 'category', label: '分类', defaultVisible: true },
  { key: 'quantity', label: '数量', defaultVisible: true },
  { key: 'avg_cost', label: '成本', defaultVisible: true },
  { key: 'diluted_cost', label: '摊薄成本', defaultVisible: false, optional: true },
  { key: 'last_price', label: '现价', defaultVisible: true },
  { key: 'market_value', label: '市值', defaultVisible: true },
  { key: 'float_profit', label: '持仓浮盈', defaultVisible: true },
  { key: 'float_rate', label: '浮盈率', defaultVisible: true },
  { key: 'lifetime_profit', label: '全周期盈亏', defaultVisible: false, optional: true },
  { key: 'lifetime_rate', label: '全周期收益率', defaultVisible: false, optional: true },
  { key: 'expected_return', label: '预计年化', defaultVisible: false, optional: true },
  { key: 'trailing_1y', label: '近一年', defaultVisible: false, optional: true },
];

const { isVisible, toggle, reset, allToggleColumns } = useTableColumns('it.cols.holdings.v1', HOLDING_COLS);

const sortState = ref({ prop: 'market_value', order: 'descending' });

function onSortChange({ prop, order }) {
  sortState.value = { prop: prop || 'market_value', order: order || 'descending' };
}

function rowMetric(row, prop) {
  if (prop === 'market_value') return Number(row.quantity || 0) * Number(row.last_price || 0);
  if (prop === 'float_profit') return Number(holdingFloatProfit(row) || 0);
  if (prop === 'float_rate') return Number(holdingFloatProfitRate(row) ?? -Infinity);
  if (prop === 'lifetime_profit') return Number(holdingLifetimeProfit(row) || 0);
  if (prop === 'quantity') return Number(row.quantity || 0);
  return Number(row[prop] || 0);
}

const sortedHoldings = computed(() => {
  const list = Array.isArray(holdings.value) ? [...holdings.value] : [];
  const { prop, order } = sortState.value || {};
  if (!prop || !order) return list;
  const dir = order === 'ascending' ? 1 : -1;
  list.sort((a, b) => (rowMetric(a, prop) - rowMetric(b, prop)) * dir);
  return list;
});

function formatQty(q) {
  const n = Number(q);
  if (!Number.isFinite(n)) return '—';
  return n.toLocaleString('zh-CN', { maximumFractionDigits: 4 });
}

const { buildUziPrompt, loadUziNote, saveUziNote } = createUziAnalysisHelper({ dashboard, formatMoney });
const uziTemplates = UZI_FOCUS_TEMPLATES;

const uziDialog = reactive({
  visible: false,
  row: null,
  depth: 'medium',
  focus: 'default',
  prompt: '',
  note: '',
});

function rebuildUziPrompt() {
  if (!uziDialog.row) return;
  try {
    uziDialog.prompt = buildUziPrompt(uziDialog.row, uziDialog.depth, uziDialog.focus) || '';
  } catch (e) {
    console.warn('[UZI] rebuild prompt failed', e);
  }
}

function openLocalUzi(row) {
  try {
    const code = String(row?.code ?? '').trim();
    if (!row || !code) {
      ElMessage.warning('该持仓缺少代码，无法生成 UZI 提示词');
      return;
    }
    const safeRow = { ...row, code };
    uziDialog.row = safeRow;
    uziDialog.depth = 'medium';
    uziDialog.focus = 'default';
    uziDialog.note = loadUziNote(code) || '';
    rebuildUziPrompt();
    if (!uziDialog.prompt) {
      uziDialog.prompt = `请使用 UZI-Skill 分析 ${safeRow.name || ''} (${code})，深度 medium。`;
    }
    uziDialog.visible = true;
  } catch (e) {
    console.error('[UZI] open failed', e);
    ElMessage.error('打开 UZI 分析失败，请看控制台');
  }
}

function applyFocus(key) {
  uziDialog.focus = key || 'default';
  rebuildUziPrompt();
}

function saveNote() {
  if (!uziDialog.row?.code) return;
  const ok = saveUziNote(uziDialog.row.code, uziDialog.note);
  if (ok) {
    ElMessage.success('备忘已保存到本机浏览器');
    rebuildUziPrompt();
  } else {
    ElMessage.warning('保存失败（可能浏览器禁用了本地存储）');
  }
}

async function copyLocalUziPrompt() {
  const t = uziDialog.prompt || '';
  if (!t) {
    ElMessage.warning('提示词为空');
    return;
  }
  try {
    await navigator.clipboard.writeText(t);
    ElMessage.success('提示词已复制，可直接粘贴到本地 Hermes 执行');
  } catch {
    ElMessage.warning('自动复制失败，请手动全选复制提示词');
  }
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
.holdings-toolbar-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.holdings-cards {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.holding-card {
  background: #fff;
  border: 1px solid var(--app-border, #e8edf3);
  border-radius: 12px;
  padding: 12px 14px;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
}
.holding-card-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}
.holding-card-mv {
  font-weight: 700;
  font-size: 15px;
  color: #111827;
}
.holding-card-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 12px;
  font-size: 13px;
}
.holding-card-ops {
  margin-top: 10px;
  display: flex;
  gap: 4px;
  border-top: 1px dashed #e5e7eb;
  padding-top: 8px;
}
.meta-label {
  font-size: 11px;
  color: #9ca3af;
  margin-bottom: 2px;
}
.meta-sub {
  margin-left: 4px;
  font-size: 12px;
  opacity: 0.85;
}
.empty-cards {
  text-align: center;
  color: #909399;
  padding: 24px;
}
</style>
