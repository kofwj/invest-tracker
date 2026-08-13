<template>
  <PageShell
    title="证券账户"
    subtitle="账户费率、证券现金校准、银证流水。交易录入会按这里的账户与费率估算手续费。"
  >
    <template #actions>
      <el-space wrap>
        <el-button size="small" type="primary" @click="saveFeeSettings">保存费率</el-button>
        <el-button size="small" @click="resetFeeSettings">恢复默认费率</el-button>
      </el-space>
    </template>

    <el-card shadow="never" class="ops-card">
      <template #header>
        <div class="ops-card-head">
          <div>
            <div class="ops-section-title">证券账户与费率</div>
            <div class="ops-hint">多账户可分别设费率；单位 %，万 2.5 填 0.025</div>
          </div>
        </div>
      </template>
      <div class="fee-toolbar">
        <span class="ops-field-label">当前账户</span>
        <el-select v-model="activeFeeAccount" style="width:180px" @change="onActiveFeeAccountChange">
          <el-option v-for="acc in feeAccounts" :key="acc" :label="acc" :value="acc"></el-option>
        </el-select>
        <el-input v-model="newFeeAccountName" placeholder="新增账户，如 招商证券" style="width:220px" clearable></el-input>
        <el-button @click="addFeeAccount">新增账户</el-button>
        <el-button type="danger" plain @click="removeFeeAccount" :disabled="feeAccounts.length <= 1">删除当前账户</el-button>
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
    </el-card>

    <el-card shadow="never" class="ops-card">
      <template #header>
        <div class="ops-card-head">
          <div>
            <div class="ops-section-title">证券现金余额</div>
            <div class="ops-hint">买入/卖出/分红自动联动；银证转账或券商余额对不上时再手动校准</div>
          </div>
        </div>
      </template>
      <el-form label-width="130px">
        <el-form-item label="当前自动余额">
          <span class="cash-balance">{{ formatMoney(dashboard.securities_cash) }}</span>
        </el-form-item>
        <el-form-item label="手动校准余额">
          <el-input-number v-model="cashForm.amount" :precision="2" :min="0" style="width: 260px"></el-input-number>
          <span class="ops-hint" style="margin-left:12px;">仅银证/券商现金校准</span>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="updateCash">保存校准</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" class="ops-card">
      <template #header>
        <div class="ops-card-head">
          <div>
            <div class="ops-section-title">证券资金流水</div>
            <div class="ops-hint">银证转入/转出、现金校准会留痕；买卖分红仍在交易记录</div>
          </div>
        </div>
      </template>
      <el-form :model="cashFlowForm" label-width="90px">
        <el-row :gutter="16">
          <el-col :span="5">
            <el-form-item label="日期">
              <el-date-picker v-model="cashFlowForm.date" type="date" value-format="YYYY-MM-DD" style="width: 100%"></el-date-picker>
            </el-form-item>
          </el-col>
          <el-col :span="5">
            <el-form-item label="证券账户">
              <el-select v-model="cashFlowForm.account" style="width: 100%">
                <el-option v-for="acc in feeAccounts" :key="acc" :label="acc" :value="acc"></el-option>
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="5">
            <el-form-item label="类型">
              <el-select v-model="cashFlowForm.flow_type" style="width: 100%">
                <el-option label="银证转入" value="银证转入"></el-option>
                <el-option label="银证转出" value="银证转出"></el-option>
                <el-option label="现金校准" value="现金校准"></el-option>
                <el-option label="其他调整" value="其他调整"></el-option>
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="5">
            <el-form-item label="金额">
              <el-input-number v-model="cashFlowForm.amount" :precision="2" :controls="false" class="wide-number-input"></el-input-number>
            </el-form-item>
          </el-col>
          <el-col :span="4">
            <el-form-item label=" ">
              <el-button type="primary" @click="addCashFlow">新增流水</el-button>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="备注">
          <el-input v-model="cashFlowForm.remark" placeholder="如：银行卡转入、转出到银行、券商余额校准"></el-input>
        </el-form-item>
      </el-form>
      <el-row :gutter="16" style="margin-bottom: 14px;">
        <el-col :span="6"><el-statistic title="区间转入" :value="cashFlowSummary.inflow" :precision="2" prefix="¥"></el-statistic></el-col>
        <el-col :span="6"><el-statistic title="区间转出" :value="cashFlowSummary.outflowAbs" :precision="2" prefix="¥"></el-statistic></el-col>
        <el-col :span="6"><el-statistic title="区间净额" :value="cashFlowSummary.net" :precision="2" prefix="¥"></el-statistic></el-col>
        <el-col :span="6"><el-statistic title="当前证券现金" :value="dashboard.securities_cash || 0" :precision="2" prefix="¥"></el-statistic></el-col>
      </el-row>
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
      <el-table :data="cashFlows" stripe size="small" class="cash-table" style="width: 100%">
        <el-table-column prop="date" label="日期" width="108" align="left" header-align="left"></el-table-column>
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
            <el-button type="danger" link size="small" @click="deleteCashFlow(scope.row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="ops-card">
      <template #header>
        <div class="ops-card-head">
          <div>
            <div class="ops-section-title">银证 vs 组合投入勾稽</div>
            <div class="ops-hint">银证转入应对组合投入，银证转出应对组合取出；按同日同额配对（容差 0.05）</div>
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
      <el-row v-if="cashAudit" :gutter="16" style="margin-bottom: 12px">
        <el-col :span="6"><el-statistic title="银证转入" :value="cashAudit.bank_in || 0" :precision="2" prefix="¥" /></el-col>
        <el-col :span="6"><el-statistic title="组合投入" :value="cashAudit.portfolio_in || 0" :precision="2" prefix="¥" /></el-col>
        <el-col :span="6"><el-statistic title="银证转出" :value="Math.abs(cashAudit.bank_out || 0)" :precision="2" prefix="¥" /></el-col>
        <el-col :span="6"><el-statistic title="组合取出" :value="Math.abs(cashAudit.portfolio_out || 0)" :precision="2" prefix="¥" /></el-col>
      </el-row>
      <div v-if="cashAudit?.unmatched_bank?.length" class="ops-hint" style="margin-bottom: 8px">未配对银证 {{ cashAudit.unmatched_bank_count }} 笔</div>
      <el-table v-if="cashAudit?.unmatched_bank?.length" :data="cashAudit.unmatched_bank" stripe size="small" style="width: 100%; margin-bottom: 12px">
        <el-table-column prop="date" label="日期" width="110" />
        <el-table-column prop="flow_type" label="类型" width="100" />
        <el-table-column label="金额" width="130" align="right">
          <template #default="s"><span class="num-cell">{{ formatMoney(s.row.amount, 2, true) }}</span></template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" show-overflow-tooltip />
      </el-table>
      <div v-if="cashAudit?.unmatched_portfolio?.length" class="ops-hint" style="margin-bottom: 8px">未配对组合流水 {{ cashAudit.unmatched_portfolio_count }} 笔</div>
      <el-table v-if="cashAudit?.unmatched_portfolio?.length" :data="cashAudit.unmatched_portfolio" stripe size="small" style="width: 100%">
        <el-table-column prop="date" label="日期" width="110" />
        <el-table-column prop="flow_type" label="类型" width="100" />
        <el-table-column label="金额" width="130" align="right">
          <template #default="s"><span class="num-cell">{{ formatMoney(s.row.amount, 2, true) }}</span></template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" show-overflow-tooltip />
      </el-table>
    </el-card>
  </PageShell>
</template>

<script setup>
import PageShell from '../components/PageShell.vue';
import { useAppCtx } from '../composables/useAppCtx.js';
const {
  dashboard, feeSettings, feeAccounts, activeFeeAccount, newFeeAccountName, feeCategories,
  cashForm, cashFlows, cashFlowForm, cashFlowQuery, cashFlowSummary, cashAudit,
  saveFeeSettings, resetFeeSettings, addFeeAccount, removeFeeAccount, onActiveFeeAccountChange,
  updateCash, queryCashFlows, resetCashFlowQuery, addCashFlow, openCashFlowEditDialog, deleteCashFlow,
  cashFlowTagType, formatMoney, fetchCashAudit,
} = useAppCtx();
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
</style>
