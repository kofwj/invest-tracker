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
    const perfCards = computed(() => {
        const s = perfSummary.value;
        if (!s) return [];
        return [
            { label: '当前总资产', value: formatMoney(s.total_assets), sub: '市值+现金+存款+在途', color: '#303133' },
            { label: '累计净投入', value: formatMoney(s.net_contribution), sub: `投入${formatMoney(s.total_in)} / 取出${formatMoney(s.total_out)}` },
            { label: '累计总收益', value: formatMoney(s.total_gain), sub: `${s.total_gain_pct?.toFixed(2)}%`, color: s.total_gain >= 0 ? '#F56C6C' : '#67C23A' },
            { label: 'XIRR 年化', value: s.xirr != null ? s.xirr.toFixed(2) + '%' : '--', sub: s.xirr_status === 'ok' ? '资金加权' : s.xirr_message || '暂无', color: (s.xirr || 0) >= 0 ? '#F56C6C' : '#67C23A' },
            { label: '浮盈 + 分红', value: formatMoney(s.current_unrealized_profit + s.total_dividend_income), sub: `浮盈${formatMoney(s.current_unrealized_profit)} / 分红${formatMoney(s.total_dividend_income)}`, color: (s.current_unrealized_profit + s.total_dividend_income) >= 0 ? '#F56C6C' : '#67C23A' },
            { label: 'YTD 收益', value: formatMoney(s.ytd_gain), sub: `${s.ytd_gain_pct?.toFixed(2)}%`, color: s.ytd_gain >= 0 ? '#F56C6C' : '#67C23A' },
        ];
    });

    const displayedPerfContribution = computed(() => {
        const totalGain = Number(perfSummary.value?.total_gain || 0);
        let rows = [...(perfContribution.value || [])];
        if (perfContributionFilter.value === 'positive') rows = rows.filter(item => Number(item.total_contribution || 0) >= 0);
        if (perfContributionFilter.value === 'negative') rows = rows.filter(item => Number(item.total_contribution || 0) < 0);
        if (perfContributionSort.value === 'market_value') {
            rows.sort((a, b) => Number(b.market_value || 0) - Number(a.market_value || 0));
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

    const renderPerfChart = () => renderPerfTimelineChartView(perfTimeline.value);

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

window.createPerformanceModule = createPerformanceModule;
