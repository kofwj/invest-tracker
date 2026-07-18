<template>
                <el-card shadow="never">
                    <div class="deposit-toolbar">
                        <div>
                            <div class="deposit-title">银行存款分析</div>
                            <div class="deposit-subtitle">展示存款总额、加权利率、预计利息、到期分布和银行集中度</div>
                        </div>
                        <el-space wrap>
                            <el-button @click="downloadDepositsTemplate">下载存款模板</el-button>
                            <el-button @click="exportDeposits">导出存款</el-button>
                            <el-upload
                                action="#"
                                :auto-upload="false"
                                :show-file-list="false"
                                accept=".csv"
                                :on-change="importDeposits"
                            >
                                <el-button type="warning">导入存款</el-button>
                            </el-upload>
                            <el-button type="primary" @click="openDepositDialog(null)">新增存款</el-button>
                        </el-space>
                    </div>

                    <div class="deposit-stats">
                        <el-card shadow="hover" class="deposit-stat-card">
                            <div class="deposit-stat-label">存款总额</div>
                            <div class="deposit-stat-value">{{ formatMoney(depositSummary.total) }}</div>
                            <div class="deposit-stat-sub">占总资产 {{ pct(depositSummary.total, dashboard.total_assets) }}</div>
                        </el-card>
                        <el-card shadow="hover" class="deposit-stat-card">
                            <div class="deposit-stat-label">加权平均利率</div>
                            <div class="deposit-stat-value" style="color:#409EFF;">{{ depositSummary.weightedRate.toFixed(2) }}%</div>
                            <div class="deposit-stat-sub">按金额加权</div>
                        </el-card>
                        <el-card shadow="hover" class="deposit-stat-card">
                            <div class="deposit-stat-label">预计年利息</div>
                            <div class="deposit-stat-value" style="color:#E6A23C;">{{ formatMoney(depositSummary.annualInterest) }}</div>
                            <div class="deposit-stat-sub">若按当前利率放满一年</div>
                        </el-card>
                        <el-card shadow="hover" class="deposit-stat-card">
                            <div class="deposit-stat-label">到期前预计利息</div>
                            <div class="deposit-stat-value" style="color:#67C23A;">{{ formatMoney(depositSummary.remainingInterest) }}</div>
                            <div class="deposit-stat-sub">按剩余天数合计（单利/365）</div>
                        </el-card>
                        <el-card shadow="hover" class="deposit-stat-card">
                            <div class="deposit-stat-label">下一笔到期</div>
                            <div class="deposit-stat-value" style="font-size:18px;">{{ depositSummary.nextDue ? depositSummary.nextDue.due_date : '—' }}</div>
                            <div class="deposit-stat-sub">{{ depositSummary.nextDue ? `${depositSummary.nextDue.bank_name} ${formatMoney(depositSummary.nextDue.amount)}，${depositSummary.nextDue.daysLeft}天` : '暂无到期日' }}</div>
                        </el-card>
                    </div>

                    <el-row :gutter="20" style="margin-bottom: 16px;">
                        <el-col :span="12">
                            <el-card shadow="never" header="银行集中度">
                                <div v-for="item in depositBankBreakdown" :key="item.bank_name" class="deposit-progress">
                                    <div class="deposit-bank-row">
                                        <span class="deposit-bank-name">{{ item.bank_name }}</span>
                                        <span>{{ formatMoney(item.amount) }} / {{ item.percentage.toFixed(1) }}%</span>
                                    </div>
                                    <el-progress :percentage="Number(item.percentage.toFixed(1))" :stroke-width="10" :show-text="false"></el-progress>
                                </div>
                                <el-empty v-if="!depositBankBreakdown.length" description="暂无存款" :image-size="60"></el-empty>
                            </el-card>
                        </el-col>
                        <el-col :span="12">
                            <el-card shadow="never" header="到期分布">
                                <el-table :data="depositMaturityBuckets" size="small" style="width:100%;">
                                    <el-table-column prop="bucket" label="期限"></el-table-column>
                                    <el-table-column label="金额" align="right" header-align="right">
                                        <template #default="scope">{{ formatMoney(scope.row.amount) }}</template>
                                    </el-table-column>
                                    <el-table-column label="占比" width="90" align="right" header-align="right">
                                        <template #default="scope">{{ scope.row.percentage.toFixed(1) }}%</template>
                                    </el-table-column>
                                </el-table>
                            </el-card>
                        </el-col>
                    </el-row>

                    <el-table :data="depositRows" stripe class="deposit-table" style="width: 100%">
                        <el-table-column prop="bank_name" label="银行名称" width="110" align="center" header-align="center"></el-table-column>
                        <el-table-column label="金额" min-width="120" align="right" header-align="right">
                            <template #default="scope">{{ formatMoney(scope.row.amount) }}</template>
                        </el-table-column>
                        <el-table-column label="组合占比" width="90" align="center" header-align="center">
                            <template #default="scope">{{ scope.row.percentage.toFixed(1) }}%</template>
                        </el-table-column>
                        <el-table-column label="年利率" width="90" align="center" header-align="center">
                            <template #default="scope">{{ Number(scope.row.interest_rate || 0).toFixed(2) }}%</template>
                        </el-table-column>
                        <el-table-column label="预计年利息" min-width="110" align="right" header-align="right">
                            <template #default="scope">{{ formatMoney(scope.row.annual_interest) }}</template>
                        </el-table-column>
                        <el-table-column label="到期前利息" min-width="110" align="right" header-align="right">
                            <template #default="scope">{{ scope.row.remaining_interest == null ? '—' : formatMoney(scope.row.remaining_interest) }}</template>
                        </el-table-column>
                        <el-table-column label="整期利息" min-width="110" align="right" header-align="right">
                            <template #default="scope">{{ scope.row.term_interest == null ? '—' : formatMoney(scope.row.term_interest) }}</template>
                        </el-table-column>
                        <el-table-column label="起存日" width="110" align="center" header-align="center">
                            <template #default="scope">{{ scope.row.start_date || '—' }}</template>
                        </el-table-column>
                        <el-table-column label="到期时间" width="110" align="center" header-align="center">
                            <template #default="scope">{{ scope.row.due_date || '—' }}</template>
                        </el-table-column>
                        <el-table-column label="剩余天数" width="100" align="center" header-align="center">
                            <template #default="scope">
                                <el-tag :type="scope.row.daysLeft <= 30 ? 'danger' : (scope.row.daysLeft <= 90 ? 'warning' : 'info')" effect="light">
                                    {{ scope.row.daysLeft === null ? '—' : `${scope.row.daysLeft}天` }}
                                </el-tag>
                            </template>
                        </el-table-column>
                        <el-table-column prop="remark" label="备注" min-width="120">
                            <template #default="scope">{{ scope.row.remark || '—' }}</template>
                        </el-table-column>
                        <el-table-column label="操作" width="130" align="center" header-align="center">
                            <template #default="scope">
                                <el-button type="primary" link @click="openDepositDialog(scope.row, scope.$index)">编辑</el-button>
                                <el-button type="danger" link @click="deleteDeposit(scope.row, scope.$index)">删除</el-button>
                            </template>
                        </el-table-column>
                    </el-table>
                </el-card>
</template>

<script setup>
import { useAppCtx } from '../composables/useAppCtx.js';
const { dashboard, depositRows, depositSummary, depositBankBreakdown, depositMaturityBuckets, downloadDepositsTemplate, exportDeposits, importDeposits, openDepositDialog, deleteDeposit, formatMoney, pct } = useAppCtx();
</script>
