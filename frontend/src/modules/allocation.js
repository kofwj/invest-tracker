import { formatMoney } from '../utils/index.js';
import { computed, ref } from 'vue';
import api from '../api/index.js';

/**
 * Allocation analysis + summary + health + chart rendering.
 * Health thresholds come from GET /allocation/story (discipline_policy), not hardcoded.
 */
const createAllocationModule = ({
    holdings,
    deposits,
    dashboard,
    pendingTransactions,
    allocationAnalysis,
    macroAllocationAnalysis,
    portfolioExpectedReturn,
    allocationStory,
    allocationStoryLoading,
}) => {
    const defaultExpectedReturns = {
        'A股权益': 6.0,
        'A股ETF': 5.0,
        '港股ETF': 5.0,
        '债基': 2.5,
        'REITs': 4.5,
        '黄金': 4.0,
        '银行存款': 2.0,
        '证券现金': 0.0,
        '未分类': 3.0,
    };

    const getMacroGroup = (cat) => {
        if (cat === '债基') return '固收';
        if (cat === '银行存款') return '存款';
        return '权益';
    };

    const calculateAllocationAnalysis = () => {
        const categories = {};
        const macroGroups = {
            '权益': { amount: 0, cost: 0, profit: 0, lifetime_profit: 0, weighted_expected_return_sum: 0, total_weight: 0, details: new Set() },
            '固收': { amount: 0, cost: 0, profit: 0, lifetime_profit: 0, weighted_expected_return_sum: 0, total_weight: 0, details: new Set() },
            '存款': { amount: 0, cost: 0, profit: 0, lifetime_profit: 0, weighted_expected_return_sum: 0, total_weight: 0, details: new Set() },
        };
        let totalValue = 0;

        holdings.value.forEach(h => {
            const cat = h.category || '未分类';
            const value = h.quantity * h.last_price;
            const cost = h.quantity * h.avg_cost;
            const profit = value - cost + (h.total_dividend || 0);
            const diluted = (h.diluted_cost != null && h.diluted_cost !== '') ? Number(h.diluted_cost) : Number(h.avg_cost || 0);
            const lifetime = (Number(h.last_price || 0) - diluted) * Number(h.quantity || 0);

            totalValue += value;

            if (!categories[cat]) {
                categories[cat] = {
                    market_value: 0,
                    cost: 0,
                    profit: 0,
                    lifetime_profit: 0,
                    count: 0,
                    weighted_expected_return_sum: 0,
                    total_weight: 0,
                };
            }

            categories[cat].market_value += value;
            categories[cat].cost += cost;
            categories[cat].profit += profit;
            categories[cat].lifetime_profit += lifetime;
            categories[cat].count += 1;

            const expectedReturn = (h.expected_return != null && h.expected_return !== '')
                ? Number(h.expected_return)
                : (defaultExpectedReturns[cat] || defaultExpectedReturns['未分类']);
            categories[cat].weighted_expected_return_sum += expectedReturn * value;
            categories[cat].total_weight += value;

            const macro = macroGroups[getMacroGroup(cat)];
            macro.amount += value;
            macro.cost += cost;
            macro.profit += profit;
            macro.lifetime_profit += lifetime;
            macro.weighted_expected_return_sum += expectedReturn * value;
            macro.total_weight += value;
            macro.details.add(cat);
        });

        const addSyntheticCategory = (cat, value, expectedReturn, detailCount = 1) => {
            if (value <= 0) return;
            if (!categories[cat]) {
                categories[cat] = { market_value: 0, cost: 0, profit: 0, lifetime_profit: 0, count: 0, weighted_expected_return_sum: 0, total_weight: 0 };
            }
            categories[cat].market_value += value;
            categories[cat].cost += value;
            categories[cat].profit += 0;
            categories[cat].lifetime_profit = (categories[cat].lifetime_profit || 0) + 0;
            categories[cat].count += detailCount;
            categories[cat].weighted_expected_return_sum += expectedReturn * value;
            categories[cat].total_weight += value;
        };

        const bankBalance = Number(dashboard.value.bank_balance || 0);
        if (bankBalance > 0) {
            addSyntheticCategory('银行存款', bankBalance, defaultExpectedReturns['银行存款'], deposits.value.length || 1);
            macroGroups['存款'].amount += bankBalance;
            macroGroups['存款'].cost += bankBalance;
            macroGroups['存款'].weighted_expected_return_sum += defaultExpectedReturns['银行存款'] * bankBalance;
            macroGroups['存款'].total_weight += bankBalance;
            macroGroups['存款'].details.add('银行存款');
        }

        const securitiesCash = Number(dashboard.value.securities_cash || 0);
        if (securitiesCash > 0) {
            addSyntheticCategory('证券现金', securitiesCash, defaultExpectedReturns['证券现金'], 1);
            macroGroups['固收'].amount += securitiesCash;
            macroGroups['固收'].cost += securitiesCash;
            macroGroups['固收'].weighted_expected_return_sum += defaultExpectedReturns['证券现金'] * securitiesCash;
            macroGroups['固收'].total_weight += securitiesCash;
            macroGroups['固收'].details.add('证券现金');
        }

        const pendingPurchase = Number(dashboard.value.pending_purchase || 0);
        if (pendingPurchase > 0) {
            const pendingCount = Math.max(1, Number(dashboard.value.pending_count || 0));
            addSyntheticCategory('基金申购在途', pendingPurchase, defaultExpectedReturns['债基'], pendingCount);
            macroGroups['固收'].amount += pendingPurchase;
            macroGroups['固收'].cost += pendingPurchase;
            macroGroups['固收'].weighted_expected_return_sum += defaultExpectedReturns['债基'] * pendingPurchase;
            macroGroups['固收'].total_weight += pendingPurchase;
            macroGroups['固收'].details.add('基金申购在途');
        }

        if (dashboard.value.total_assets) {
            totalValue = dashboard.value.total_assets;
        }

        allocationAnalysis.value = Object.keys(categories).map(cat => {
            const data = categories[cat];
            const expectedReturn = data.total_weight > 0
                ? data.weighted_expected_return_sum / data.total_weight
                : (defaultExpectedReturns[cat] || defaultExpectedReturns['未分类']);

            return {
                category: cat,
                market_value: data.market_value,
                percentage: totalValue > 0 ? (data.market_value / totalValue) * 100 : 0,
                profit: data.profit,
                lifetime_profit: data.lifetime_profit || 0,
                profit_rate: data.cost > 0 ? (data.profit / data.cost) * 100 : 0,
                count: data.count,
                expected_annual_return: expectedReturn,
            };
        }).sort((a, b) => b.market_value - a.market_value);

        macroAllocationAnalysis.value = ['权益', '固收', '存款'].map(group => {
            const data = macroGroups[group];
            return {
                group,
                amount: data.amount,
                percentage: totalValue > 0 ? (data.amount / totalValue) * 100 : 0,
                profit: data.profit,
                lifetime_profit: data.lifetime_profit || 0,
                profit_rate: data.cost > 0 ? (data.profit / data.cost) * 100 : 0,
                expected_return: data.total_weight > 0 ? data.weighted_expected_return_sum / data.total_weight : 0,
                detail: Array.from(data.details).join('、') || '—',
            };
        });

        let weightedSum = 0;
        let totalWeight = 0;
        macroAllocationAnalysis.value.forEach(item => {
            weightedSum += item.expected_return * item.amount;
            totalWeight += item.amount;
        });
        portfolioExpectedReturn.value = totalWeight > 0 ? weightedSum / totalWeight : 0;
    };

    const emptyStory = () => ({
        headline: '',
        severity: 'ok',
        bullets: [],
        policy: null,
        snapshot: null,
        gaps: null,
        health: [],
        issues: [],
        concentration: null,
        homogeneity: { groups: [], note: '' },
        profit_dependency: null,
        liquidity: null,
        scenarios: [],
        discipline_summary: '',
        open_draft_count: 0,
    });

    if (allocationStory && allocationStory.value == null) {
        allocationStory.value = emptyStory();
    }

    const fetchAllocationStory = async () => {
        if (allocationStoryLoading) allocationStoryLoading.value = true;
        try {
            const res = await api.allocationStory();
            allocationStory.value = res.data || emptyStory();
        } catch (e) {
            console.warn('allocation story failed', e);
            // keep last good story if any
            if (!allocationStory.value) allocationStory.value = emptyStory();
        } finally {
            if (allocationStoryLoading) allocationStoryLoading.value = false;
        }
    };

    const storySnap = computed(() => allocationStory?.value?.snapshot || null);
    const storyPolicy = computed(() => allocationStory?.value?.policy || null);

    const allocationSummary = computed(() => {
        const snap = storySnap.value;
        const total = Number(snap?.total_assets ?? dashboard.value.total_assets ?? 0);
        if (snap) {
            const equityAmount = Number(snap.equity_mv || 0);
            const fixedAmount = Number(snap.fixed_mv || 0);
            const depositAmount = Number(snap.deposit_mv || 0);
            const defensiveAmount = fixedAmount + depositAmount;
            // defensive_pct from backend may include defensive_extra
            const equityRatio = Number(snap.equity_pct || 0);
            const defensiveRatio = Number(snap.defensive_pct || 0);
            const comment = allocationStory.value?.headline
                || allocationStory.value?.discipline_summary
                || '当前配置结论加载中…';
            return {
                total,
                equityAmount,
                equityRatio,
                defensiveAmount,
                defensiveRatio,
                fixedAmount,
                depositAmount,
                comment,
            };
        }
        // Fallback before story loads: pie-side macro only (no threshold commentary).
        const getGroup = (name) => macroAllocationAnalysis.value.find(x => x.group === name) || { amount: 0, percentage: 0 };
        const equity = getGroup('权益');
        const fixed = getGroup('固收');
        const deposit = getGroup('存款');
        const defensiveAmount = Number(fixed.amount || 0) + Number(deposit.amount || 0);
        return {
            total,
            equityAmount: Number(equity.amount || 0),
            equityRatio: Number(equity.percentage || 0),
            defensiveAmount,
            defensiveRatio: total > 0 ? defensiveAmount / total * 100 : 0,
            fixedAmount: Number(fixed.amount || 0),
            depositAmount: Number(deposit.amount || 0),
            comment: '正在加载配置诊断…',
        };
    });

    const allocationHealth = computed(() => {
        const list = allocationStory?.value?.health;
        if (Array.isArray(list) && list.length) {
            return list.map((item) => ({
                label: item.label,
                status: item.status,
                type: item.type || (item.level === 'warning' ? 'warning' : item.level === 'info' ? 'info' : 'success'),
                text: item.text,
                level: item.level,
                code: item.code,
            }));
        }
        return [];
    });

    const renderAllocationCharts = async () => {
        const { renderAllocationChartsView, waitForChartDom } = await import('../charts/index.js');
        // lazy tab + 异步 SFC：单次 nextTick 时 #allocationChart 往往还没挂上
        const ready = await waitForChartDom(['allocationChart', 'categoryChart']);
        if (!ready) return;
        // 再等一帧，避免容器宽高仍为 0
        await new Promise((r) => requestAnimationFrame(() => r()));
        renderAllocationChartsView(macroAllocationAnalysis.value, allocationAnalysis.value);
    };

    return {
        calculateAllocationAnalysis,
        allocationSummary,
        allocationHealth,
        renderAllocationCharts,
        fetchAllocationStory,
        storyPolicy,
    };
};

export { createAllocationModule };
export default createAllocationModule;
