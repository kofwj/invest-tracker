<template>
        <!-- 登录锁屏遮罩 -->
        <div v-if="showLoginOverlay" class="login-overlay" role="dialog" aria-modal="true" aria-label="系统登录">
            <div class="login-box">
                <div class="login-logo" aria-hidden="true">投</div>
                <h3>投资资产管理系统</h3>
                <p class="login-subtitle">请输入访问密码以继续</p>
                <form @submit.prevent="handleLogin" style="margin-top: 24px;" autocomplete="on">
                    <div class="login-field">
                        <label class="login-field-label" for="login-password-input">访问密码</label>
                        <input
                            id="login-password-input"
                            v-model="loginPassword"
                            type="password"
                            class="login-native-input"
                            placeholder="请输入系统访问密码"
                            autocomplete="current-password"
                            autofocus
                            required
                            lang="zh-CN"
                        >
                    </div>
                    <p class="login-error" v-if="loginError">{{ loginError }}</p>
                    <button type="submit" class="login-native-button" :disabled="loginLoading">
                        {{ loginLoading ? '正在验证...' : '登录' }}
                    </button>
                </form>
            </div>
        </div>
</template>

<script setup>
import { useAppCtx } from '../composables/useAppCtx.js';
const { showLoginOverlay, loginLoading, loginPassword, loginError, handleLogin } = useAppCtx();
</script>
