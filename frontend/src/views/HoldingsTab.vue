<template>
  <div class="holdings-tab">
    <el-alert
      title="近一年标的收益率 = 标的自身过去一年价格/净值涨跌；不是你的账户实际持有收益。若为空，请点右上角“同步近一年收益率”。持仓浮盈只看当前仓；全周期盈亏含历史买卖，接近券商累计盈亏。"
      type="info"
      show-icon
      :closable="false"
      style="margin-bottom: 12px;"
    />
    <el-table :data="holdings" stripe class="holdings-table" style="width: 100%" @row-click="showTransactions">
      <el-table-column prop="name" label="名称" width="150" fixed="left" align="center" header-align="center" />
      <el-table-column prop="category" label="分类" width="100" fixed="left" align="center" header-align="center" />
      <el-table-column prop="code" label="代码" width="100" align="center" header-align="center" />
      <el-table-column label="持仓数量" min-width="110" align="center" header-align="center">
        <template #default="scope"><span class="nowrap-cell">{{ scope.row.quantity }}</span></template>
      </el-table-column>
      <el-table-column label="普通成本" min-width="100" align="center" header-align="center">
        <template #header>
          <el-tooltip content="普通成本：剩余持仓按平均成本结转后的买入成本，不扣历史卖出回款。" placement="top">
            <span>普通成本</span>
          </el-tooltip>
        </template>
        <template #default="scope"><span class="nowrap-cell">{{ formatMoney(scope.row.avg_cost, 4) }}</span></template>
      </el-table-column>
      <el-table-column label="摊薄成本" min-width="110" align="center" header-align="center">
        <template #header>
          <el-tooltip content="券商口径：累计买入成本 - 卖出回款 - 累计分红，再除以剩余持仓；可能为负。" placement="top">
            <span>摊薄成本</span>
          </el-tooltip>
        </template>
        <template #default="scope">
          <span class="nowrap-cell" :style="{ color: Number(scope.row.diluted_cost || 0) < 0 ? '#67C23A' : '#303133' }">{{ formatMoney(scope.row.diluted_cost, 4) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="最新价" min-width="100" align="center" header-align="center">
        <template #default="scope"><span class="nowrap-cell">{{ formatMoney(scope.row.last_price, 4) }}</span></template>
      </el-table-column>
      <el-table-column label="市值" min-width="120" align="center" header-align="center">
        <template #default="scope"><span class="nowrap-cell">{{ formatMoney(scope.row.quantity * scope.row.last_price) }}</span></template>
      </el-table-column>
      <el-table-column label="持仓浮盈" min-width="120" align="center" header-align="center">
        <template #header>
          <el-tooltip content="持仓浮盈 = (最新价 − 普通成本) × 数量 + 累计分红；只看当前剩余持仓，不含历史卖出已实现盈亏。" placement="top">
            <span>持仓浮盈</span>
          </el-tooltip>
        </template>
        <template #default="scope">
          <span class="nowrap-cell" :style="{ color: holdingFloatProfit(scope.row) >= 0 ? '#F56C6C' : '#67C23A' }">
            {{ formatMoney(holdingFloatProfit(scope.row), 2, true) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="全周期盈亏" min-width="120" align="center" header-align="center">
        <template #header>
          <el-tooltip content="全周期盈亏 ≈ (最新价 − 摊薄成本) × 数量；含历史买卖已实现与分红摊薄，接近券商「累计盈亏」。" placement="top">
            <span>全周期盈亏</span>
          </el-tooltip>
        </template>
        <template #default="scope">
          <span class="nowrap-cell" :style="{ color: holdingLifetimeProfit(scope.row) >= 0 ? '#F56C6C' : '#67C23A' }">
            {{ formatMoney(holdingLifetimeProfit(scope.row), 2, true) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="浮盈率" min-width="90" align="center" header-align="center">
        <template #header>
          <el-tooltip content="持仓浮盈 / (普通成本 × 数量)" placement="top">
            <span>浮盈率</span>
          </el-tooltip>
        </template>
        <template #default="scope">
          <span class="nowrap-cell" :style="{ color: (holdingFloatProfitRate(scope.row) ?? 0) >= 0 ? '#F56C6C' : '#67C23A' }">
            {{ holdingFloatProfitRate(scope.row) === null ? '—' : formatPercent(holdingFloatProfitRate(scope.row)) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="全周期收益率" min-width="110" align="center" header-align="center">
        <template #header>
          <el-tooltip content="全周期盈亏 / (摊薄成本 × 数量)；净投入≤0 时不展示。" placement="top">
            <span>全周期收益率</span>
          </el-tooltip>
        </template>
        <template #default="scope">
          <span class="nowrap-cell" :style="{ color: (holdingLifetimeProfitRate(scope.row) ?? 0) >= 0 ? '#F56C6C' : '#67C23A' }">
            {{ holdingLifetimeProfitRate(scope.row) === null ? '—' : formatPercent(holdingLifetimeProfitRate(scope.row)) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="预计年化收益" width="120" align="center" header-align="center">
        <template #default="scope">
          <span>{{ scope.row.expected_return?.toFixed(1) }}%</span>
        </template>
      </el-table-column>
      <el-table-column label="近一年标的收益率" width="135" align="center" header-align="center">
        <template #header>
          <el-tooltip content="标的自身过去一年价格/净值回溯收益，不等于你的账户实际持有收益。" placement="top">
            <span>近一年收益</span>
          </el-tooltip>
        </template>
        <template #default="scope">
          <el-tooltip :content="scope.row.trailing_return_1y_source || '暂无数据，请同步近一年收益率'" placement="top">
            <span class="nowrap-cell" :style="{ color: Number(scope.row.trailing_return_1y || 0) >= 0 ? '#F56C6C' : '#67C23A' }">
              {{ formatPercent(scope.row.trailing_return_1y) }}
            </span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="操作" min-width="240" width="260" align="center" header-align="center" fixed="right">
        <template #default="scope">
          <div class="holdings-ops" @click.stop>
            <el-button type="primary" link @click="openExpectedReturnDialog(scope.row)">年化</el-button>
            <el-button type="warning" link @click="openHoldingCorrectionDialog(scope.row)">校正</el-button>
            <el-button type="info" link @click="openHoldingCorrectionHistory(scope.row)">记录</el-button>
            <el-button type="success" link @click="openLocalUzi(scope.row)">UZI 分析</el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <!-- UZI 弹窗放在持仓页本地，避免跨组件 provide 状态不同步 -->
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
          :rows="11"
          readonly
          style="font-family: monospace; font-size: 13px;"
        />

        <div style="margin-top:12px;">
          <div style="font-size:13px; color:#606266; margin-bottom:6px;">
            分析备忘（只存在本机浏览器，不进真仓）
          </div>
          <el-input
            v-model="uziDialog.note"
            type="textarea"
            :rows="3"
            placeholder="可粘贴 Hermes/UZI 结论摘要或报告路径，方便下次对照"
          />
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
import { reactive } from 'vue';
import { ElMessage } from 'element-plus';
import { useAppCtx } from '../composables/useAppCtx.js';
import { createUziAnalysisHelper, UZI_FOCUS_TEMPLATES } from '../modules/uziAnalysis.js';

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
} = useAppCtx();

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
  } catch (e) {
    ElMessage.warning('自动复制失败，请手动全选复制提示词');
  }
}
</script>

<style scoped>
.holdings-ops {
  display: flex;
  flex-wrap: wrap;
  gap: 2px 4px;
  justify-content: center;
  align-items: center;
}
</style>
