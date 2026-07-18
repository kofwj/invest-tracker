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
        await Promise.all([
            fetchData(),
            queryTransactions(),
            queryCashFlows(),
            fetchSnapshots(),
            fetchMaintenance(),
        ]);
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
        await bootstrapAfterAuth();
    };

    return {
        bootstrapAfterAuth,
        setupOnMounted,
    };
};

export { createAppInit };
export default createAppInit;
