import { defineStore } from 'pinia';
import { ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import api from '../api/index.js';

export const useAuthStore = defineStore('auth', () => {
  const getInitialMask = () => {
    if (typeof window === 'undefined') return false;
    const params = new URLSearchParams(window.location.search);
    return params.get('mask') === '1' || params.get('screenshot') === '1';
  };

  const isMasked = ref(getInitialMask());
  if (typeof document !== 'undefined') {
    if (isMasked.value) {
      document.documentElement.classList.add('screenshot-mask');
    } else {
      document.documentElement.classList.remove('screenshot-mask');
    }
  }

  const toggleMask = () => {
    isMasked.value = !isMasked.value;
    if (typeof document !== 'undefined') {
      if (isMasked.value) {
        document.documentElement.classList.add('screenshot-mask');
      } else {
        document.documentElement.classList.remove('screenshot-mask');
      }
    }
  };

  const showLoginOverlay = ref(false);
  const loginLoading = ref(false);
  const loginPassword = ref('');
  const loginError = ref('');
  const authEnabled = ref(false);
  const sessionExpired = ref(false);

  let onUnlockedCallback = null;
  const setOnUnlocked = (fn) => {
    onUnlockedCallback = fn;
  };

  const showMessage = (type, text) => {
    try {
      if (type === 'success') ElMessage.success(text);
      else if (type === 'warning') ElMessage.warning(text);
      else ElMessage.error(text);
    } catch (err) {
      console.error('ElMessage failed', err);
      if (typeof alert !== 'undefined') alert(text);
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
      if (typeof localStorage !== 'undefined') {
        localStorage.setItem('invest_tracker_token', token);
      }
      showLoginOverlay.value = false;
      loginPassword.value = '';
      loginError.value = '';
      showMessage('success', '解锁成功');
      if (typeof onUnlockedCallback === 'function') {
        await onUnlockedCallback();
      }
    } catch (e) {
      console.error('登录出现异常:', e);
      let detail = e?.response?.data?.detail || e?.message || '密码错误或网络异常';
      if (Array.isArray(detail)) {
        detail = detail.map((x) => x?.msg || x?.message || String(x)).join('；');
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
    if (typeof localStorage !== 'undefined') {
      localStorage.removeItem('invest_tracker_token');
    }
    showLoginOverlay.value = true;
    ElMessage.success('已安全退出');
  };

  if (typeof window !== 'undefined') {
    window.onAuthRequired = () => {
      if (authEnabled.value) {
        sessionExpired.value = false;
        showLoginOverlay.value = true;
      } else {
        showLoginOverlay.value = false;
        sessionExpired.value = true;
      }
    };
  }

  const reloadForRelogin = () => {
    if (typeof window !== 'undefined') {
      window.location.reload();
    }
  };

  watch(
    showLoginOverlay,
    (visible) => {
      if (typeof document === 'undefined') return;
      if (visible) {
        document.documentElement.classList.remove('screenshot-mask');
      } else if (isMasked.value) {
        document.documentElement.classList.add('screenshot-mask');
      }
    },
    { immediate: true }
  );

  return {
    isMasked,
    toggleMask,
    showLoginOverlay,
    loginLoading,
    loginPassword,
    loginError,
    authEnabled,
    sessionExpired,
    handleLogin,
    handleLogout,
    reloadForRelogin,
    showMessage,
    setOnUnlocked,
  };
});
