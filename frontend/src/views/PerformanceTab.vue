<template>
                <div class="perf-page-header">
                    <div>
                        <h3 class="perf-page-title">收益分析</h3>
                        <div class="perf-page-subtitle">
                            用「整户总账 + 当前仓贡献 + 全周期 + 年化」看收益。数字和券商/持仓页对不上时，先看口径，不要先怀疑算错。
                        </div>
                    </div>
                    <div class="perf-page-actions">
                        <el-tag :type="perfSummary?.xirr_status === 'ok' ? 'success' : (hasPerfFlows ? 'info' : 'warning')" size="small">
                            {{ perfSummary?.xirr_status === 'ok' ? 'XIRR 已计算' : (hasPerfFlows ? (perfSummary?.xirr_message || '年化暂不可用') : '外部流水未录入') }}
                        </el-tag>
                        <el-button size="small" @click="fetchPerformance" :loading="perfLoading">刷新</el-button>
                    </div>
                </div>

                <div class="perf-guide-grid">
                    <div class="perf-guide-card" v-for="item in perfGuideSteps" :key="item.step">
                        <div class="perf-guide-step">{{ item.step }}</div>
                        <div class="perf-guide-body">
                            <div class="perf-guide-title">{{ item.title }}</div>
                            <div class="perf-guide-text">{{ item.text }}</div>
                        </div>
                    </div>
                </div>

                <div class="perf-tip-list">
                    <el-alert
                        v-for="tip in perfReadTips"
                        :key="tip.title"
                        :title="tip.title"
                        :description="tip.text"
                        :type="tip.type"
                        show-icon
                        :closable="false"
                        class="perf-tip-alert"
                    ></el-alert>
                </div>

                <el-row :gutter="12" class="perf-cards-row" style="margin-bottom: 18px;">
                    <el-col :xs="12" :sm="8" :md="4" v-for="m in perfCards" :key="m.label">
                        <el-card shadow="hover" class="perf-metric-card">
                            <div class="perf-metric-plain">{{ m.plain }}</div>
                            <div class="perf-metric-label">{{ m.label }}</div>
                            <div class="perf-metric-value" :style="{ color: m.color || '#303133' }">{{ m.value }}</div>
                            <div class="perf-metric-sub" :title="m.sub">{{ m.sub }}</div>
                        </el-card>
                    </el-col>
                </el-row>

                <el-card shadow="never" class="perf-lens-card" style="margin-bottom: 18px;">
                    <div class="perf-contrib-toolbar" style="margin-bottom: 10px;">
                        <div>
                            <div class="perf-contrib-title">三套盈亏口径对照</div>
                            <div class="perf-contrib-sub">先认口径，再对数字。日常配置决策优先看持仓明细；本页更适合看整户结果与相对贡献。</div>
                        </div>
                    </div>
                    <el-table :data="perfLensRows" size="small" class="perf-lens-table" style="width: 100%;">
                        <el-table-column prop="name" label="口径" width="120"></el-table-column>
                        <el-table-column prop="where" label="在哪里看" min-width="170"></el-table-column>
                        <el-table-column prop="meaning" label="怎么算" min-width="220"></el-table-column>
                        <el-table-column prop="goodFor" label="适合回答" min-width="220"></el-table-column>
                        <el-table-column prop="notFor" label="不要拿它当" min-width="220"></el-table-column>
                    </el-table>
                </el-card>

                <el-row :gutter="20" style="margin-bottom: 18px;" v-if="perfTimeline.length > 1">
                    <el-col :span="24">
                        <el-card shadow="never">
                            <template #header>
                                <div class="perf-chart-header">
                                    <div>
                                        <div class="perf-contrib-title">资产 vs 净投入</div>
                                        <div class="perf-contrib-sub">蓝线是总资产，橙线是累计净投入。资产线在净投入线上方，表示整户赚钱；间距越大赚得越多。</div>
                                    </div>
                                </div>
                            </template>
                            <div id="perfTimelineChart" style="height: 280px;"></div>
                        </el-card>
                    </el-col>
                </el-row>

                <el-card shadow="never" style="margin-bottom: 18px;">
                    <div class="perf-contrib-toolbar">
                        <div>
                            <div class="perf-contrib-title">标的收益贡献</div>
                            <div class="perf-contrib-sub">默认按「当前仓浮盈 + 累计分红」排序；另有「全周期盈亏」列接近券商累计。对账优先看全周期。</div>
                        </div>
                        <div class="perf-contrib-controls">
                            <el-tag size="small" type="info">共 {{ perfContribution.length }} 个标的</el-tag>
                            <el-select v-model="perfContributionFilter" size="small" style="width: 110px;">
                                <el-option label="全部标的" value="all"></el-option>
                                <el-option label="只看正贡献" value="positive"></el-option>
                                <el-option label="只看负贡献" value="negative"></el-option>
                            </el-select>
                            <el-select v-model="perfContributionSort" size="small" style="width: 150px;">
                                <el-option label="按当前仓贡献" value="contribution"></el-option>
                                <el-option label="按全周期盈亏" value="lifetime"></el-option>
                                <el-option label="按收益占比" value="share"></el-option>
                                <el-option label="按市值" value="market_value"></el-option>
                            </el-select>
                        </div>
                    </div>
                    <div class="perf-contrib-summary">
                        <div class="perf-summary-pill is-positive">
                            <div class="perf-summary-label">头号收益来源（当前仓）</div>
                            <div class="perf-summary-main">{{ perfContributionHeadline.best?.name || '—' }}</div>
                            <div class="perf-summary-sub">{{ perfContributionHeadline.best ? `${formatMoney(perfContributionHeadline.best.total_contribution, 2, true)} · 占整户总收益 ${pct(perfContributionHeadline.best.total_contribution, perfSummary?.total_gain || 0)}` : '暂无数据' }}</div>
                        </div>
                        <div class="perf-summary-pill is-negative">
                            <div class="perf-summary-label">当前拖累最大（当前仓）</div>
                            <div class="perf-summary-main">{{ perfContributionHeadline.worst?.name || '—' }}</div>
                            <div class="perf-summary-sub">{{ perfContributionHeadline.worst ? `${formatMoney(perfContributionHeadline.worst.total_contribution, 2, true)} · 占整户总收益 ${pct(perfContributionHeadline.worst.total_contribution, perfSummary?.total_gain || 0)}` : '暂无回撤标的' }}</div>
                        </div>
                        <div class="perf-summary-pill is-neutral">
                            <div class="perf-summary-label">结构概览</div>
                            <div class="perf-summary-main">正贡献 {{ perfContributionMix.positiveCount }} 个 / 负贡献 {{ perfContributionMix.negativeCount }} 个</div>
                            <div class="perf-summary-sub">前 3 大贡献合计 {{ formatMoney(perfContributionMix.top3Contribution, 2, true) }}</div>
                        </div>
                    </div>
                    <el-table :data="displayedPerfContribution" stripe size="small" class="perf-contrib-table" style="width: 100%">
                        <el-table-column label="标的" min-width="190" fixed="left">
                            <template #default="s">
                                <div class="perf-name-cell">
                                    <span class="perf-rank-badge" :class="{ 'perf-rank-top': s.$index < 3 }">{{ s.$index + 1 }}</span>
                                    <div class="perf-name-main">
                                        <div class="perf-name-title">{{ s.row.name }}</div>
                                        <div class="perf-name-code">{{ s.row.code }} · {{ s.row.category || '未分类' }}</div>
                                    </div>
                                </div>
                            </template>
                        </el-table-column>
                        <el-table-column label="市值 / 仓位" min-width="130" align="right" header-align="right">
                            <template #default="s">
                                <div>{{ formatMoney(s.row.market_value) }}</div>
                                <div class="perf-contrib-share">占总资产 {{ pct(s.row.market_value, perfSummary?.total_assets || 0) }}</div>
                            </template>
                        </el-table-column>
                        <el-table-column label="当前仓浮盈" min-width="120" align="right" header-align="right">
                            <template #header>
                                <el-tooltip content="(最新价 − 普通成本) × 数量，只看当前还持有的仓" placement="top">
                                    <span>当前仓浮盈</span>
                                </el-tooltip>
                            </template>
                            <template #default="s"><span :style="{color: s.row.unrealized_profit >= 0 ? '#F56C6C' : '#67C23A'}">{{ formatMoney(s.row.unrealized_profit, 2, true) }}</span></template>
                        </el-table-column>
                        <el-table-column label="累计分红" min-width="110" align="right" header-align="right">
                            <template #default="s"><span>{{ formatMoney(s.row.dividend_income, 2, true) }}</span></template>
                        </el-table-column>
                        <el-table-column label="全周期盈亏" min-width="120" align="right" header-align="right">
                            <template #header>
                                <el-tooltip content="(最新价 − 摊薄成本) × 数量；接近券商累计盈亏，分红已体现在摊薄成本中。" placement="top">
                                    <span>全周期盈亏</span>
                                </el-tooltip>
                            </template>
                            <template #default="s"><span :style="{color: (s.row.lifetime_profit || 0) >= 0 ? '#F56C6C' : '#67C23A'}">{{ formatMoney(s.row.lifetime_profit || 0, 2, true) }}</span></template>
                        </el-table-column>
                        <el-table-column label="当前仓总贡献" min-width="140" align="right" header-align="right">
                            <template #header>
                                <el-tooltip content="当前仓总贡献 = 当前仓浮盈 + 累计分红。不含历史卖出已实现盈亏。" placement="top">
                                    <span>当前仓总贡献</span>
                                </el-tooltip>
                            </template>
                            <template #default="s">
                                <div class="perf-contrib-value" :style="{color: s.row.total_contribution >= 0 ? '#F56C6C' : '#67C23A'}">{{ formatMoney(s.row.total_contribution, 2, true) }}</div>
                                <div class="perf-contrib-share">占整户总收益 {{ pct(s.row.total_contribution, perfSummary?.total_gain || 0) }}</div>
                            </template>
                        </el-table-column>
                        <el-table-column label="贡献强度" min-width="180">
                            <template #default="s">
                                <div class="perf-bar-track">
                                    <div class="perf-bar-fill" :style="contributionBarStyle(s.row.total_contribution)"></div>
                                </div>
                            </template>
                        </el-table-column>
                    </el-table>
                </el-card>

                <el-card shadow="never">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
                        <div>
                            <div style="font-weight:700;font-size:16px;color:#303133;">组合资金流水（外部投入/取出）</div>
                            <div class="perf-contrib-sub">只记「额外塞进组合」或「从组合提走」的钱。买卖股票、银证互转、银行内部转账都不要记这里。</div>
                        </div>
                        <el-tag size="small">共 {{ perfFlows.length }} 笔</el-tag>
                    </div>
                    <el-alert
                        title="示例：工资入金 10 万买股票 → 记一笔「投入 10 万」；年底提出 2 万花掉 → 记「取出 2 万」。在券商里卖 A 买 B，不算取出。"
                        type="info"
                        show-icon
                        :closable="false"
                        style="margin-bottom: 12px;"
                    ></el-alert>
                    <el-form :inline="true" size="small" style="margin-bottom: 12px;">
                        <el-form-item label="日期">
                            <el-date-picker v-model="perfFlowForm.date" type="date" value-format="YYYY-MM-DD" style="width:140px;"></el-date-picker>
                        </el-form-item>
                        <el-form-item label="类型">
                            <el-select v-model="perfFlowForm.flow_type" style="width:90px;">
                                <el-option label="投入" value="投入"></el-option>
                                <el-option label="取出" value="取出"></el-option>
                            </el-select>
                        </el-form-item>
                        <el-form-item label="金额">
                            <el-input-number v-model="perfFlowForm.amount" :min="0" :step="10000" style="width:140px;"></el-input-number>
                        </el-form-item>
                        <el-form-item label="来源">
                            <el-input v-model="perfFlowForm.source" placeholder="银行卡/工资" style="width:100px;"></el-input>
                        </el-form-item>
                        <el-form-item label="备注">
                            <el-input v-model="perfFlowForm.remark" style="width:120px;"></el-input>
                        </el-form-item>
                        <el-form-item>
                            <el-button type="primary" @click="addPerfFlow">新增</el-button>
                        </el-form-item>
                    </el-form>
                    <el-table :data="perfFlows" stripe size="small" style="width:100%;">
                        <el-table-column prop="date" label="日期" width="110"></el-table-column>
                        <el-table-column prop="flow_type" label="类型" width="70">
                            <template #default="s"><el-tag :type="s.row.flow_type === '投入' ? 'danger' : 'success'" size="small">{{ s.row.flow_type }}</el-tag></template>
                        </el-table-column>
                        <el-table-column label="金额" width="130" align="right">
                            <template #default="s">{{ formatMoney(s.row.amount) }}</template>
                        </el-table-column>
                        <el-table-column prop="source" label="来源" width="100"></el-table-column>
                        <el-table-column prop="remark" label="备注" min-width="120"></el-table-column>
                        <el-table-column label="操作" width="80" align="center">
                            <template #default="s">
                                <el-button type="danger" size="small" text @click="deletePerfFlow(s.row.id)">删除</el-button>
                            </template>
                        </el-table-column>
                    </el-table>
                </el-card>

                <el-card shadow="never" style="margin-top: 12px;">
                    <template #header>
                        <div>
                            <div class="perf-contrib-title">口径说明（备查）</div>
                            <div class="perf-contrib-sub">需要核对公式时再看这里；平时优先看页顶三步导读和三口径对照表。</div>
                        </div>
                    </template>
                    <el-descriptions :column="1" size="small" border>
                        <el-descriptions-item label="累计净投入">所有「投入」流水合计 − 所有「取出」流水合计（仅组合外部资金）</el-descriptions-item>
                        <el-descriptions-item label="累计总收益">当前总资产 − 累计净投入（整户总账）</el-descriptions-item>
                        <el-descriptions-item label="XIRR 年化">按组合外部现金流（投入/取出）+ 当前总资产计算的资金加权年化收益率</el-descriptions-item>
                        <el-descriptions-item label="当前仓浮盈/浮动盈亏">Σ[(最新价 − 普通成本) × 数量]；不含历史卖出已实现</el-descriptions-item>
                        <el-descriptions-item label="当前仓浮盈+分红">当前仓浮盈 + 累计分红；本页贡献表默认口径</el-descriptions-item>
                        <el-descriptions-item label="全周期盈亏">Σ[(最新价 − 摊薄成本) × 数量]；含卖出回款与分红摊薄，接近券商累计盈亏（见持仓明细）</el-descriptions-item>
                        <el-descriptions-item label="累计分红">所有持仓累计分红合计</el-descriptions-item>
                        <el-descriptions-item label="YTD">年初至今收益 = 当前总资产 − 年初快照总资产 − 今年净投入变化</el-descriptions-item>
                    </el-descriptions>
                </el-card>
</template>

<script setup>
import { useAppCtx } from '../composables/useAppCtx.js';
const { formatMoney, pct, perfSummary, perfTimeline, perfContribution, perfFlows, perfLoading, perfFlowForm, hasPerfFlows, perfGuideSteps, perfLensRows, perfReadTips, perfCards, displayedPerfContribution, perfContributionFilter, perfContributionSort, perfContributionHeadline, perfContributionMix, fetchPerformance, addPerfFlow, deletePerfFlow, contributionBarStyle } = useAppCtx();
</script>
