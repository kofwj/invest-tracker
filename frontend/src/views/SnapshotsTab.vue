<template>
                <el-card shadow="never">
                    <div class="snapshot-toolbar">
                        <div>
                            <div class="snapshot-title">资产快照分析</div>
                            <div class="snapshot-subtitle">看总资产、投资仓位、现金缓冲和区间变化，不只是一张快照流水表</div>
                        </div>
                        <div class="snapshot-controls">
                            <el-date-picker
                                v-model="snapshotRange"
                                type="daterange"
                                range-separator="至"
                                start-placeholder="开始日期"
                                end-placeholder="结束日期"
                                value-format="YYYY-MM-DD"
                                @change="fetchSnapshots"
                                style="width: 300px"
                            ></el-date-picker>
                            <el-button type="primary" @click="createSnapshot" :loading="snapshotLoading">记录/更新今日快照</el-button>
                            <el-button @click="exportSnapshots">导出快照</el-button>
                            <el-button type="warning" plain @click="compactSnapshots">压缩历史快照</el-button>
                        </div>
                    </div>

                    <el-alert
                        v-if="snapshotSummary?.day_over_day_anomaly?.text"
                        :title="snapshotSummary.day_over_day_anomaly.text"
                        type="warning"
                        show-icon
                        :closable="false"
                        style="margin-bottom: 16px;"
                    ></el-alert>
                    <el-alert
                        title="重复点击今天的快照会更新当天记录，不再因为已存在而丢掉最新价格/现金数据。"
                        type="info"
                        show-icon
                        :closable="false"
                        style="margin-bottom: 16px;"
                    ></el-alert>

                    <div class="snapshot-hero">
                        <el-card shadow="hover" v-for="(m, idx) in snapshotMetrics" :key="m.key" class="snapshot-metric-card" :class="{ 'is-highlight': idx === 0 }">
                            <div class="snapshot-metric-value" :style="{color: m.color || '#303133'}">{{ m.value }}</div>
                            <div class="snapshot-metric-label">{{ m.label }}</div>
                            <div class="snapshot-sub">{{ m.sub }}</div>
                        </el-card>
                    </div>

                    <div class="snapshot-insights" v-if="snapshotInsights.length">
                        <div class="snapshot-pill is-blue">
                            <div class="snapshot-pill-label">最新快照锚点</div>
                            <div class="snapshot-pill-main">{{ snapshotInsights[0]?.main || '—' }}</div>
                            <div class="snapshot-pill-sub">{{ snapshotInsights[0]?.sub || '暂无快照数据' }}</div>
                        </div>
                        <div class="snapshot-pill is-orange">
                            <div class="snapshot-pill-label">区间波动焦点</div>
                            <div class="snapshot-pill-main">{{ snapshotInsights[1]?.main || '—' }}</div>
                            <div class="snapshot-pill-sub">{{ snapshotInsights[1]?.sub || '至少需要两条快照' }}</div>
                        </div>
                        <div class="snapshot-pill is-green">
                            <div class="snapshot-pill-label">当前防守缓冲</div>
                            <div class="snapshot-pill-main">{{ snapshotInsights[2]?.main || '—' }}</div>
                            <div class="snapshot-pill-sub">{{ snapshotInsights[2]?.sub || '暂无数据' }}</div>
                        </div>
                    </div>

                    <el-row :gutter="20" style="margin-bottom: 18px;">
                        <el-col :span="14">
                            <el-card shadow="never" header="总资产趋势">
                                <div id="snapshotTrendChart" class="snapshot-chart"></div>
                            </el-card>
                        </el-col>
                        <el-col :span="10">
                            <el-card shadow="never" header="当前资产结构">
                                <div id="snapshotStructureChart" class="snapshot-chart"></div>
                            </el-card>
                        </el-col>
                    </el-row>

                    <el-row :gutter="20" style="margin-bottom: 18px;">
                        <el-col :span="24">
                            <el-card shadow="never" header="区间变化明细">
                                <el-table :data="snapshotChangeRows" stripe size="small" class="snapshot-table data-table" style="width: 100%" empty-text="至少需要两条快照，或选择包含两条以上记录的日期范围">
                                    <el-table-column prop="label" label="项目" width="120" align="left" header-align="left"></el-table-column>
                                    <el-table-column label="期初" min-width="120" align="right" header-align="right">
                                        <template #default="scope"><span class="num-cell">{{ formatMoney(scope.row.start) }}</span></template>
                                    </el-table-column>
                                    <el-table-column label="期末" min-width="120" align="right" header-align="right">
                                        <template #default="scope"><span class="num-cell">{{ formatMoney(scope.row.end) }}</span></template>
                                    </el-table-column>
                                    <el-table-column label="变化额" min-width="120" align="right" header-align="right">
                                        <template #default="scope">
                                            <span class="num-cell" :style="{color: scope.row.change >= 0 ? '#F56C6C' : '#67C23A'}">{{ formatMoney(scope.row.change, 2, true) }}</span>
                                        </template>
                                    </el-table-column>
                                    <el-table-column label="变化率" width="100" align="right" header-align="right">
                                        <template #default="scope">
                                            <span class="num-cell" :style="{color: scope.row.change >= 0 ? '#F56C6C' : '#67C23A'}">{{ scope.row.change_pct === null ? '—' : (scope.row.change_pct >= 0 ? '+' : '') + scope.row.change_pct.toFixed(2) + '%' }}</span>
                                        </template>
                                    </el-table-column>
                                </el-table>
                            </el-card>
                        </el-col>
                    </el-row>

                    <el-card shadow="never" header="快照历史记录">
                        <div class="desktop-only table-scroll">
                        <el-table :data="snapshots" stripe size="small" class="snapshot-table data-table" style="width: 100%" empty-text="暂无快照记录" :default-sort="{ prop: 'date', order: 'descending' }">
                            <el-table-column prop="date" label="日期" width="108" sortable align="left" header-align="left"></el-table-column>
                            <el-table-column label="总资产" min-width="120" align="right" header-align="right" sortable>
                                <template #default="scope"><span class="num-cell">{{ formatMoney(scope.row.total_assets) }}</span></template>
                            </el-table-column>
                            <el-table-column label="投资市值" min-width="120" align="right" header-align="right">
                                <template #default="scope"><span class="num-cell">{{ formatMoney(scope.row.total_market_value) }}</span></template>
                            </el-table-column>
                            <el-table-column label="银行存款" min-width="110" align="right" header-align="right">
                                <template #default="scope"><span class="num-cell">{{ formatMoney(scope.row.bank_balance) }}</span></template>
                            </el-table-column>
                            <el-table-column label="证券现金" min-width="100" align="right" header-align="right">
                                <template #default="scope"><span class="num-cell">{{ formatMoney(scope.row.securities_cash) }}</span></template>
                            </el-table-column>
                            <el-table-column label="申购在途" min-width="100" align="right" header-align="right">
                                <template #default="scope"><span class="num-cell">{{ formatMoney(scope.row.pending_purchase || 0) }}</span></template>
                            </el-table-column>
                            <el-table-column label="持仓浮盈" min-width="110" align="right" header-align="right">
                                <template #header>
                                    <el-tooltip content="快照时点的投资账户持仓浮盈（普通成本口径），不含历史已实现。" placement="top">
                                        <span>持仓浮盈</span>
                                    </el-tooltip>
                                </template>
                                <template #default="scope">
                                    <span class="num-cell" :style="{color: scope.row.total_profit >= 0 ? '#F56C6C' : '#67C23A'}">
                                        {{ formatMoney(scope.row.total_profit, 2, true) }}
                                    </span>
                                </template>
                            </el-table-column>
                            <el-table-column label="全周期" min-width="110" align="right" header-align="right">
                                <template #header>
                                    <el-tooltip content="快照时点的全周期盈亏（摊薄成本口径，接近券商累计）。旧快照可能为 0。" placement="top">
                                        <span>全周期</span>
                                    </el-tooltip>
                                </template>
                                <template #default="scope">
                                    <span class="num-cell" :style="{color: (scope.row.lifetime_profit || 0) >= 0 ? '#F56C6C' : '#67C23A'}">
                                        {{ formatMoney(scope.row.lifetime_profit || 0, 2, true) }}
                                    </span>
                                </template>
                            </el-table-column>
                            <el-table-column label="投资占比" width="88" align="right" header-align="right">
                                <template #default="scope"><span class="num-cell">{{ pct(scope.row.total_market_value, scope.row.total_assets) }}</span></template>
                            </el-table-column>
                            <el-table-column label="现金+存款+在途" min-width="128" align="right" header-align="right">
                                <template #default="scope"><span class="num-cell">{{ formatMoney((scope.row.bank_balance || 0) + (scope.row.securities_cash || 0) + (scope.row.pending_purchase || 0)) }}</span></template>
                            </el-table-column>
                            <el-table-column prop="holdings_count" label="持仓" width="68" align="right" header-align="right"></el-table-column>
                        </el-table>
                        </div>

                        <div class="mobile-only snapshot-cards">
                            <div v-for="row in snapshots" :key="row.date" class="holding-card">
                                <div class="holding-card-head">
                                    <div class="asset-name">{{ row.date }}</div>
                                    <div class="num-cell" style="font-weight:700;">{{ formatMoney(row.total_assets) }}</div>
                                </div>
                                <div class="holding-card-grid">
                                    <div>
                                        <div class="meta-label">投资市值</div>
                                        <div class="num-cell">{{ formatMoney(row.total_market_value) }}</div>
                                    </div>
                                    <div>
                                        <div class="meta-label">持仓浮盈</div>
                                        <div class="num-cell" :style="{color: row.total_profit >= 0 ? '#F56C6C' : '#67C23A'}">{{ formatMoney(row.total_profit, 2, true) }}</div>
                                    </div>
                                    <div>
                                        <div class="meta-label">银行存款</div>
                                        <div class="num-cell">{{ formatMoney(row.bank_balance) }}</div>
                                    </div>
                                    <div>
                                        <div class="meta-label">证券现金</div>
                                        <div class="num-cell">{{ formatMoney(row.securities_cash) }}</div>
                                    </div>
                                </div>
                            </div>
                            <div v-if="!snapshots.length" class="empty-cards">暂无快照</div>
                        </div>
                    </el-card>
                </el-card>
</template>

<script setup>
import { useAppCtx } from '../composables/useAppCtx.js';
const { snapshots, snapshotRange, snapshotMetrics, snapshotChangeRows, snapshotInsights, snapshotSummary, snapshotLoading, createSnapshot, fetchSnapshots, exportSnapshots, compactSnapshots, formatMoney, pct } = useAppCtx();
</script>

<style scoped>
.holding-card {
  background: #fff;
  border: 1px solid var(--app-border, #e8edf3);
  border-radius: 12px;
  padding: 12px 14px;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
  margin-bottom: 10px;
}
.holding-card-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
  align-items: center;
}
.holding-card-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 12px;
  font-size: 13px;
}
.meta-label {
  font-size: 11px;
  color: #9ca3af;
  margin-bottom: 2px;
}
.empty-cards {
  text-align: center;
  color: #909399;
  padding: 24px;
}
.snapshot-cards {
  display: flex;
  flex-direction: column;
}
</style>
