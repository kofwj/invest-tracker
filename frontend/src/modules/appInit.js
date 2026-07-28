/**
 * App bootstrap and initialization logic.
 * Extracted from main.js: bootstrapAfterAuth + onMounted auth + initial data loads.
 */
const createAppInit = ({
    api,
    authEnabled,
    showLoginOverlay,
    fetchData,
    queryTransactions,
    queryCashFlows,
    fetchSnapshots,
    fetchMaintenance,
}) => {
    let bootstrapAfterAuth = async () => {};

    const bootstrap = async () => {
        const results = await Promise.allSettled([
            fetchData(),
            queryTransactions(),
            queryCashFlows(),
            fetchSnapshots(),
            fetchMaintenance(),
        ]);
        const failed = results.filter((result) => result.status === 'rejected');
        if (failed.length) {
            console.error('部分初始化数据加载失败', failed.map((result) => result.reason));
        }
    };

    bootstrapAfterAuth = bootstrap;

    const setupOnMounted = async () => {
        try {
            const statusRes = await api.getAuthStatus();
            authEnabled.value = statusRes.data.auth_enabled;
            if (authEnabled.value) {
                const token = localStorage.getItem('invest_tracker_token');
                if (!token) {
                    showLoginOverlay.value = true;
                    return;
                }
            }
        } catch (e) {
            console.error('获取登录状态失败', e);
        }
        try {
            await bootstrapAfterAuth();
        } catch (e) {
            console.error('初始化数据加载失败', e);
        }
    };

    return {
        bootstrapAfterAuth,
        setupOnMounted,
    };
};

export { createAppInit };
export default createAppInit;
