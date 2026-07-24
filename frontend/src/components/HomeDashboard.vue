<template>
        <div class="home-tagline">真仓账本 · 记清每一笔，再决定怎么调 · 分析只读不改仓</div>
        <!-- 顶部资产概览 -->
        <div class="top-stats">
            <el-card shadow="hover" class="stat-card stat-main">
                <div class="stat-card-inner">
                    <div class="stat-label">总资产</div>
                    <div class="stat-value">{{ formatMoney(dashboard.total_assets) }}</div>
                    <div class="stat-sub">市值 + 现金 + 存款 + 申购在途</div>
                </div>
            </el-card>
            <el-card shadow="hover" class="stat-card">
                <div class="stat-card-inner">
                    <div class="stat-label">投资账户市值</div>
                    <div class="stat-value">{{ formatMoney(dashboard.total_market_value) }}</div>
                    <div class="stat-sub">已确认持仓</div>
                </div>
            </el-card>
            <el-card shadow="hover" class="stat-card">
                <div class="stat-card-inner">
                    <div class="stat-label">证券现金</div>
                    <div class="stat-value">{{ formatMoney(dashboard.securities_cash) }}</div>
                    <div class="stat-sub">交易自动联动</div>
                </div>
            </el-card>
            <el-card shadow="hover" class="stat-card">
                <div class="stat-card-inner">
                    <div class="stat-label">银行存款</div>
                    <div class="stat-value">{{ formatMoney(dashboard.bank_balance) }}</div>
                    <div class="stat-sub">表内存款合计</div>
                </div>
            </el-card>
            <el-card shadow="hover" class="stat-card stat-profit">
                <div class="stat-card-inner">
                    <div class="stat-label">投资账户持仓浮盈</div>
                    <div class="stat-value" :style="{ color: dashboard.total_profit >= 0 ? '#F56C6C' : '#67C23A' }">
                        {{ formatMoney(dashboard.total_profit) }}
                    </div>
                    <div class="stat-sub">普通成本当前仓；不含已卖出已实现</div>
                </div>
            </el-card>
            <el-card shadow="hover" class="stat-card stat-lifetime">
                <div class="stat-card-inner">
                    <div class="stat-label">投资账户全周期盈亏</div>
                    <div class="stat-value" :style="{ color: (dashboard.lifetime_profit ?? 0) >= 0 ? '#F56C6C' : '#67C23A' }">
                        {{ formatMoney(dashboard.lifetime_profit) }}
                    </div>
                    <div class="stat-sub">摊薄成本口径；接近券商累计盈亏</div>
                </div>
            </el-card>
        </div>

        <div class="home-status-strip">
            <el-card shadow="never" class="home-status-card">
                <div class="home-status-label">最新价同步</div>
                <div class="home-status-main" :class="dashboard.price_stale ? 'is-warn' : ''">{{ latestPriceStatusText }}</div>
                <div class="home-status-sub">取持仓最新更新时间</div>
            </el-card>
            <el-card shadow="never" class="home-status-card">
                <div class="home-status-label">今日快照</div>
                <div class="home-status-main" :class="todaySnapshotDone ? 'is-ok' : 'is-warn'">{{ todaySnapshotDone ? '已记录' : '未记录' }}</div>
                <div class="home-status-sub">最新快照：{{ dashboard.latest_snapshot_date || '暂无' }}</div>
            </el-card>
            <el-card shadow="never" class="home-status-card">
                <div class="home-status-label">最近备份</div>
                <div class="home-status-main">{{ latestBackupText }}</div>
                <div class="home-status-sub">备份数：{{ maintenanceStatus.backup_count || 0 }}</div>
            </el-card>
        </div>

        <el-alert
            v-if="Number(dashboard.pending_purchase || 0) > 0"
            type="warning"
            show-icon
            :closable="false"
            class="mt-20"
        >
            <template #title>
                <span>
                    当前有 {{ dashboard.pending_count || pendingTransactions.length || 0 }} 笔申购在途，金额 {{ formatMoney(dashboard.pending_purchase) }}。确认份额/净值后，请到交易管理把对应记录从“申购待确认”改为“买入”。
                </span>
                <el-button type="warning" link style="margin-left: 12px;" @click="goPendingTransactions">查看在途交易</el-button>
            </template>
        </el-alert>
</template>

<script setup>
import { useAppCtx } from '../composables/useAppCtx.js';
const { dashboard, maintenanceStatus, todaySnapshotDone, latestPriceStatusText, latestBackupText, pendingTransactions, goPendingTransactions, formatMoney } = useAppCtx();
</script>
