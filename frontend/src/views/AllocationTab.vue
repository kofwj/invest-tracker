<template>
                <el-card shadow="never">
                    <template #header>
                        <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;">
                            <div>
                                <div class="allocation-section-title">资产配置分析</div>
                                <div style="font-size:12px;color:#909399;margin-top:4px;">按权益 / 固收 / 存款拆解风险暴露、收益贡献和预计年化</div>
                            </div>
                            <el-tag type="info" effect="plain">总资产 {{ formatMoney(dashboard.total_assets) }}</el-tag>
                        </div>
                    </template>

                    <div class="allocation-hero">
                        <el-card shadow="hover" class="allocation-card allocation-main-card">
                            <div class="allocation-label">权益资产占比</div>
                            <div class="allocation-value" :style="{color: allocationSummary.equityRatio > 55 ? '#E6A23C' : '#303133'}">{{ allocationSummary.equityRatio.toFixed(1) }}%</div>
                            <div class="allocation-sub">权益金额 {{ formatMoney(allocationSummary.equityAmount) }}</div>
                        </el-card>
                        <el-card shadow="hover" class="allocation-card">
                            <div class="allocation-label">固收 + 存款占比</div>
                            <div class="allocation-value" style="color:#409EFF;">{{ allocationSummary.defensiveRatio.toFixed(1) }}%</div>
                            <div class="allocation-sub">防守资产 {{ formatMoney(allocationSummary.defensiveAmount) }}</div>
                        </el-card>
                        <el-card shadow="hover" class="allocation-card">
                            <div class="allocation-label">组合预计年化</div>
                            <div class="allocation-value" style="color:#E6A23C;">{{ portfolioExpectedReturn?.toFixed(2) }}%</div>
                            <div class="allocation-sub">按各资产预计收益加权</div>
                        </el-card>
                        <el-card shadow="hover" class="allocation-card">
                            <div class="allocation-label">当前申购在途</div>
                            <div class="allocation-value">{{ formatMoney(dashboard.pending_purchase || 0) }}</div>
                            <div class="allocation-sub">计入固收，不计入持仓盈亏</div>
                        </el-card>
                    </div>

                    <el-alert
                        :title="allocationSummary.comment"
                        type="info"
                        show-icon
                        :closable="false"
                        style="margin-bottom: 16px;"
                    ></el-alert>

                    <el-row :gutter="20" style="margin-bottom: 18px;">
                        <el-col :span="12">
                            <el-card shadow="never" header="大类资产结构">
                                <div id="allocationChart" class="chart-container"></div>
                            </el-card>
                        </el-col>
                        <el-col :span="12">
                            <el-card shadow="never" header="细分类别占比">
                                <div id="categoryChart" class="chart-container"></div>
                            </el-card>
                        </el-col>
                    </el-row>

                    <el-row :gutter="20" style="margin-bottom: 18px;">
                        <el-col :span="10">
                            <el-card shadow="never" header="配置健康检查">
                                <div class="allocation-risk-list">
                                    <div v-for="item in allocationHealth" :key="item.label" class="allocation-risk-item">
                                        <div class="allocation-risk-head">
                                            <span>{{ item.label }}</span>
                                            <el-tag :type="item.type" effect="light">{{ item.status }}</el-tag>
                                        </div>
                                        <div style="font-size:12px;color:#606266;line-height:1.5;">{{ item.text }}</div>
                                    </div>
                                </div>
                            </el-card>
                        </el-col>
                        <el-col :span="14">
                            <el-card shadow="never" header="资产大类汇总">
                                <el-table :data="macroAllocationAnalysis" stripe class="allocation-table" style="width: 100%">
                                    <el-table-column prop="group" label="大类" width="90" align="center" header-align="center"></el-table-column>
                                    <el-table-column label="金额" min-width="125" align="right" header-align="right">
                                        <template #default="scope">{{ formatMoney(scope.row.amount) }}</template>
                                    </el-table-column>
                                    <el-table-column label="占比" width="90" align="center" header-align="center">
                                        <template #default="scope">{{ scope.row.percentage?.toFixed(1) }}%</template>
                                    </el-table-column>
                                    <el-table-column label="持仓浮盈" min-width="120" align="right" header-align="right">
                                        <template #header>
                                            <el-tooltip content="按普通成本汇总的当前持仓浮盈+分红，不含历史卖出已实现。" placement="top">
                                                <span>持仓浮盈</span>
                                            </el-tooltip>
                                        </template>
                                        <template #default="scope"><span :style="{color: scope.row.profit >= 0 ? '#F56C6C' : '#67C23A'}">{{ formatMoney(scope.row.profit, 2, true) }}</span></template>
                                    </el-table-column>
                                    <el-table-column label="全周期盈亏" min-width="120" align="right" header-align="right">
                                        <template #header>
                                            <el-tooltip content="按摊薄成本汇总的全周期盈亏，接近券商累计盈亏。" placement="top">
                                                <span>全周期盈亏</span>
                                            </el-tooltip>
                                        </template>
                                        <template #default="scope"><span :style="{color: (scope.row.lifetime_profit || 0) >= 0 ? '#F56C6C' : '#67C23A'}">{{ formatMoney(scope.row.lifetime_profit || 0, 2, true) }}</span></template>
                                    </el-table-column>
                                    <el-table-column label="预计年化" width="100" align="center" header-align="center">
                                        <template #default="scope"><span style="color:#409EFF;font-weight:bold;">{{ scope.row.expected_return?.toFixed(2) }}%</span></template>
                                    </el-table-column>
                                    <el-table-column prop="detail" label="包含资产" min-width="170" show-overflow-tooltip></el-table-column>
                                </el-table>
                            </el-card>
                        </el-col>
                    </el-row>

                    <el-card shadow="never" header="细分类别明细">
                        <el-table :data="allocationAnalysis" stripe class="allocation-table" style="width: 100%">
                            <el-table-column prop="category" label="资产类别" width="110" align="center" header-align="center"></el-table-column>
                            <el-table-column label="市值/金额" min-width="125" align="right" header-align="right">
                                <template #default="scope">{{ formatMoney(scope.row.market_value) }}</template>
                            </el-table-column>
                            <el-table-column label="总资产占比" width="105" align="center" header-align="center">
                                <template #default="scope">{{ scope.row.percentage?.toFixed(1) }}%</template>
                            </el-table-column>
                            <el-table-column label="持仓浮盈" min-width="120" align="right" header-align="right">
                                <template #default="scope"><span :style="{color: scope.row.profit >= 0 ? '#F56C6C' : '#67C23A'}">{{ formatMoney(scope.row.profit, 2, true) }}</span></template>
                            </el-table-column>
                            <el-table-column label="全周期盈亏" min-width="120" align="right" header-align="right">
                                <template #default="scope"><span :style="{color: (scope.row.lifetime_profit || 0) >= 0 ? '#F56C6C' : '#67C23A'}">{{ formatMoney(scope.row.lifetime_profit || 0, 2, true) }}</span></template>
                            </el-table-column>
                            <el-table-column label="浮盈率" width="95" align="center" header-align="center">
                                <template #default="scope"><span :style="{color: scope.row.profit_rate >= 0 ? '#F56C6C' : '#67C23A'}">{{ scope.row.profit_rate >= 0 ? '+' : '' }}{{ scope.row.profit_rate?.toFixed(2) }}%</span></template>
                            </el-table-column>
                            <el-table-column prop="count" label="标的数" width="80" align="center" header-align="center"></el-table-column>
                            <el-table-column label="预计年化" width="100" align="center" header-align="center">
                                <template #default="scope"><span style="color:#409EFF;font-weight:bold;">{{ scope.row.expected_annual_return?.toFixed(1) }}%</span></template>
                            </el-table-column>
                        </el-table>
                    </el-card>
                </el-card>
</template>

<script setup>
import { onMounted, watch, nextTick } from 'vue';
import { useAppCtx } from '../composables/useAppCtx.js';

const {
    dashboard,
    allocationAnalysis,
    macroAllocationAnalysis,
    allocationSummary,
    allocationHealth,
    portfolioExpectedReturn,
    formatMoney,
} = useAppCtx();

// 本 tab 为 lazy + 异步组件：父级 watch 的 nextTick 经常早于本组件挂载。
// 挂载后再画一次，并在配置数据变化时刷新。
const paintCharts = async () => {
    const { renderAllocationChartsView, waitForChartDom } = await import('../charts/index.js');
    const ready = await waitForChartDom(['allocationChart', 'categoryChart']);
    if (!ready) return;
    await nextTick();
    renderAllocationChartsView(macroAllocationAnalysis.value, allocationAnalysis.value);
};

onMounted(() => {
    paintCharts();
});

watch(
    [macroAllocationAnalysis, allocationAnalysis],
    () => {
        paintCharts();
    },
    { deep: true },
);
</script>
