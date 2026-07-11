import { ref, watch } from 'vue/dist/vue.esm-bundler.js';
import { ElMessage } from 'element-plus';
import api from '../api/index.js';

/**
 * Login overlay + privacy mask helpers.
 * Keeps HTML template field names stable (isMasked, showLoginOverlay, ...).
 */
export function createAuthMask({ onUnlocked } = {}) {
    const screenshotParams = new URLSearchParams(window.location.search);
    const isMasked = ref(screenshotParams.get('mask') !== '0' && screenshotParams.get('screenshot') !== '0');
    if (isMasked.value) {
        document.documentElement.classList.add('screenshot-mask');
    } else {
        document.documentElement.classList.remove('screenshot-mask');
    }

    const toggleMask = () => {
        isMasked.value = !isMasked.value;
        if (isMasked.value) {
            document.documentElement.classList.add('screenshot-mask');
        } else {
            document.documentElement.classList.remove('screenshot-mask');
        }
    };

    const showLoginOverlay = ref(false);
    const loginLoading = ref(false);
    const loginPassword = ref('');
    const loginError = ref('');
    const authEnabled = ref(false);

    const showMessage = (type, text) => {
        try {
            if (type === 'success') ElMessage.success(text);
            else if (type === 'warning') ElMessage.warning(text);
            else ElMessage.error(text);
        } catch (err) {
            console.error('ElMessage failed', err);
            alert(text);
        }
    };

    const handleLogin = async () => {
        loginError.value = '';
        if (!loginPassword.value) {
            loginError.value = '请输入密码';
            showMessage('warning', '请输入密码');
            return;
        }
        loginLoading.value = true;
        try {
            const res = await api.login(loginPassword.value);
            const token = res.data.token;
            localStorage.setItem('invest_tracker_token', token);
            showLoginOverlay.value = false;
            loginPassword.value = '';
            loginError.value = '';
            showMessage('success', '解锁成功');
            if (typeof onUnlocked === 'function') await onUnlocked();
        } catch (e) {
            console.error('登录出现异常:', e);
            let detail = e?.response?.data?.detail || e?.message || '密码错误或网络异常';
            if (Array.isArray(detail)) {
                detail = detail.map(x => x?.msg || x?.message || String(x)).join('；');
            } else if (detail && typeof detail === 'object') {
                detail = detail.msg || detail.message || JSON.stringify(detail);
            }
            loginError.value = String(detail);
            showMessage('error', String(detail));
        } finally {
            loginLoading.value = false;
        }
    };

    const handleLogout = () => {
        localStorage.removeItem('invest_tracker_token');
        showLoginOverlay.value = true;
        ElMessage.success('已安全退出');
    };

    window.onAuthRequired = () => {
        showLoginOverlay.value = true;
    };

    // Login gate must never look "garbled": drop privacy blur while overlay is visible.
    watch(showLoginOverlay, (visible) => {
        if (visible) {
            document.documentElement.classList.remove('screenshot-mask');
        } else if (isMasked.value) {
            document.documentElement.classList.add('screenshot-mask');
        }
    }, { immediate: true });

    return {
        isMasked,
        toggleMask,
        showLoginOverlay,
        loginLoading,
        loginPassword,
        loginError,
        authEnabled,
        handleLogin,
        handleLogout,
        showMessage,
    };
}
