<template>
                <el-alert
                    title="近一年标的收益率 = 标的自身过去一年价格/净值涨跌；不是你的账户实际持有收益。若为空，请点右上角“同步近一年收益率”。持仓浮盈只看当前仓；全周期盈亏含历史买卖，接近券商累计盈亏。"
                    type="info"
                    show-icon
                    :closable="false"
                    style="margin-bottom: 12px;"
                ></el-alert>
                <el-table :data="holdings" stripe class="holdings-table" style="width: 100%" @row-click="showTransactions">
                    <el-table-column prop="name" label="名称" width="150" fixed="left" align="center" header-align="center"></el-table-column>
                    <el-table-column prop="category" label="分类" width="100" fixed="left" align="center" header-align="center"></el-table-column>
                    <el-table-column prop="code" label="代码" width="100" align="center" header-align="center"></el-table-column>
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
                    <el-table-column label="操作" min-width="220" width="240" align="center" header-align="center" fixed="right">
                        <template #default="scope">
                            <el-space wrap :size="4" style="justify-content:center;">
                                <el-button type="primary" link @click.stop="openExpectedReturnDialog(scope.row)">年化</el-button>
                                <el-button type="warning" link @click.stop="openHoldingCorrectionDialog(scope.row)">校正</el-button>
                                <el-button type="info" link @click.stop="openHoldingCorrectionHistory(scope.row)">记录</el-button>
                                <el-button type="success" link @click.stop="openUziAnalysisDialog(scope.row)">UZI 分析</el-button>
                            </el-space>
                        </template>
                    </el-table-column>
                </el-table>
</template>

<script setup>
import { useAppCtx } from '../composables/useAppCtx.js';
const { holdings, showTransactions, openExpectedReturnDialog, openHoldingCorrectionDialog, openHoldingCorrectionHistory, openUziAnalysisDialog, formatMoney, formatPercent, holdingFloatProfit, holdingLifetimeProfit, holdingFloatProfitRate, holdingLifetimeProfitRate } = useAppCtx();
</script>
