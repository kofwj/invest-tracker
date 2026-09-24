import axios from 'axios';

const API = '/api';

/**
 * oauth2-proxy 会话过期时不会返回 401：Caddy 的 forward_auth 会 302 到 /oauth2/sign_in，
 * 而 XHR 自动跟随 302 —— axios 最终拿到的是 **200 的登录页 HTML**（实测 46KB、
 * content-type: text/html）。此时 axios 认为请求成功，dashboard.value 被赋成一段 HTML，
 * 页面所有数字变成 undefined/0，却没有任何登录提示。所以对 /api/* 的响应补一层
 * content-type 校验兜底。
 */
const SESSION_EXPIRED_MESSAGE = '登录状态已过期，请重新登录';

const isApiUrl = (url) => typeof url === 'string' && url.includes(API + '/');

const looksLikeHtml = (response) => {
    const contentType = response?.headers?.['content-type'];
    return typeof contentType === 'string' && contentType.toLowerCase().includes('text/html');
};

const notifyAuthRequired = () => {
    localStorage.removeItem('invest_tracker_token');
    if (typeof window !== 'undefined' && typeof window.onAuthRequired === 'function') {
        window.onAuthRequired();
    }
};

const sessionExpiredError = (response) => {
    const err = new Error(SESSION_EXPIRED_MESSAGE);
    err.isSessionExpired = true;
    err.response = response;
    err.config = response?.config;
    return err;
};

// 兜底超时：没单独声明 timeout 的接口原先可能一直挂着（表现为按钮永远转圈）。
// 需要更久的接口（同步价 120s / 同步收益率 180s / K线 180s / 导入导出 180s）
// 都显式声明了自己的 timeout，会覆盖这个默认值。
axios.defaults.timeout = 60000;

// 注册请求与响应拦截器处理身份校验
axios.interceptors.request.use(
    (config) => {
        const token = localStorage.getItem('invest_tracker_token');
        if (token) {
            config.headers['Authorization'] = `Bearer ${token}`;
        }
        return config;
    },
    (error) => Promise.reject(error)
);

axios.interceptors.response.use(
    (response) => {
        // 会话失效被伪装成 200 HTML —— 必须当成失败，否则页面静默显示空数据
        if (isApiUrl(response?.config?.url) && looksLikeHtml(response)) {
            notifyAuthRequired();
            return Promise.reject(sessionExpiredError(response));
        }
        return response;
    },
    (error) => {
        if (error.response && error.response.status === 401) {
            notifyAuthRequired();
        }
        return Promise.reject(error);
    }
);

