<template>
        <div class="header">
            <h2>投资资产管理系统</h2>
            <div class="header-actions">
                <el-button :type="isMasked ? 'danger' : 'info'" plain @click="toggleMask">
                    {{ isMasked ? '显示数据' : '隐藏数据' }}
                </el-button>
                <el-button type="success" @click="fetchData">刷新数据</el-button>
                <el-button type="primary" @click="syncPrices" :loading="syncing">同步最新价</el-button>
                <el-button type="warning" plain @click="syncTrailingReturns" :loading="trailingSyncing">同步近一年收益率</el-button>
                <el-button type="success" plain @click="openDividendDraftDialog" :loading="dividendLoading">分红草稿</el-button>
                <el-button v-if="authEnabled" type="info" link @click="handleLogout" style="margin-left: 8px;">
                    退出登录
                </el-button>
                <span v-if="syncNotice.text" class="inline-sync-status" :class="syncNotice.type">{{ syncNotice.text }}</span>
            </div>
        </div>
</template>

<script setup>
import { useAppCtx } from '../composables/useAppCtx.js';
const { isMasked, toggleMask, authEnabled, handleLogout, syncing, trailingSyncing, syncNotice, dividendLoading, syncPrices, syncTrailingReturns, openDividendDraftDialog, fetchData } = useAppCtx();
</script>
