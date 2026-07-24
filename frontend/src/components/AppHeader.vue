<template>
        <div class="header">
            <div class="header-brand">
                <h2>投资资产管理系统</h2>
            </div>
            <div class="header-actions">
                <el-button type="success" @click="fetchData">刷新数据</el-button>
                <el-button type="primary" @click="syncPrices" :loading="syncing">同步最新价</el-button>
                <el-button v-if="authEnabled" plain @click="handleLogout">退出登录</el-button>
                <span v-if="syncNotice.text" class="inline-sync-status" :class="syncNotice.type">{{ syncNotice.text }}</span>
            </div>
        </div>
</template>

<script setup>
import { useAppCtx } from '../composables/useAppCtx.js';
const {
    authEnabled, handleLogout, syncing, syncNotice,
    syncPrices, fetchData,
} = useAppCtx();
</script>
