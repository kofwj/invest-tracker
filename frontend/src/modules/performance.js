import api from '../api/index.js';
import { formatMoney } from '../utils/index.js';

const createPerformanceModule = ({
    perfSummary,
    perfTimeline,
    perfContribution,
    perfFlows,
    perfLoading,
    perfContributionFilter,
    perfContributionSort,
    perfFlowForm,
    showSyncNotice,
    nextTick,
    computed,
}) => {
    const hasPerfFlows = computed(() => Number(perfSummary.value?.flow_count || 0) > 0);

    const perfGuideSteps = computed(() => ([
        {
            step: '1',
            title: '先看整户赚没赚',
            text: '重点看「你还净投了多少」和「整户一共赚了多少」。这是全组合账，不是单只股票。',
        },
        {
            step: '2',
            title: '再看谁在贡献收益',
            text: '中间贡献表默认按「当前仓浮盈 + 分红」；另有「全周期盈亏」列，接近券商累计，可切换排序。',
        },
        {
            step: '3',
            title: '需要年化时再录流水',
            text: 'XIRR / 准确净投入，依赖底部「组合资金流水」（外部投入/取出）。买卖交易、银证转账不要记这里。',
        },
    ]));

    const perfLensRows = computed(() => ([
        {
            name: '整户总账',
            where: '本页顶部「累计总收益」',
            meaning: '当前总资产 − 累计净投入',
            goodFor: '回答：整锅钱相对额外投入，到底赚了多少',
            notFor: '不对应华泰某只票的累计盈亏',
        },
        {
            name: '当前仓贡献',
            where: '本页「浮盈+分红」与贡献表',
            meaning: '(现价 − 普通成本)×数量 + 分红',
            goodFor: '回答：现在还拿着的仓，谁在帮你赚钱',
            notFor: '不含历史卖出已实现；通常小于券商累计盈亏',
        },
        {
            name: '接近券商累计',
            where: '首页卡片 / 持仓明细 / 本页贡献表「全周期」',
            meaning: '(现价 − 摊薄成本)×数量',
            goodFor: '和券商 App 累计盈亏对账',
            notFor: '不要和「当前仓贡献」混加',
        },
    ]));

    const perfReadTips = computed(() => {
        const s = perfSummary.value || {};
        const tips = [];
        if (!hasPerfFlows.value) {
            tips.push({
                type: 'warning',
                title: '外部资金流水尚未录入',
                text: '净投入、累计总收益、XIRR 都依赖底部「组合资金流水」。没录之前，请把它们当参考，优先看贡献表相对排序。',
            });
        } else {
            tips.push({
                type: 'success',
                title: '外部流水已启用',
                text: `已记录 ${s.flow_count || 0} 笔组合外部资金进出。净投入与 XIRR 才有完整意义。`,
            });
        }
        tips.push({
            type: 'info',
            title: '三套盈亏本来就不会相等',
            text: '整户总账 ≠ 当前仓浮盈+分红 ≠ 持仓页全周期盈亏。对不上是口径不同，不是算错。',
        });
        tips.push({
            type: 'info',
            title: '日常怎么选页',
            text: '看单票涨跌/是否减仓 → 持仓明细；看配置比例 → 资产配置；看整户赚亏与年化 → 本页。',
        });
        return tips;
    });

    const perfCards = computed(() => {
        const s = perfSummary.value;
        if (!s) return [];
        const flowReady = Number(s.flow_count || 0) > 0;
        const gainColor = s.total_gain >= 0 ? '#F56C6C' : '#67C23A';
        const floatSum = Number(s.current_unrealized_profit || 0) + Number(s.total_dividend_income || 0);
        return [
            {
                label: '当前总资产',
                plain: '你现在一共有多少钱',
                value: formatMoney(s.total_assets),
                sub: '市值 + 证券现金 + 存款 + 申购在途',
                color: '#303133',
            },
            {
                label: '累计净投入',
                plain: '你还净投了多少',
                value: flowReady ? formatMoney(s.net_contribution) : '待录入',
                sub: flowReady
                    ? `投入 ${formatMoney(s.total_in)} − 取出 ${formatMoney(s.total_out)}`
                    : '请在下方录「投入/取出」，不是买卖流水',
                color: flowReady ? '#303133' : '#E6A23C',
            },
            {
                label: '累计总收益',
                plain: '整户一共赚了多少',
                value: flowReady ? formatMoney(s.total_gain) : '待录入',
                sub: flowReady
                    ? `相对净投入 ${Number(s.total_gain_pct || 0).toFixed(2)}% · 总资产−净投入`
                    : '公式：总资产 − 净投入（需先有外部流水）',
                color: flowReady ? gainColor : '#E6A23C',
            },
            {
                label: 'XIRR 年化',
                plain: '考虑进出时间后的年化',
                value: s.xirr != null ? `${Number(s.xirr).toFixed(2)}%` : (flowReady ? '--' : '待录入'),
                sub: s.xirr_status === 'ok'
                    ? '资金加权年化，适合长期跟踪'
                    : (s.xirr_message || '至少需要有效的投入/取出与当前资产'),
                color: s.xirr != null ? ((s.xirr || 0) >= 0 ? '#F56C6C' : '#67C23A') : '#909399',
            },
            {
                label: '当前仓浮盈+分红',
                plain: '现在还拿着的仓赚多少',
                value: formatMoney(floatSum),
                sub: `浮盈 ${formatMoney(s.current_unrealized_profit)} / 分红 ${formatMoney(s.total_dividend_income)} · 不含已卖出`,
                color: floatSum >= 0 ? '#F56C6C' : '#67C23A',
            },
            {
                label: '全周期盈亏合计',
                plain: '接近券商累计盈亏',
                value: formatMoney(s.lifetime_profit),
                sub: 'Σ(现价 − 摊薄成本)×数量 · 分红已在摊薄中',
                color: Number(s.lifetime_profit || 0) >= 0 ? '#F56C6C' : '#67C23A',
            },
            {
                label: 'YTD 收益',
                plain: '今年初至今赚了多少',
                value: formatMoney(s.ytd_gain),
                sub: `相对年初快照 ${Number(s.ytd_gain_pct || 0).toFixed(2)}% · 已扣今年净投入变化`,
                color: s.ytd_gain >= 0 ? '#F56C6C' : '#67C23A',
            },
        ];
    });

    const displayedPerfContribution = computed(() => {
        const totalGain = Number(perfSummary.value?.total_gain || 0);
        let rows = [...(perfContribution.value || [])];
        if (perfContributionFilter.value === 'positive') rows = rows.filter(item => Number(item.total_contribution || 0) >= 0);
        if (perfContributionFilter.value === 'negative') rows = rows.filter(item => Number(item.total_contribution || 0) < 0);
        if (perfContributionSort.value === 'market_value') {
            rows.sort((a, b) => Number(b.market_value || 0) - Number(a.market_value || 0));
        } else if (perfContributionSort.value === 'lifetime') {
            rows.sort((a, b) => Number(b.lifetime_profit || 0) - Number(a.lifetime_profit || 0));
        } else if (perfContributionSort.value === 'share') {
            rows.sort((a, b) => {
                const shareB = totalGain ? Number(b.total_contribution || 0) / totalGain : 0;
                const shareA = totalGain ? Number(a.total_contribution || 0) / totalGain : 0;
                return shareB - shareA;
            });
        } else {
            rows.sort((a, b) => Number(b.total_contribution || 0) - Number(a.total_contribution || 0));
        }
        return rows;
    });

    const perfContributionHeadline = computed(() => {
        const rows = [...(perfContribution.value || [])].sort((a, b) => Number(b.total_contribution || 0) - Number(a.total_contribution || 0));
        return { best: rows[0] || null, worst: rows.length ? rows[rows.length - 1] : null };
    });

    const perfContributionMix = computed(() => {
        const rows = perfContribution.value || [];
        const sorted = [...rows].sort((a, b) => Number(b.total_contribution || 0) - Number(a.total_contribution || 0));
        return {
            positiveCount: rows.filter(item => Number(item.total_contribution || 0) >= 0).length,
            negativeCount: rows.filter(item => Number(item.total_contribution || 0) < 0).length,
            top3Contribution: sorted.slice(0, 3).reduce((sum, item) => sum + Number(item.total_contribution || 0), 0),
        };
    });

    const contributionBarStyle = (value) => {
        const maxAbs = Math.max(...(perfContribution.value || []).map(item => Math.abs(Number(item.total_contribution || 0))), 0);
        const ratio = maxAbs > 0 ? Math.max(Math.abs(Number(value || 0)) / maxAbs, 0.04) : 0;
        return {
            width: `${Math.min(ratio * 100, 100)}%`,
            background: Number(value || 0) >= 0 ? 'linear-gradient(90deg, #f89898 0%, #F56C6C 100%)' : 'linear-gradient(90deg, #95d475 0%, #67C23A 100%)',
        };
    };

    const renderPerfChart = async () => {
        const { renderPerfTimelineChartView, waitForChartDom } = await import('../charts/index.js');
        if (!perfTimeline.value?.length) return;
        const ready = await waitForChartDom(['perfTimelineChart']);
        if (!ready) return;
        await new Promise((r) => requestAnimationFrame(() => r()));
        renderPerfTimelineChartView(perfTimeline.value);
    };

    async function fetchPerformance() {
        perfLoading.value = true;
        try {
            const [sumR, tlR, ctR, flR] = await Promise.all([
                api.performanceSummary(),
                api.performanceTimeline(),
                api.performanceContribution(),
                api.listPortfolioCashFlows(),
            ]);
            perfSummary.value = sumR.data;
            perfTimeline.value = tlR.data;
            perfContribution.value = ctR.data;
            perfFlows.value = flR.data;
            nextTick(renderPerfChart);
        } catch (e) {
            console.error('fetchPerformance', e);
            showSyncNotice('获取收益分析失败：' + (e?.response?.data?.detail || e?.message || '未知错误'), 'error');
        } finally {
            perfLoading.value = false;
        }
    }

    async function addPerfFlow() {
        try {
            await api.addPortfolioCashFlow(perfFlowForm.value);
            showSyncNotice('新增成功');
            fetchPerformance();
        } catch (e) { showSyncNotice('新增失败: ' + (e.response?.data?.detail || e.message), 'error'); }
    }

    async function deletePerfFlow(id) {
        try {
            await api.deletePortfolioCashFlow(id);
            showSyncNotice('已删除');
            fetchPerformance();
        } catch (e) { showSyncNotice('删除失败', 'error'); }
    }

    return {
        hasPerfFlows,
        perfGuideSteps,
        perfLensRows,
        perfReadTips,
        perfCards,
        displayedPerfContribution,
        perfContributionHeadline,
        perfContributionMix,
        contributionBarStyle,
        renderPerfChart,
        fetchPerformance,
        addPerfFlow,
        deletePerfFlow,
    };
};

export { createPerformanceModule };
export default createPerformanceModule;
