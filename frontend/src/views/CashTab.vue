<template>
  <PageShell>
    <template #actions>
      <el-space wrap>
        <el-button size="small" type="primary" :loading="feeBusy === 'save'" :disabled="!!feeBusy && feeBusy !== 'save'" @click="onSaveFeeSettings">保存费率</el-button>
      </el-space>
    </template>

    <!-- 状态带：钱有多少 / 费率配没配 / 上一笔动了什么 -->
    <div class="app-stat-row cols-3" aria-label="证券账户状态速览">
      <div class="app-stat-cell">
        <div class="k">券商现金合计</div>
        <div class="v">{{ formatMoney(dashboard.securities_cash) }}</div>
        <div class="s">买卖 / 分红自动联动，银证与校准写流水</div>
      </div>
      <div class="app-stat-cell">
        <div class="k">费率</div>
        <div class="v" :class="feeConfigured ? 'ok' : 'warn'">{{ feeConfigured ? '已配置' : '默认费率' }}</div>
        <div class="s">当前账户 {{ activeFeeAccount }} · 共 {{ feeAccounts.length }} 个账户</div>
      </div>
      <div class="app-stat-cell">
        <div class="k">最近一笔现金流水</div>
        <div class="v" :class="latestCashFlow ? (Number(latestCashFlow.amount || 0) >= 0 ? 'up' : 'down') : 'muted'">
          {{ latestCashFlow ? formatMoney(latestCashFlow.amount, 2, true) : '暂无流水' }}
        </div>
        <div class="s">
          {{ latestCashFlow
            ? [latestCashFlow.date, latestCashFlow.flow_type, latestCashFlow.account, '调整后 ' + formatMoney(latestCashFlow.balance_after)].filter(Boolean).join(' · ')
            : '还没有银证 / 校准流水' }}
        </div>
      </div>
    </div>

    <!-- Q1 哪个账户、按什么费率算 -->
    <el-card shadow="never" class="ops-card">
      <template #header>
        <div class="ops-card-head">
          <div>
            <div class="ops-section-title"><span class="ops-q">Q1</span>哪个账户、按什么费率算</div>
            <div class="ops-hint">多账户可分别设费率；单位 %，万 2.5 填 0.025。改完点右上角「保存费率」才生效。</div>
          </div>
          <span class="ops-card-actions">
            <el-tag size="small" :type="feeConfigured ? 'success' : 'info'" effect="light">
              {{ feeConfigured ? '已配置' : '默认费率' }}
            </el-tag>
            <el-tag size="small" type="info" effect="light">{{ feeAccounts.length }} 个账户</el-tag>
          </span>
        </div>
      </template>
      <div class="fee-toolbar">
        <span class="ops-field-label">当前账户</span>
        <el-select v-model="activeFeeAccount" style="width:180px" @change="onActiveFeeAccountChange">
          <el-option v-for="acc in feeAccounts" :key="acc" :label="acc" :value="acc"></el-option>
        </el-select>
        <el-input v-model="newFeeAccountName" placeholder="新增账户，如 招商证券" style="width:220px" clearable></el-input>
        <el-button :loading="feeBusy === 'add'" :disabled="!!feeBusy && feeBusy !== 'add'" @click="onAddFeeAccount">新增账户</el-button>
      </div>
      <div class="fee-settings-native" v-if="feeSettings[activeFeeAccount]">
        <div class="fee-settings-head">
          <div>类别</div><div>佣金率(%)</div><div>印花税(%)</div><div>过户费(%)</div><div>最低佣金(元)</div>
        </div>
        <div class="fee-settings-row" v-for="cat in feeCategories" :key="cat">
          <div class="fee-cat">{{ cat }}</div>
          <el-input-number v-model="feeSettings[activeFeeAccount][cat].commission_rate_pct" :precision="4" :min="0" :controls="false" class="fee-rate-input"></el-input-number>
          <el-input-number v-model="feeSettings[activeFeeAccount][cat].stamp_tax_rate_pct" :precision="4" :min="0" :controls="false" class="fee-rate-input"></el-input-number>
          <el-input-number v-model="feeSettings[activeFeeAccount][cat].transfer_fee_rate_pct" :precision="4" :min="0" :controls="false" class="fee-rate-input"></el-input-number>
          <el-input-number v-model="feeSettings[activeFeeAccount][cat].min_commission" :precision="2" :min="0" :controls="false" class="fee-rate-input"></el-input-number>
        </div>
      </div>
      <div class="ops-hint" style="margin-top:12px;">
        默认：A股佣金万2.5、卖出印花税万5、过户费万0.1；ETF/REITs/黄金默认只收佣金；债基默认0。最终以券商成交单为准。
      </div>

      <!-- 危险操作单独成组：费率重置与账户删除 -->
      <div class="hazard">
        <div class="hazard-head">
          <el-tag size="small" type="danger" effect="light">危险操作</el-tag>
          <strong>费率重置与账户删除</strong>
          <div class="hazard-hint">两个入口都不进「日常」，放在这张卡片的底部，都会带一次二次确认。</div>
        </div>
        <div class="hazard-body">
          <el-button type="danger" plain :loading="feeBusy === 'reset'" :disabled="!!feeBusy && feeBusy !== 'reset'" @click="onResetFeeSettings">恢复默认费率</el-button>
          <el-button type="danger" plain :loading="feeBusy === 'remove'" :disabled="feeAccounts.length <= 1 || (!!feeBusy && feeBusy !== 'remove')" @click="onRemoveFeeAccount">删除当前账户</el-button>
          <span class="hazard-hint">
            当前 {{ feeAccounts.length }} 个账户{{ feeAccounts.length <= 1 ? '，只剩 1 个时不可删' : '，可删' }}；「恢复默认费率」会覆盖全部账户的费率。
          </span>
        </div>
        <p class="hazard-note">
          两个操作都会先弹确认：「确定删除账户「{{ activeFeeAccount }}」的费率配置？交易记录不会删除。」/「恢复默认费率会覆盖全部账户的费率，确定继续？」
        </p>
      </div>
    </el-card>

    <!-- Q2 自动余额对不上时怎么校准 -->
    <el-card shadow="never" class="ops-card">
      <template #header>
        <div class="ops-card-head">
          <div>
            <div class="ops-section-title"><span class="ops-q">Q2</span>自动余额对不上时怎么校准</div>
            <div class="ops-hint">买入 / 卖出 / 分红自动联动；银证转账或券商余额对不上时再手动校准。</div>
          </div>
        </div>
      </template>
      <el-form label-position="top">
        <div class="field-grid">
          <div class="field">
            <div class="field-label">当前自动余额</div>
            <div class="field-row">
              <span class="cash-balance">{{ formatMoney(dashboard.securities_cash) }}</span>
            </div>
            <div class="ops-hint">只读：由交易与流水推出来的余额。</div>
          </div>
          <div class="field">
            <div class="field-label">手动校准余额</div>
            <div class="field-row">
              <el-input-number v-model="cashForm.amount" :precision="2" :min="0" style="width: 260px"></el-input-number>
              <el-button type="primary" :loading="cashSaving" @click="onUpdateCash">保存校准</el-button>
            </div>
            <div class="ops-hint">仅银证/券商现金校准；差额会写成一条「现金校准」流水。</div>
          </div>
        </div>
      </el-form>

      <div class="ops-section-title cash-sub-title">其他调整（现金校准留下的痕迹）</div>
      <el-table :data="adjustRows" stripe size="small" class="cash-table" style="width: 100%" empty-text="暂无其他调整" aria-label="其他调整流水">
        <el-table-column prop="date" label="日期" width="108" align="left" header-align="left" />
        <el-table-column prop="flow_type" label="类型" width="100">
          <template #default="scope">
            <el-tag size="small" :type="cashFlowTagType(scope.row.flow_type)">{{ scope.row.flow_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="金额" width="130" align="right" header-align="right">
          <template #default="scope"><span class="num-cell" :class="(Number(scope.row.amount || 0) >= 0) ? 'num-up' : 'num-down'">{{ formatMoney(scope.row.amount, 2, true) }}</span></template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="120" show-overflow-tooltip />
        <el-table-column label="操作" width="120" fixed="right" align="center" header-align="center">
          <template #default="scope">
            <el-button type="primary" link size="small" @click="openCashFlowEditDialog(scope.row)">编辑</el-button>
            <el-button type="danger" link size="small" :loading="cashFlowDeleting === scope.row" @click="onDeleteCashFlow(scope.row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="ops-hint" style="margin-top:10px;">这些行同时出现在下面的「证券资金流水」里，类型筛「现金校准」就能只看它们。</div>
    </el-card>

    <!-- Q3 钱怎么进出证券账户 -->
    <el-card shadow="never" class="ops-card">
      <template #header>
        <div class="ops-card-head">
          <div>
            <div class="ops-section-title"><span class="ops-q">Q3</span>钱怎么进出证券账户</div>
            <div class="ops-hint">银证转入 / 转出、现金校准会留痕；买卖分红仍在交易记录。区间统计跟着下面的筛选走。</div>
          </div>
        </div>
      </template>
      <el-form :model="cashFlowForm">
        <div class="field-grid cols-3">
          <div class="field">
            <div class="field-label">日期</div>
            <div class="field-row">
              <el-date-picker v-model="cashFlowForm.date" type="date" value-format="YYYY-MM-DD" style="width: 100%"></el-date-picker>
            </div>
          </div>
          <div class="field">
            <div class="field-label">证券账户</div>
            <div class="field-row">
              <el-select v-model="cashFlowForm.account" style="width: 100%">
                <el-option v-for="acc in feeAccounts" :key="acc" :label="acc" :value="acc"></el-option>
              </el-select>
            </div>
          </div>
          <div class="field">
            <div class="field-label">类型</div>
            <div class="field-row">
              <el-select v-model="cashFlowForm.flow_type" style="width: 100%">
                <el-option label="银证转入" value="银证转入"></el-option>
                <el-option label="银证转出" value="银证转出"></el-option>
                <el-option label="现金校准" value="现金校准"></el-option>
                <el-option label="其他调整" value="其他调整"></el-option>
              </el-select>
            </div>
          </div>
          <div class="field">
            <div class="field-label">金额</div>
            <div class="field-row">
              <el-input-number v-model="cashFlowForm.amount" :precision="2" :controls="false" class="wide-number-input"></el-input-number>
            </div>
          </div>
          <div class="field span-2">
            <div class="field-label">备注</div>
            <div class="field-row">
              <el-input v-model="cashFlowForm.remark" placeholder="如：银行卡转入、转出到银行、券商余额校准"></el-input>
            </div>
          </div>
          <div class="field">
            <div class="field-label">提交</div>
            <div class="field-row">
              <el-button type="primary" :loading="cashFlowSaving" @click="onAddCashFlow">新增流水</el-button>
            </div>
          </div>
        </div>
      </el-form>

      <!-- 区间四个数：一行发丝线分格 -->
      <div class="app-brief cols-4" style="margin:14px 0;">
        <div class="app-brief-cell">
          <div class="k">区间转入</div>
          <div class="v">{{ formatMoney(cashFlowSummary.inflow, 2) }}</div>
        </div>
        <div class="app-brief-cell">
          <div class="k">区间转出</div>
          <div class="v">{{ formatMoney(cashFlowSummary.outflowAbs, 2) }}</div>
        </div>
        <div class="app-brief-cell">
          <div class="k">区间净额</div>
          <div class="v" :class="Number(cashFlowSummary.net || 0) >= 0 ? 'up' : 'down'">{{ formatMoney(cashFlowSummary.net, 2, true) }}</div>
        </div>
        <div class="app-brief-cell">
          <div class="k">当前证券现金</div>
          <div class="v">{{ formatMoney(dashboard.securities_cash || 0, 2) }}</div>
        </div>
      </div>

      <div class="cash-filter-bar">
        <el-date-picker v-model="cashFlowQuery.dateRange" type="daterange" range-separator="至" start-placeholder="开始日期" end-placeholder="结束日期" value-format="YYYY-MM-DD" style="width:260px" @change="queryCashFlows"></el-date-picker>
        <el-select v-model="cashFlowQuery.account" placeholder="账户" clearable style="width:150px" @change="queryCashFlows">
          <el-option v-for="acc in feeAccounts" :key="acc" :label="acc" :value="acc"></el-option>
        </el-select>
        <el-select v-model="cashFlowQuery.flow_type" placeholder="类型" clearable style="width:150px" @change="queryCashFlows">
          <el-option label="银证转入" value="银证转入"></el-option>
          <el-option label="银证转出" value="银证转出"></el-option>
          <el-option label="现金校准" value="现金校准"></el-option>
          <el-option label="其他调整" value="其他调整"></el-option>
        </el-select>
        <el-button @click="queryCashFlows">查询</el-button>
        <el-button @click="resetCashFlowQuery">重置</el-button>
      </div>
      <el-table :data="cashFlows" stripe size="small" class="cash-table" style="width: 100%" aria-label="证券资金流水">
        <el-table-column prop="date" label="日期" width="108" align="left" header-align="left" fixed="left"></el-table-column>
        <el-table-column prop="account" label="账户" width="100" align="left" header-align="left"></el-table-column>
        <el-table-column prop="flow_type" label="类型" width="100" align="left" header-align="left">
          <template #default="scope">
            <el-tag size="small" :type="cashFlowTagType(scope.row.flow_type)">{{ scope.row.flow_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="金额" width="120" align="right" header-align="right">
          <template #default="scope"><span class="num-cell" :class="(Number(scope.row.amount || 0) >= 0 ) ? 'num-up' : 'num-down'">{{ formatMoney(scope.row.amount, 2, true) }}</span></template>
        </el-table-column>
        <el-table-column label="调整前" width="120" align="right" header-align="right"><template #default="scope"><span class="num-cell">{{ formatMoney(scope.row.balance_before) }}</span></template></el-table-column>
        <el-table-column label="调整后" width="120" align="right" header-align="right"><template #default="scope"><span class="num-cell">{{ formatMoney(scope.row.balance_after) }}</span></template></el-table-column>
        <el-table-column prop="remark" label="备注" show-overflow-tooltip></el-table-column>
        <el-table-column label="操作" width="120" fixed="right" align="center" header-align="center">
          <template #default="scope">
            <el-button type="primary" link size="small" @click="openCashFlowEditDialog(scope.row)">编辑</el-button>
            <el-button type="danger" link size="small" :loading="cashFlowDeleting === scope.row" @click="onDeleteCashFlow(scope.row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Q4 银证和组合投入对得上吗 -->
    <el-card shadow="never" class="ops-card">
      <template #header>
        <div class="ops-card-head">
          <div>
            <div class="ops-section-title"><span class="ops-q">Q4</span>银证和组合投入对得上吗</div>
            <div class="ops-hint">银证转入应对组合投入，银证转出应对组合取出；按同日同额配对（容差 0.05）。</div>
          </div>
          <el-button size="small" @click="fetchCashAudit">刷新勾稽</el-button>
        </div>
      </template>
      <el-alert
        v-if="cashAudit"
        :title="cashAudit.summary_text"
        :type="cashAudit.ok ? 'success' : 'warning'"
        show-icon
        :closable="false"
        style="margin-bottom: 12px"
      />
      <el-empty v-else description="打开本页或查询流水后会自动勾稽" />
      <div v-if="cashAudit" class="app-brief cols-4" style="margin-bottom: 12px;">
        <div class="app-brief-cell">
          <div class="k">银证转入</div>
          <div class="v">{{ formatMoney(cashAudit.bank_in || 0, 2) }}</div>
        </div>
        <div class="app-brief-cell">
          <div class="k">组合投入</div>
          <div class="v">{{ formatMoney(cashAudit.portfolio_in || 0, 2) }}</div>
        </div>
        <div class="app-brief-cell">
          <div class="k">银证转出</div>
          <div class="v">{{ formatMoney(Math.abs(cashAudit.bank_out || 0), 2) }}</div>
        </div>
        <div class="app-brief-cell">
          <div class="k">组合取出</div>
          <div class="v">{{ formatMoney(Math.abs(cashAudit.portfolio_out || 0), 2) }}</div>
        </div>
      </div>
      <!-- 未配对流水：空数据整块不渲染（别常显两张空表）；有数据时保持原样 -->
      <template v-if="hasUnmatchedRows">
        <template v-if="unmatchedBankRows.length">
          <div class="ops-hint" style="margin-bottom: 8px">未配对银证 {{ cashAudit.unmatched_bank_count || unmatchedBankRows.length }} 笔</div>
          <el-table :data="unmatchedBankRows" stripe size="small" style="width: 100%; margin-bottom: 12px" aria-label="未配对银证流水">
            <el-table-column prop="date" label="日期" width="110" />
            <el-table-column prop="flow_type" label="类型" width="100" />
            <el-table-column label="金额" width="130" align="right">
              <template #default="s"><span class="num-cell">{{ formatMoney(s.row.amount, 2, true) }}</span></template>
            </el-table-column>
            <el-table-column prop="remark" label="备注" show-overflow-tooltip />
          </el-table>
        </template>
        <template v-if="unmatchedPortfolioRows.length">
          <div class="ops-hint" style="margin-bottom: 8px">未配对组合流水 {{ cashAudit.unmatched_portfolio_count || unmatchedPortfolioRows.length }} 笔</div>
          <el-table :data="unmatchedPortfolioRows" stripe size="small" style="width: 100%" aria-label="未配对组合流水">
            <el-table-column prop="date" label="日期" width="110" />
            <el-table-column prop="flow_type" label="类型" width="100" />
            <el-table-column label="金额" width="130" align="right">
              <template #default="s"><span class="num-cell">{{ formatMoney(s.row.amount, 2, true) }}</span></template>
            </el-table-column>
            <el-table-column prop="remark" label="备注" show-overflow-tooltip />
          </el-table>
        </template>
      </template>
    </el-card>
  </PageShell>
</template>

<script setup>
import PageShell from '../components/PageShell.vue';
import { computed, ref } from 'vue';
import { ElMessageBox } from 'element-plus';
import { useAppCtx } from '../composables/useAppCtx.js';
const {
  dashboard, feeSettings, feeAccounts, activeFeeAccount, newFeeAccountName, feeCategories,
  cashForm, cashFlows, cashFlowForm, cashFlowQuery, cashFlowSummary, cashAudit,
  saveFeeSettings, resetFeeSettings, addFeeAccount, removeFeeAccount, onActiveFeeAccountChange,
  updateCash, queryCashFlows, resetCashFlowQuery, addCashFlow, openCashFlowEditDialog, deleteCashFlow,
  cashFlowTagType, formatMoney, fetchCashAudit,
} = useAppCtx();

// 未配对流水：后端没返回 / 返回空数组时都当空，整块不渲染（生产库 only 几行流水时别常显空表）
const auditData = () => cashAudit?.value ?? cashAudit ?? null;
const unmatchedBankRows = computed(() => {
  const rows = auditData()?.unmatched_bank;
  return Array.isArray(rows) ? rows : [];
});
const unmatchedPortfolioRows = computed(() => {
  const rows = auditData()?.unmatched_portfolio;
  return Array.isArray(rows) ? rows : [];
});
const hasUnmatchedRows = computed(
  () => !!(unmatchedBankRows.value.length || unmatchedPortfolioRows.value.length),
);
// 状态带格 3：最近一笔现金流水（当前筛选结果里的第一行，没有就留空）
const flowRows = () => (cashFlows?.value ?? cashFlows) || [];
const latestCashFlow = computed(() => {
  const rows = flowRows();
  return Array.isArray(rows) ? rows[0] || null : null;
});
// Q2「其他调整」：只挑现金校准 / 其他调整两类（编辑 / 删除复用流水表同一套处理函数）
const adjustRows = computed(() => {
  const rows = flowRows();
  if (!Array.isArray(rows)) return [];
  return rows.filter((r) => r && (r.flow_type === '现金校准' || r.flow_type === '其他调整'));
});
// 状态带 / Q1 卡头胶囊共用同一份判断：当前账户在 feeSettings 里有记录＝已有费率，否则走默认费率
const feeConfigured = computed(() => {
  const table = feeSettings?.value ?? feeSettings;
  const acc = activeFeeAccount?.value ?? activeFeeAccount;
  return !!(table && acc && table[acc]);
});

// 写操作防连点：模块里没有现成的 loading ref，这里用一个 in-flight 标志包一层。
// feeBusy 记当前在跑的费率写操作（保存/恢复默认/新增/删除账户），互斥避免并发覆盖同一份费率。
const feeBusy = ref('');
const cashSaving = ref(false);
const cashFlowSaving = ref(false);

async function runFeeWrite(key, fn) {
  if (feeBusy.value) return;
  feeBusy.value = key;
  try {
    await fn();
  } finally {
    if (feeBusy.value === key) feeBusy.value = '';
  }
}

const onSaveFeeSettings = () => runFeeWrite('save', saveFeeSettings);
const onAddFeeAccount = () => runFeeWrite('add', addFeeAccount);
const onRemoveFeeAccount = () => runFeeWrite('remove', removeFeeAccount);
// 恢复默认费率是破坏性操作（会覆盖全部账户的费率），补一次二次确认；取消就不调模块。
async function onResetFeeSettings() {
  if (feeBusy.value) return;
  try {
    await ElMessageBox.confirm('恢复默认费率会覆盖全部账户的费率配置（交易记录不变），确定继续？', '恢复默认费率', { type: 'warning' });
  } catch {
    return;
  }
  return runFeeWrite('reset', resetFeeSettings);
}

async function onUpdateCash() {
  if (cashSaving.value) return;
  cashSaving.value = true;
  try {
    await updateCash();
  } finally {
    cashSaving.value = false;
  }
}

async function onAddCashFlow() {
  if (cashFlowSaving.value) return;
  cashFlowSaving.value = true;
  try {
    await addCashFlow();
  } finally {
    cashFlowSaving.value = false;
  }
}

// 行内删除流水防连点：原来只有模块里的 confirm，连点会发两次 DELETE。
// 用「哪一行」做 in-flight 标记，只让被点的那行进 loading。
const cashFlowDeleting = ref(null);

async function onDeleteCashFlow(row) {
  if (cashFlowDeleting.value) return;
  cashFlowDeleting.value = row;
  try {
    await deleteCashFlow(row);
  } finally {
    if (cashFlowDeleting.value === row) cashFlowDeleting.value = null;
  }
}
</script>

<style scoped>
.ops-card { margin-bottom: 14px; }
.ops-card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
  flex-wrap: wrap;
}
.ops-section-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--app-text);
}
.ops-hint {
  margin-top: 2px;
  font-size: 12px;
  color: var(--app-soft);
}
.ops-field-label {
  font-size: 13px;
  color: var(--app-muted);
  font-weight: 600;
}
.cash-sub-title { margin: 18px 0 10px; }
.fee-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}
.cash-balance {
  font-size: 20px;
  font-weight: 700;
  color: var(--app-text);
  font-variant-numeric: tabular-nums;
}
.cash-filter-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

/* —— 参考图 idiom：卡片更轻、输入框更高（与消息推送页同一套，.chan-* 是推送页专属不在此列） —— */
.ops-card {
  border: 1px solid var(--app-hairline);
  border-radius: 12px;
  box-shadow: none;
}
.ops-card + .ops-card { margin-top: 16px; }
.ops-card :deep(.el-card__body) { padding: 18px 20px; }
.ops-card :deep(.el-input__wrapper) { min-height: 40px; }
</style>
