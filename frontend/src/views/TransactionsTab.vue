<template>
                <el-card header="新增交易记录">
                    <el-form :model="transForm" label-width="100px">
                        <el-row :gutter="20">
                            <el-col :span="8">
                                <el-form-item label="日期">
                                    <el-date-picker v-model="transForm.date" type="date" placeholder="选择日期" value-format="YYYY-MM-DD" style="width: 100%"></el-date-picker>
                                </el-form-item>
                            </el-col>
                            <el-col :span="8">
                                <el-form-item label="证券账户">
                                    <el-select v-model="transForm.account" placeholder="证券账户" style="width: 100%">
                                        <el-option v-for="acc in feeAccounts" :key="acc" :label="acc" :value="acc"></el-option>
                                    </el-select>
                                </el-form-item>
                            </el-col>
                            <el-col :span="8">
                                <el-form-item label="方向">
                                    <el-select v-model="transForm.direction" style="width: 100%">
                                        <el-option label="买入" value="买入"></el-option>
                                        <el-option label="卖出" value="卖出"></el-option>
                                        <el-option label="分红" value="分红"></el-option>
                                        <el-option label="分红再投资" value="分红再投资"></el-option>
                                        <el-option label="申购待确认" value="申购待确认"></el-option>
                                    </el-select>
                                </el-form-item>
                            </el-col>
                        </el-row>
                        <el-row :gutter="20">
                            <el-col :span="12">
                                <el-form-item label="代码">
                                    <el-autocomplete
                                        v-model="transForm.code"
                                        :fetch-suggestions="queryAssetByCode"
                                        placeholder="输入代码，如 601288"
                                        clearable
                                        style="width: 100%"
                                        @select="selectTransAsset"
                                        @input="(val) => autoMatchTransAsset('code', val)"
                                        @change="autoMatchTransAsset('code')"
                                    >
                                        <template #default="{ item }">
                                            <div class="asset-suggestion">
                                                <span class="asset-suggestion-main">{{ item.code }} - {{ item.name }}</span>
                                                <span class="asset-suggestion-tag">{{ item.category || '未分类' }}</span>
                                            </div>
                                        </template>
                                    </el-autocomplete>
                                </el-form-item>
                            </el-col>
                            <el-col :span="12">
                                <el-form-item label="名称">
                                    <el-autocomplete
                                        v-model="transForm.name"
                                        :fetch-suggestions="queryAssetByName"
                                        placeholder="输入名称，如 农业银行"
                                        clearable
                                        style="width: 100%"
                                        @select="selectTransAsset"
                                        @input="(val) => autoMatchTransAsset('name', val)"
                                        @change="autoMatchTransAsset('name')"
                                    >
                                        <template #default="{ item }">
                                            <div class="asset-suggestion">
                                                <span class="asset-suggestion-main">{{ item.name }} - {{ item.code }}</span>
                                                <span class="asset-suggestion-tag">{{ item.category || '未分类' }}</span>
                                            </div>
                                        </template>
                                    </el-autocomplete>
                                </el-form-item>
                            </el-col>
                        </el-row>
                        <el-row :gutter="20">
                            <el-col :span="12">
                                <el-form-item label="分类">
                                    <el-select v-model="transForm.category" placeholder="自动识别，可手动改" clearable style="width: 100%">
                                        <el-option label="A股权益" value="A股权益"></el-option>
                                        <el-option label="A股ETF" value="A股ETF"></el-option>
                                        <el-option label="港股ETF" value="港股ETF"></el-option>
                                        <el-option label="债基" value="债基"></el-option>
                                        <el-option label="REITs" value="REITs"></el-option>
                                        <el-option label="黄金" value="黄金"></el-option>
                                        <el-option label="其他" value="其他"></el-option>
                                    </el-select>
                                </el-form-item>
                            </el-col>
                            <el-col :span="12">
                                <el-form-item label="匹配标的">
                                    <span v-if="transForm.code || transForm.name">{{ transForm.name || '—' }} {{ transForm.code ? '(' + transForm.code + ')' : '' }}</span>
                                    <span v-else style="color: #909399;">—</span>
                                </el-form-item>
                            </el-col>
                        </el-row>
                        <el-row :gutter="20">
                            <el-col :span="12">
                                <el-form-item label="数量">
                                    <el-input-number v-model="transForm.quantity" :controls="false" class="wide-number-input"></el-input-number>
                                </el-form-item>
                            </el-col>
                            <el-col :span="12">
                                <el-form-item label="单价">
                                    <el-input-number v-model="transForm.price" :precision="4" :controls="false" class="wide-number-input"></el-input-number>
                                </el-form-item>
                            </el-col>
                        </el-row>
                        <el-alert
                            v-if="transForm.direction === '申购待确认'"
                            title="申购待确认：只填总金额即可，数量/单价可保持 0；证券现金会自动扣减，金额进入申购在途；不进入持仓份额和盈亏。份额确认后再编辑为‘买入’并补充份额/单价。"
                            type="info"
                            show-icon
                            :closable="false"
                            style="margin-bottom: 12px;"
                        ></el-alert>
                        <el-alert
                            v-if="transForm.direction === '分红再投资'"
                            title="分红再投资：金额填写分红/再投资金额，数量填写再投获得份额，单价填写再投净值；累计分红会增加，持仓份额也会增加，证券现金净影响通常为 0（如有手续费则扣手续费）。"
                            type="success"
                            show-icon
                            :closable="false"
                            style="margin-bottom: 12px;"
                        ></el-alert>
                        <el-row :gutter="20">
                            <el-col :span="12">
                                <el-form-item label="手续费">
                                    <el-input-number v-model="transForm.fee" :precision="2" :controls="false" class="wide-number-input" @input="markFeeManual"></el-input-number>
                                </el-form-item>
                            </el-col>
                            <el-col :span="12">
                                <el-form-item label="总金额">
                                    <el-input-number v-model="transForm.amount" :precision="2" :controls="false" class="wide-number-input"></el-input-number>
                                </el-form-item>
                            </el-col>
                        </el-row>
                        <div class="fee-hint">手续费会按当前费率自动估算，但保留手动输入；最终以券商实际成交单为准。{{ feeAutoHint }}</div>
                        <el-form-item>
                            <el-button type="primary" @click="submitTrans">提交记录</el-button>
                            <el-button @click="resetForm">重置</el-button>
                        </el-form-item>
                    </el-form>
                </el-card>


                <el-divider content-position="left">交易管理</el-divider>
                <el-alert
                    v-if="Number(dashboard?.pending_count || pendingTransactions.length || 0) > 0"
                    type="warning"
                    show-icon
                    :closable="false"
                    style="margin-bottom: 12px;"
                >
                    <template #title>
                        申购在途提醒：{{ Number(dashboard?.pending_count || pendingTransactions.length || 0) }} 笔，合计 {{ formatMoney(dashboard?.pending_purchase != null ? dashboard.pending_purchase : pendingPurchaseTotal) }}。份额/净值确认后，点击对应记录“编辑”，把方向改为“买入”并补充数量/单价。
                    </template>
                </el-alert>
                <el-card>
                    <template #header>
                        <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;">
                            <span>交易记录查询</span>
                            <el-space wrap>
                                <el-button @click="downloadTransactionsTemplate">下载交易模板</el-button>
                                <el-button @click="exportTransactions">导出交易</el-button>
                                <el-upload
                                    action="#"
                                    :auto-upload="false"
                                    :show-file-list="false"
                                    accept=".csv"
                                    :on-change="importTransactions"
                                >
                                    <el-button type="warning">导入交易</el-button>
                                </el-upload>
                            </el-space>
                        </div>
                    </template>
                    <!-- 筛选条件 -->
                    <el-row :gutter="20" style="margin-bottom: 20px;">
                        <el-col :span="8">
                            <el-date-picker
                                v-model="transQuery.dateRange"
                                type="daterange"
                                range-separator="至"
                                start-placeholder="开始日期"
                                end-placeholder="结束日期"
                                value-format="YYYY-MM-DD"
                                style="width: 100%"
                            ></el-date-picker>
                        </el-col>
                        <el-col :span="4">
                            <el-input v-model="transQuery.code" placeholder="代码" clearable></el-input>
                        </el-col>
                        <el-col :span="4">
                            <el-input v-model="transQuery.name" placeholder="名称" clearable></el-input>
                        </el-col>
                        <el-col :span="4">
                            <el-select v-model="transQuery.direction" placeholder="方向" clearable style="width: 100%">
                                <el-option label="买入" value="买入"></el-option>
                                <el-option label="卖出" value="卖出"></el-option>
                                <el-option label="分红" value="分红"></el-option>
                                <el-option label="分红再投资" value="分红再投资"></el-option>
                                <el-option label="申购待确认" value="申购待确认"></el-option>
                            </el-select>
                        </el-col>
                        <el-col :span="4">
                            <el-button type="primary" @click="applyTransFilter">查询</el-button>
                            <el-button @click="resetTransQuery">重置</el-button>
                        </el-col>
                    </el-row>
                    
                    <!-- 交易记录表格 -->
                    <el-table :data="filteredTransactions" stripe class="transaction-table" style="width: 100%" max-height="500">
                        <el-table-column prop="date" label="日期" width="115" sortable></el-table-column>
                        <el-table-column prop="code" label="代码" width="95"></el-table-column>
                        <el-table-column prop="name" label="名称" min-width="130"></el-table-column>
                        <el-table-column prop="category" label="分类" width="90"></el-table-column>
                        <el-table-column prop="account" label="账户" width="95"></el-table-column>
                        <el-table-column prop="direction" label="方向" width="80">
                            <template #default="scope">
                                <el-tag :type="scope.row.direction === '买入' ? 'danger' : (scope.row.direction === '卖出' ? 'success' : (scope.row.direction === '申购待确认' ? 'info' : (scope.row.direction === '分红再投资' ? 'primary' : 'warning')))">
                                    {{ scope.row.direction }}
                                </el-tag>
                            </template>
                        </el-table-column>
                        <el-table-column label="数量" min-width="130">
                            <template #default="scope"><span class="nowrap-cell">{{ scope.row.quantity?.toLocaleString() }}</span></template>
                        </el-table-column>
                        <el-table-column label="单价" min-width="115">
                            <template #default="scope"><span class="nowrap-cell">{{ formatMoney(scope.row.price, 4) }}</span></template>
                        </el-table-column>
                        <el-table-column label="金额" min-width="140">
                            <template #default="scope"><span class="nowrap-cell">{{ formatMoney(scope.row.amount) }}</span></template>
                        </el-table-column>
                        <el-table-column label="手续费" min-width="100">
                            <template #default="scope"><span class="nowrap-cell">{{ formatMoney(scope.row.fee) }}</span></template>
                        </el-table-column>
                        <el-table-column prop="remark" label="备注" min-width="120" show-overflow-tooltip></el-table-column>
                        <el-table-column label="操作" width="170" fixed="right">
                            <template #default="scope">
                                <el-button type="primary" size="small" @click="openTransEditDialog(scope.row)">编辑</el-button>
                                <el-button type="danger" size="small" @click="deleteTransaction(scope.row)">删除</el-button>
                            </template>
                        </el-table-column>
                    </el-table>
                    
                    <div style="margin-top: 12px; display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap;">
                        <span style="color: #909399;">当前页 {{ filteredTransactions.length }} 条 / 共 {{ transPage.total }} 条记录</span>
                        <el-pagination
                            background
                            layout="sizes, prev, pager, next, jumper"
                            :current-page="transPage.page"
                            :page-size="transPage.pageSize"
                            :page-sizes="[50, 100, 200, 500]"
                            :total="transPage.total"
                            @current-change="handleTransPageChange"
                            @size-change="handleTransPageSizeChange"
                        ></el-pagination>
                    </div>
                </el-card>
</template>

<script setup>
import { useAppCtx } from '../composables/useAppCtx.js';
const { transForm, feeAccounts, feeAutoHint, filteredTransactions, pendingTransactions, pendingPurchaseTotal, transQuery, transPage, submitTrans, resetForm, markFeeManual, downloadTransactionsTemplate, exportTransactions, importTransactions, queryAssetByCode, queryAssetByName, selectTransAsset, autoMatchTransAsset, applyTransFilter, resetTransQuery, handleTransPageChange, handleTransPageSizeChange, openTransEditDialog, deleteTransaction, formatMoney, dashboard } = useAppCtx();
</script>
