/**
 * 响应拦截器的会话失效兜底。
 *
 * 背景：oauth2-proxy 会话过期时，Caddy 的 forward_auth 会 302 到 /oauth2/sign_in，
 * XHR 跟随 302 之后 axios 拿到的是 **200 的登录页 HTML**。没有这层校验时，
 * dashboard.value 会被赋成一段 HTML，页面数字全变 undefined/0，且没有任何提示。
 * 生产环境实测过这个响应（200 / text/html / 46KB）。
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import axios from 'axios';
import api, { SESSION_EXPIRED_MESSAGE } from '../src/api/index.js';

const originalAdapter = axios.defaults.adapter;

/** 让底层请求直接返回我们构造的原始响应 */
const stubAdapter = (response) => {
  axios.defaults.adapter = async (config) => ({ ...response, config });
};

beforeEach(() => {
  localStorage.setItem('invest_tracker_token', 'tok');
  window.onAuthRequired = vi.fn();
});

afterEach(() => {
  axios.defaults.adapter = originalAdapter;
  delete window.onAuthRequired;
});

describe('会话失效（200 HTML）', () => {
  it('rejects instead of returning the login page as data', async () => {
    stubAdapter({
      status: 200,
      statusText: 'OK',
      headers: { 'content-type': 'text/html; charset=utf-8' },
      data: '<!DOCTYPE html><html><body>Sign in with GitHub</body></html>',
    });

    await expect(api.getDashboard()).rejects.toThrow(SESSION_EXPIRED_MESSAGE);
  });

  it('clears the token and asks the app to show the login overlay', async () => {
    stubAdapter({
      status: 200,
      statusText: 'OK',
      headers: { 'content-type': 'text/html; charset=utf-8' },
      data: '<html></html>',
    });

    await api.getDashboard().catch(() => {});
    expect(localStorage.getItem('invest_tracker_token')).toBeNull();
    expect(window.onAuthRequired).toHaveBeenCalledTimes(1);
  });

  it('marks the error so callers can tell it apart from a normal failure', async () => {
    stubAdapter({
      status: 200,
      statusText: 'OK',
      headers: { 'content-type': 'text/html' },
      data: '<html></html>',
    });

    const err = await api.getHoldings().catch((e) => e);
    expect(err.isSessionExpired).toBe(true);
  });

  it('does not touch blob/csv downloads (they are not html)', async () => {
    stubAdapter({
      status: 200,
      statusText: 'OK',
      headers: { 'content-type': 'text/csv; charset=utf-8' },
      data: 'date,code\n2026-09-22,600000\n',
    });

    const res = await api.download('/transactions/export');
    expect(res.data).toContain('600000');
    expect(window.onAuthRequired).not.toHaveBeenCalled();
  });

  it('passes normal json responses straight through', async () => {
    stubAdapter({
      status: 200,
      statusText: 'OK',
      headers: { 'content-type': 'application/json' },
      data: { total_assets: 2929620.26 },
    });

    const res = await api.getDashboard();
    expect(res.data.total_assets).toBe(2929620.26);
    expect(window.onAuthRequired).not.toHaveBeenCalled();
  });
});

describe('请求兜底设置', () => {
  it('has a default timeout so a hung request cannot spin forever', () => {
    expect(axios.defaults.timeout).toBe(60000);
  });

  it('still sends the bearer token when present', async () => {
    let seen = null;
    axios.defaults.adapter = async (config) => {
      seen = config;
      return { status: 200, statusText: 'OK', headers: { 'content-type': 'application/json' }, data: {}, config };
    };
    await api.getHealth();
    expect(seen.headers.Authorization).toBe('Bearer tok');
  });
});

describe('会话过期遮罩', () => {
  it('asks the user to re-login instead of showing a password box when app auth is off', async () => {
    const { createApp, h, provide, ref } = await import('vue');
    const LoginOverlay = (await import('../src/components/LoginOverlay.vue')).default;
    const { APP_CTX_KEY } = await import('../src/composables/useAppCtx.js');

    const reloadForRelogin = vi.fn();
    const ctx = {
      showLoginOverlay: ref(false),
      loginLoading: ref(false),
      loginPassword: ref(''),
      loginError: ref(''),
      handleLogin: vi.fn(),
      sessionExpired: ref(true),
      reloadForRelogin,
    };
    const host = document.createElement('div');
    const App = { setup() { provide(APP_CTX_KEY, ctx); return () => h(LoginOverlay); } };
    const app = createApp(App);
    app.mount(host);

    // 密码输入框不该出现（生产没开应用级密码，弹它没意义）
    expect(host.querySelector('#login-password-input')).toBeNull();
    expect(host.textContent).toContain('登录状态已过期');

    const btn = [...host.querySelectorAll('button')].find((b) => b.textContent.includes('重新登录'));
    expect(btn).toBeTruthy();
    btn.click();
    expect(reloadForRelogin).toHaveBeenCalled();

    app.unmount();
  });
});
