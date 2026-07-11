import axios from 'axios';

const API = '/api';

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
    (response) => response,
    (error) => {
        if (error.response && error.response.status === 401) {
            localStorage.removeItem('invest_tracker_token');
            if (typeof window.onAuthRequired === 'function') {
                window.onAuthRequired();
            }
        }
        return Promise.reject(error);
    }
);

const api = {
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

    createSnapshot: () => axios.post(API + '/snapshots'),
    listSnapshots: (range = []) => {
        let url = API + '/snapshots';
        if (range && range.length === 2) url += `?start_date=${range[0]}&end_date=${range[1]}`;
        return axios.get(url);
    },
    snapshotSummary: (range = []) => axios.get(API + `/snapshots/summary?start_date=${range[0]}&end_date=${range[1]}`),
    compactSnapshots: () => axios.post(API + '/snapshots/compact'),

    maintenanceStatus: () => axios.get(API + '/maintenance/status'),
    listBackups: () => axios.get(API + '/maintenance/backups'),
    createBackup: () => axios.post(API + '/maintenance/backups'),
    restoreBackup: (filename) => axios.post(API + '/maintenance/restore', { filename }),
    restoreUploadedBackup: (formData) => axios.post(API + '/maintenance/restore-upload', formData, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 180000 }),
    deleteBackup: (filename) => axios.delete(API + '/maintenance/backups/' + encodeURIComponent(filename)),

    performanceSummary: () => axios.get(API + '/performance/summary'),
    performanceTimeline: () => axios.get(API + '/performance/timeline'),
    performanceContribution: () => axios.get(API + '/performance/contribution'),
    listPortfolioCashFlows: () => axios.get(API + '/portfolio-cash-flows'),
    addPortfolioCashFlow: (payload) => axios.post(API + '/portfolio-cash-flows', payload),
    deletePortfolioCashFlow: (id) => axios.delete(API + '/portfolio-cash-flows/' + id),

    download: (url) => axios.get(API + url, { responseType: 'blob' }),
    uploadCsv: (url, formData) => axios.post(API + url, formData, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 180000 }),
};

Object.assign(window, { API, api });

export { API, api };
export default api;
