<template>
        <div class="header">
            <div class="header-brand">
                <h2>投资资产管理系统</h2>
                <div class="header-subtitle">真仓账本 · 记清每一笔，再决定怎么调</div>
            </div>
            <div class="header-actions">
                <el-button :type="isMasked ? 'danger' : 'info'" plain @click="toggleMask">
                    {{ isMasked ? '显示数据' : '隐藏数据' }}
                </el-button>
                <el-button type="success" @click="fetchData">刷新数据</el-button>
                <el-button type="primary" @click="syncPrices" :loading="syncing">同步最新价</el-button>
                <el-dropdown trigger="click" @command="onHeaderMore">
                    <el-button plain>
                        更多
                        <span style="margin-left:4px;opacity:.7">▾</span>
                    </el-button>
                    <template #dropdown>
                        <el-dropdown-menu>
                            <el-dropdown-item command="trailing" :disabled="trailingSyncing">同步近一年收益率</el-dropdown-item>
                            <el-dropdown-item command="dividend" :disabled="dividendLoading">分红草稿</el-dropdown-item>
                            <el-dropdown-item command="brief">生成晚间简报</el-dropdown-item>
                            <el-dropdown-item v-if="authEnabled" divided command="logout">退出登录</el-dropdown-item>
                        </el-dropdown-menu>
                    </template>
                </el-dropdown>
                <span v-if="syncNotice.text" class="inline-sync-status" :class="syncNotice.type">{{ syncNotice.text }}</span>
            </div>
        </div>
</template>

<script setup>
import { useAppCtx } from '../composables/useAppCtx.js';
const {
    isMasked, toggleMask, authEnabled, handleLogout, syncing, trailingSyncing, syncNotice,
    dividendLoading, syncPrices, syncTrailingReturns, openDividendDraftDialog, fetchData, openEveningBrief,
} = useAppCtx();

const onHeaderMore = (cmd) => {
    if (cmd === 'trailing') syncTrailingReturns();
    else if (cmd === 'dividend') openDividendDraftDialog();
    else if (cmd === 'brief') openEveningBrief?.();
    else if (cmd === 'logout') handleLogout();
};
</script>