const api = {
    getHealth: () => axios.get(API + '/health'),
    getAuthStatus: () => axios.get(API + '/auth/status'),
    login: (password) => axios.post(API + '/login', { password }),
    getDashboard: () => axios.get(API + '/dashboard'),
    getHoldings: () => axios.get(API + '/holdings'),
    getDeposits: () => axios.get(API + '/deposits'),
    getSecuritiesCash: () => axios.get(API + '/securities-cash'),
    getFeeSettings: () => axios.get(API + '/fee-settings'),
    updateFeeSettings: (payload) => axios.put(API + '/fee-settings', payload),
    resetFeeSettings: () => axios.post(API + '/fee-settings/reset'),

    syncPrices: () => axios.post(API + '/sync-prices', null, { timeout: 120000 }),
    syncTrailingReturns: () => axios.post(API + '/sync-trailing-returns', null, { timeout: 180000 }),
    scanDividends: (payload = {}) => axios.post(API + '/dividends/scan', payload, { timeout: 180000 }),
    confirmDividends: (payload) => axios.post(API + '/dividends/confirm', payload, { timeout: 120000 }),
    downloadDividendTemplate: () => axios.get(API + '/dividends/template', { responseType: 'blob' }),
    importDividends: (formData) => axios.post(API + '/dividends/import', formData, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 180000 }),

    addTransaction: (payload) => axios.post(API + '/transactions', payload),
    listTransactions: (params = {}) => {
        const qs = new URLSearchParams();
        Object.entries(params || {}).forEach(([key, value]) => {
            if (value !== undefined && value !== null && value !== '') qs.set(key, value);
        });
        return axios.get(API + '/transactions' + (qs.toString() ? '?' + qs.toString() : ''));
    },
    listTransactionsByCode: (code) => axios.get(API + '/transactions?legacy=1&code=' + encodeURIComponent(code)),
    exportTransactions: (params = {}) => {
        const qs = new URLSearchParams();
        Object.entries(params || {}).forEach(([key, value]) => {
            if (value !== undefined && value !== null && value !== '') qs.set(key, value);
        });
        return axios.get(API + '/transactions/export' + (qs.toString() ? '?' + qs.toString() : ''), { responseType: 'blob' });
    },
    updateTransaction: (id, payload) => axios.put(API + '/transactions/' + id, payload),
    deleteTransaction: (id) => axios.delete(API + '/transactions/' + id),

    addDeposit: (payload) => axios.post(API + '/deposits', payload),
    updateDeposit: (id, payload) => axios.put(API + '/deposits/' + id, payload),
    deleteDeposit: (id) => axios.delete(API + '/deposits/' + id),

    updateSecuritiesCash: (amount) => axios.put(API + '/securities-cash', { amount }),
    listCashFlows: (params = []) => axios.get(API + '/cash-flows' + (params.length ? '?' + params.join('&') : '')),
    addCashFlow: (payload) => axios.post(API + '/cash-flows', payload),
    updateCashFlow: (id, payload) => axios.put(API + '/cash-flows/' + id, payload),
    deleteCashFlow: (id) => axios.delete(API + '/cash-flows/' + id),

    updateExpectedReturn: (code, expected_return) => axios.put(API + '/holdings/' + encodeURIComponent(code), { expected_return }),
    addHoldingCorrection: (payload) => axios.post(API + '/holding-corrections', payload),
    listHoldingCorrections: (code) => axios.get(API + '/holding-corrections?code=' + encodeURIComponent(code)),
    deleteHoldingCorrection: (id) => axios.delete(API + '/holding-corrections/' + id),

    getKlines: (code, days = 120) => axios.get(API + '/klines/' + encodeURIComponent(code) + '?days=' + days, { timeout: 30000 }),
    syncKlines: (payload = {}) => axios.post(API + '/klines/sync', payload, { timeout: 180000 }),
    fundamentalCheck: (code) => axios.get(API + '/analysis/' + encodeURIComponent(code), { timeout: 45000 }),

    // force=true 用于「最新价不是今天的」被 409 拦住后，用户确认强制记录
    createSnapshot: (force = false) => axios.post(API + '/snapshots' + (force ? '?force=true' : '')),
    // 手动填价：数据源全挂时的兜底。后端会同时把「价格同步时间」刷成现在，
    // 视为人工确认了今天的价（快照闸门因此放行）。
    setHoldingPrice: (code, price, note = '') => axios.put(API + '/holdings/' + encodeURIComponent(code) + '/price', { price, note }),
    listSnapshots: (range = []) => {
        let url = API + '/snapshots';
        if (range && range.length === 2) url += `?start_date=${range[0]}&end_date=${range[1]}`;
        return axios.get(url);
    },
    snapshotSummary: (range = []) => axios.get(API + `/snapshots/summary?start_date=${range[0]}&end_date=${range[1]}`),
    compactSnapshots: () => axios.post(API + '/snapshots/compact'),
    saveReconcile: (payload) => axios.post(API + '/snapshots/reconcile', payload),
    getReconcile: () => axios.get(API + '/snapshots/reconcile'),

    maintenanceStatus: () => axios.get(API + '/maintenance/status'),
    listBackups: () => axios.get(API + '/maintenance/backups'),
    createBackup: () => axios.post(API + '/maintenance/backups'),
    restoreBackup: (filename) => axios.post(API + '/maintenance/restore', { filename }),
    restoreUploadedBackup: (formData) => axios.post(API + '/maintenance/restore-upload', formData, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 180000 }),
    deleteBackup: (filename) => axios.delete(API + '/maintenance/backups/' + encodeURIComponent(filename)),

    // 分析类接口统一 45s 超时：/performance/summary 内部会算基准指数相对收益，
    // 没有超时的话外网卡住会让按钮一直转圈（表现为"刷新不出来"）。
    performanceSummary: (params = {}) => axios.get(API + '/performance/summary', { params, timeout: 45000 }),
    performanceWindows: () => axios.get(API + '/performance/windows', { timeout: 45000 }),
    performanceTimeline: (params = {}) => axios.get(API + '/performance/timeline', { params, timeout: 45000 }),
    performanceContribution: () => axios.get(API + '/performance/contribution', { timeout: 45000 }),
    performanceStory: (params = {}) => axios.get(API + '/performance/story', { params, timeout: 45000 }),
    allocationStory: () => axios.get(API + '/allocation/story', { timeout: 60000 }),
    listPortfolioCashFlows: (params = {}) => axios.get(API + '/portfolio-cash-flows', { params }),
    addPortfolioCashFlow: (payload) => axios.post(API + '/portfolio-cash-flows', payload),
    updatePortfolioCashFlow: (id, payload) => axios.put(API + '/portfolio-cash-flows/' + id, payload),
    deletePortfolioCashFlow: (id) => axios.delete(API + '/portfolio-cash-flows/' + id),
    portfolioCashFlowSuggest: () => axios.get(API + '/portfolio-cash-flows/suggest'),
    eveningBrief: () => axios.get(API + '/evening-brief'),
    eveningBriefNotify: () => axios.post(API + '/evening-brief/notify'),

    brokerReconcilePreview: (formData) => axios.post(API + '/broker-reconcile/preview', formData, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120000 }),
    brokerReconcileApply: (payload) => axios.post(API + '/broker-reconcile/apply', payload || {}, { timeout: 120000 }),
    brokerReconcileHistory: (limit = 20) => axios.get(API + '/broker-reconcile/history?limit=' + encodeURIComponent(limit)),
    brokerCashAudit: (params = {}) => axios.get(API + '/broker-reconcile/cash-audit', { params }),

    getMarketSummary: () => axios.get(API + '/market/summary', { timeout: 60000 }),
    getTradingDay: (date) => axios.get(API + '/market/trading-day' + (date ? ('?date=' + encodeURIComponent(date)) : '')),
    getWatchlist: () => axios.get(API + '/market/watchlist'),
    saveWatchlist: (payload) => axios.put(API + '/market/watchlist', payload || { items: [] }),
    listAlertRules: () => axios.get(API + '/market/alert-rules'),
    createAlertRule: (payload) => axios.post(API + '/market/alert-rules', payload),
    updateAlertRule: (id, payload) => axios.put(API + '/market/alert-rules/' + id, payload),
    deleteAlertRule: (id) => axios.delete(API + '/market/alert-rules/' + id),
    listAlertEvents: (params = {}) => {
        const qs = new URLSearchParams();
        Object.entries(params || {}).forEach(([key, value]) => {
            if (value !== undefined && value !== null && value !== '') qs.set(key, value);
        });
        return axios.get(API + '/market/alert-events' + (qs.toString() ? '?' + qs.toString() : ''));
    },
    exportAlertEvents: (params = {}) => {
        const qs = new URLSearchParams();
        Object.entries(params || {}).forEach(([key, value]) => {
            if (value !== undefined && value !== null && value !== '') qs.set(key, value);
        });
        return axios.get(API + '/market/alert-events/export' + (qs.toString() ? '?' + qs.toString() : ''), { responseType: 'blob' });
    },
    clearAlertEvents: (payload = {}) => axios.post(API + '/market/alert-events/clear', payload || {}),
    checkAlerts: (payload = {}) => axios.post(API + '/market/alerts/check', payload || {}, { timeout: 60000 }),

    getNotifyStatus: () => axios.get(API + '/notify/status'),
    saveNotifySettings: (payload) => axios.put(API + '/notify/settings', payload || {}),
    listNotifyLogs: (limit = 20) => axios.get(API + '/notify/logs?limit=' + encodeURIComponent(limit)),
    testNotify: (payload = {}) => axios.post(API + '/notify/test', payload || {}),
    getNotifyDepositDue: () => axios.get(API + '/notify/deposit-due'),
    pushNotifyDepositDue: (force = false) => axios.post(API + '/notify/deposit-due?force=' + (force ? 'true' : 'false')),
    getNotifyDiscipline: () => axios.get(API + '/notify/discipline'),
    pushNotifyDiscipline: (force = false) => axios.post(API + '/notify/discipline?force=' + (force ? 'true' : 'false') + '&only_if_breaches=' + (force ? 'false' : 'true')),
    runNotifyScheduled: (payload = {}) => axios.post(API + '/notify/run', payload || {}),

    getAiStatus: () => axios.get(API + '/ai/status'),
    saveAiConfig: (payload) => axios.put(API + '/ai/config', payload || {}),
    testAi: () => axios.post(API + '/ai/test', {}, { timeout: 125000 }),

    getDisciplineReport: () => axios.get(API + '/discipline/report', { timeout: 60000 }),
    getDisciplinePolicy: () => axios.get(API + '/discipline/policy'),
    saveDisciplinePolicy: (payload) => axios.put(API + '/discipline/policy', payload || {}),
    listDisciplinePresets: () => axios.get(API + '/discipline/presets'),
    applyDisciplinePreset: (presetId) => axios.post(API + '/discipline/presets/apply', { preset_id: presetId }),
    listDisciplineDrafts: (params = {}) => {
        const qs = new URLSearchParams();
        Object.entries(params || {}).forEach(([key, value]) => {
            if (value !== undefined && value !== null && value !== '') qs.set(key, value);
        });
        return axios.get(API + '/discipline/drafts' + (qs.toString() ? '?' + qs.toString() : ''));
    },
    createDisciplineDrafts: (payload = {}) => axios.post(API + '/discipline/drafts', payload || {}),
    updateDisciplineDraft: (id, payload) => axios.put(API + '/discipline/drafts/' + id, payload || {}),
    deleteDisciplineDraft: (id) => axios.delete(API + '/discipline/drafts/' + id),
    confirmDisciplineDraft: (id) => axios.post(API + '/discipline/drafts/' + id + '/confirm'),
    confirmDisciplineDrafts: (payload) => axios.post(API + '/discipline/drafts/confirm', payload || {}),

    download: (url) => axios.get(API + url, { responseType: 'blob' }),
    uploadCsv: (url, formData) => axios.post(API + url, formData, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 180000 }),
};

export { API, api, SESSION_EXPIRED_MESSAGE };

export default api;