<template>
                <el-card header="证券账户现金余额">
                    <el-alert
                        title="证券现金已改为自动联动：买入/申购待确认自动扣减，卖出/分红自动增加，分红再投资通常现金净影响为0；银证转账或券商余额校准时，在这里手动更新当前余额即可。"
                        type="info"
                        show-icon
                        :closable="false"
                        style="margin-bottom: 16px;"
                    ></el-alert>
                    <el-form label-width="130px">
                        <el-form-item label="当前自动余额">
                            <span style="font-size: 20px; font-weight: bold;">{{ formatMoney(dashboard.securities_cash) }}</span>
                        </el-form-item>
                        <el-form-item label="手动校准余额">
                            <el-input-number v-model="cashForm.amount" :precision="2" :min="0" style="width: 300px"></el-input-number>
                            <span style="margin-left: 12px; color: #909399;">仅用于银证转账/券商现金余额校准</span>
                        </el-form-item>
                        <el-form-item>
                            <el-button type="primary" @click="updateCash">保存校准</el-button>
                        </el-form-item>
                    </el-form>
                </el-card>

                <el-card header="证券资金流水" class="mt-20">
                    <el-alert
                        title="银证转入、银证转出、现金校准会在这里留痕；买入/卖出/分红/分红再投资/申购待确认仍在交易记录里查询。证券现金 = 现金基准 + 资金流水 + 交易现金流。"
                        type="info"
                        show-icon
                        :closable="false"
                        style="margin-bottom: 16px;"
                    ></el-alert>
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
                    <div style="display:flex; align-items:center; gap:12px; margin-bottom:12px; flex-wrap:wrap;">
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
                    <el-table :data="cashFlows" stripe style="width: 100%">
                        <el-table-column prop="date" label="日期" width="110"></el-table-column>
                        <el-table-column prop="account" label="账户" width="100"></el-table-column>
                        <el-table-column prop="flow_type" label="类型" width="100">
                            <template #default="scope">
                                <el-tag :type="cashFlowTagType(scope.row.flow_type)">{{ scope.row.flow_type }}</el-tag>
                            </template>
                        </el-table-column>
                        <el-table-column label="金额" width="130">
                            <template #default="scope"><span :style="{ color: Number(scope.row.amount || 0) >= 0 ? '#F56C6C' : '#67C23A' }">{{ formatMoney(scope.row.amount, 2, true) }}</span></template>
                        </el-table-column>
                        <el-table-column label="调整前" width="130"><template #default="scope">{{ formatMoney(scope.row.balance_before) }}</template></el-table-column>
                        <el-table-column label="调整后" width="130"><template #default="scope">{{ formatMoney(scope.row.balance_after) }}</template></el-table-column>
                        <el-table-column prop="remark" label="备注" show-overflow-tooltip></el-table-column>
                        <el-table-column label="操作" width="150" fixed="right">
                            <template #default="scope">
                                <el-button type="primary" link @click="openCashFlowEditDialog(scope.row)">编辑</el-button>
                                <el-button type="danger" link @click="deleteCashFlow(scope.row)">删除</el-button>
                            </template>
                        </el-table-column>
                    </el-table>
                </el-card>

                <el-card header="交易费率设置" class="mt-20">
                    <el-alert
                        title="支持多个证券账户分别设置费率。交易录入会按所选账户和分类自动估算手续费，但手续费输入框仍可手动覆盖，最终以券商实际成交单为准。费率单位为 %，例如万2.5填 0.025。"
                        type="info"
                        show-icon
                        :closable="false"
                        style="margin-bottom: 16px;"
                    ></el-alert>
                    <div style="display:flex; align-items:center; gap:12px; margin-bottom:14px; flex-wrap:wrap;">
                        <span style="color:#606266;">当前费率账户</span>
                        <el-select v-model="activeFeeAccount" style="width:180px" @change="onActiveFeeAccountChange">
                            <el-option v-for="acc in feeAccounts" :key="acc" :label="acc" :value="acc"></el-option>
                        </el-select>
                        <el-input v-model="newFeeAccountName" placeholder="新增账户名称，如 招商证券" style="width:220px" clearable></el-input>
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
                    <div style="margin-top: 14px; display:flex; gap:12px; align-items:center; flex-wrap:wrap;">
                        <el-button type="primary" @click="saveFeeSettings">保存费率设置</el-button>
                        <el-button @click="resetFeeSettings">恢复默认费率</el-button>
                        <span style="color:#909399;font-size:12px;">每个账户独立保存；默认：A股佣金万2.5、卖出印花税万5、过户费万0.1；ETF/REITs/黄金默认只收佣金；债基默认0。</span>
                    </div>
                </el-card>
</template>

<script setup>
import { useAppCtx } from '../composables/useAppCtx.js';
const { dashboard, feeSettings, feeAccounts, activeFeeAccount, newFeeAccountName, feeCategories, cashForm, cashFlows, cashFlowForm, cashFlowQuery, cashFlowSummary, saveFeeSettings, resetFeeSettings, addFeeAccount, removeFeeAccount, onActiveFeeAccountChange, updateCash, queryCashFlows, resetCashFlowQuery, addCashFlow, openCashFlowEditDialog, deleteCashFlow, cashFlowTagType, formatMoney } = useAppCtx();
</script>
