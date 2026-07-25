import api from '../api/index.js';
import { formatMoney } from '../utils/index.js';
import { computed } from 'vue';

function shiftIsoDays(days) {
    const d = new Date();
    d.setHours(12, 0, 0, 0);
    d.setDate(d.getDate() + days);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
}

function yearStartIso() {
    return `${new Date().getFullYear()}-01-01`;
}

const createPerformanceModule = ({
    perfSummary,
    perfTimeline,
    perfContribution,
    perfFlows,
    perfStory,
    perfLoading,
    perfContributionFilter,
    perfContributionSort,
    perfTimelineRange,
    perfFlowForm,
    showSyncNotice,
    nextTick,
}) => {
    const hasPerfFlows = computed(() => Number(perfSummary.value?.flow_count || 0) > 0);

    const perfStoryToneType = computed(() => {
        const t = perfStory.value?.tone;
        if (t === 'positive') return 'success';
        if (t === 'negative') return 'error';
        return 'info';
    });

    const perfGuideSteps = computed(() => ([
        {
            step: '1',
            title: '先看整户赚没赚',
            text: '重点看「净投入」和「整户总收益」。这是全组合账，不是单只股票。',
        },
        {
            step: '2',
            title: '再看谁在贡献收益',
            text: '贡献表默认按「当前仓浮盈 + 分红」；「全周期」接近券商累计，可切换排序。',
        },
        {
            step: '3',
            title: '需要年化时再录流水',
            text: 'XIRR / 准确净投入，依赖「组合资金流水」（外部投入/取出）。买卖、银证转账不要记这里。',
        },
    ]));

    const perfLensRows = computed(() => ([
        {
            name: '整户总账',
            where: '本页主卡「累计总收益」',
            meaning: '当前总资产 − 累计净投入',
            goodFor: '回答：整锅钱相对额外投入，到底赚了多少',
            notFor: '不对应华泰某只票的累计盈亏',
        },
        {
            name: '当前仓贡献',
            where: '本页贡献表',
            meaning: '(现价 − 普通成本)×数量 + 分红',
            goodFor: '回答：现在还拿着的仓，谁在帮你赚钱',
            notFor: '不含历史卖出已实现；通常小于券商累计盈亏',
        },
        {
            name: '接近券商累计',
            where: '持仓明细 / 本页「全周期」',
            meaning: '(现价 − 摊薄成本)×数量',
            goodFor: '和券商 App 累计盈亏对账',
            notFor: '不要和「当前仓贡献」混加',
        },
    ]));

    /** 主卡 4 张：结论优先 */
    const perfPrimaryCards = computed(() => {
        const s = perfSummary.value;
        if (!s) return [];
        const flowReady = Number(s.flow_count || 0) > 0;
        const gainColor = s.total_gain >= 0 ? 'var(--app-up)' : 'var(--app-down)';
        return [
            {
                label: '累计净投入',
                plain: '你还净投了多少',
                value: flowReady ? formatMoney(s.net_contribution) : '待录入',
                sub: flowReady
                    ? `投入 ${formatMoney(s.total_in)} − 取出 ${formatMoney(s.total_out)}`
                    : '请在下方录「投入/取出」',
                color: flowReady ? 'var(--app-text)' : 'var(--app-warn)',
            },
            {
                label: '累计总收益',
                plain: '整户一共赚了多少',
                value: flowReady ? formatMoney(s.total_gain) : '待录入',
                sub: flowReady
                    ? `相对净投入 ${Number(s.total_gain_pct || 0).toFixed(2)}%`
                    : '公式：总资产 − 净投入',
                color: flowReady ? gainColor : 'var(--app-warn)',
                main: true,
            },
            {
                label: 'XIRR 年化',
                plain: '考虑进出时间后的年化',
                value: s.xirr != null ? `${Number(s.xirr).toFixed(2)}%` : (flowReady ? '—' : '待录入'),
                sub: s.xirr_status === 'ok'
                    ? '资金加权年化'
                    : (s.xirr_message || '需有效投入/取出与当前资产'),
                color: s.xirr != null ? ((s.xirr || 0) >= 0 ? 'var(--app-up)' : 'var(--app-down)') : 'var(--app-muted)',
                main: true,
            },
            {
                label: '全周期盈亏',
                plain: '接近券商累计盈亏',
                value: formatMoney(s.lifetime_profit),
                sub: 'Σ(现价 − 摊薄成本)×数量',
                color: Number(s.lifetime_profit || 0) >= 0 ? 'var(--app-up)' : 'var(--app-down)',
            },
        ];
    });

    /** 次卡：浮盈+分红 / YTD / 总资产 */
    const perfSecondaryCards = computed(() => {
        const s = perfSummary.value;
        if (!s) return [];
        const floatSum = Number(s.current_unrealized_profit || 0) + Number(s.total_dividend_income || 0);
        return [
            {
                label: '当前总资产',
                plain: '你现在一共有多少钱',
                value: formatMoney(s.total_assets),
                sub: '市值 + 现金 + 存款 + 在途',
                color: 'var(--app-text)',
            },
            {
                label: '当前仓浮盈+分红',
                plain: '现在还拿着的仓赚多少',
                value: formatMoney(floatSum),
                sub: `浮盈 ${formatMoney(s.current_unrealized_profit)} / 分红 ${formatMoney(s.total_dividend_income)}`,
                color: floatSum >= 0 ? 'var(--app-up)' : 'var(--app-down)',
            },
            {
                label: 'YTD 收益',
                plain: '今年初至今',
                value: formatMoney(s.ytd_gain),
                sub: `相对年初快照 ${Number(s.ytd_gain_pct || 0).toFixed(2)}%`,
                color: s.ytd_gain >= 0 ? 'var(--app-up)' : 'var(--app-down)',
            },
        ];
    });

    // 兼容旧字段
    const perfCards = computed(() => [...perfPrimaryCards.value, ...perfSecondaryCards.value]);

    const perfCategoryBars = computed(() => {
        const rows = perfStory.value?.category_contrib || [];
        const maxAbs = Math.max(...rows.map((r) => Math.abs(Number(r.amount || 0))), 0) || 1;
        return rows.map((r) => {
            const amount = Number(r.amount || 0);
            return {
                name: r.name,
                amount,
                text: r.text || `${r.name} ${formatMoney(amount, 2, true)}`,
                widthPct: Math.min(100, Math.max(6, (Math.abs(amount) / maxAbs) * 100)),
                positive: amount >= 0,
            };
        });
    });

    const displayedPerfContribution = computed(() => {
        const totalGain = Number(perfSummary.value?.total_gain || 0);
        let rows = [...(perfContribution.value || [])];
        if (perfContributionFilter.value === 'positive') rows = rows.filter((item) => Number(item.total_contribution || 0) >= 0);
        if (perfContributionFilter.value === 'negative') rows = rows.filter((item) => Number(item.total_contribution || 0) < 0);
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
        const rows = [...(perfContribution.value || [])].sort(
            (a, b) => Number(b.total_contribution || 0) - Number(a.total_contribution || 0),
        );
        return { best: rows[0] || null, worst: rows.length ? rows[rows.length - 1] : null };
    });

    const perfContributionMix = computed(() => {
        const rows = perfContribution.value || [];
        const sorted = [...rows].sort((a, b) => Number(b.total_contribution || 0) - Number(a.total_contribution || 0));
        return {
            positiveCount: rows.filter((item) => Number(item.total_contribution || 0) >= 0).length,
            negativeCount: rows.filter((item) => Number(item.total_contribution || 0) < 0).length,
            top3Contribution: sorted.slice(0, 3).reduce((sum, item) => sum + Number(item.total_contribution || 0), 0),
        };
    });

    const contributionBarStyle = (value) => {
        const maxAbs = Math.max(...(perfContribution.value || []).map((item) => Math.abs(Number(item.total_contribution || 0))), 0);
        const ratio = maxAbs > 0 ? Math.max(Math.abs(Number(value || 0)) / maxAbs, 0.04) : 0;
        return {
            width: `${Math.min(ratio * 100, 100)}%`,
            background: Number(value || 0) >= 0
                ? 'linear-gradient(90deg, color-mix(in srgb, var(--app-up) 55%, #fff) 0%, var(--app-up) 100%)'
                : 'linear-gradient(90deg, color-mix(in srgb, var(--app-down) 55%, #fff) 0%, var(--app-down) 100%)',
        };
    };

    const timelineQuery = () => {
        const range = perfTimelineRange?.value || 'all';
        if (range === 'ytd') return { start_date: yearStartIso() };
        if (range === '1y') return { start_date: shiftIsoDays(-365) };
        return {};
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
            const q = timelineQuery();
            const [sumR, tlR, ctR, flR, stR] = await Promise.all([
                api.performanceSummary(),
                api.performanceTimeline(q),
                api.performanceContribution(),
                api.listPortfolioCashFlows(),
                api.performanceStory(),
            ]);
            perfSummary.value = sumR.data;
            perfTimeline.value = tlR.data;
            perfContribution.value = ctR.data;
            perfFlows.value = flR.data;
            perfStory.value = stR.data;
            nextTick(renderPerfChart);
        } catch (e) {
            console.error('fetchPerformance', e);
            showSyncNotice('获取收益分析失败：' + (e?.response?.data?.detail || e?.message || '未知错误'), 'error');
        } finally {
            perfLoading.value = false;
        }
    }

    async function setPerfTimelineRange(range) {
        if (perfTimelineRange) perfTimelineRange.value = range || 'all';
        await fetchPerformance();
    }

    async function addPerfFlow() {
        try {
            await api.addPortfolioCashFlow(perfFlowForm.value);
            showSyncNotice('新增成功');
            fetchPerformance();
        } catch (e) { showSyncNotice('新增失败: ' + (e.response?.data?.detail || e.message), 'error'); }
    }

    async function updatePerfFlow(id, payload) {
        try {
            await api.updatePortfolioCashFlow(id, payload || {});
            showSyncNotice('已更新');
            fetchPerformance();
        } catch (e) { showSyncNotice('更新失败: ' + (e?.response?.data?.detail || e.message), 'error'); }
    }

    async function deletePerfFlow(id) {
        try {
            await api.deletePortfolioCashFlow(id);
            showSyncNotice('已删除');
            fetchPerformance();
        } catch (e) { showSyncNotice('删除失败', 'error'); }
    }

    async function loadPerfFlowSuggestions() {
        try {
            const res = await api.portfolioCashFlowSuggest();
            return res.data || { drafts: [], count: 0 };
        } catch (e) {
            showSyncNotice('加载流水建议失败: ' + (e?.response?.data?.detail || e.message), 'error');
            return { drafts: [], count: 0 };
        }
    }

    async function applyPerfFlowSuggestion(row) {
        try {
            await api.addPortfolioCashFlow({
                date: row.date,
                flow_type: row.flow_type,
                amount: row.amount,
                source: row.source || '',
                remark: row.remark || '',
            });
            showSyncNotice('已记入组合流水');
            fetchPerformance();
        } catch (e) {
            showSyncNotice('写入失败: ' + (e?.response?.data?.detail || e.message), 'error');
        }
    }

    return {
        hasPerfFlows,
        perfStoryToneType,
        perfGuideSteps,
        perfLensRows,
        perfPrimaryCards,
        perfSecondaryCards,
        perfCards,
        perfCategoryBars,
        displayedPerfContribution,
        perfContributionHeadline,
        perfContributionMix,
        contributionBarStyle,
        renderPerfChart,
        fetchPerformance,
        setPerfTimelineRange,
        addPerfFlow,
        updatePerfFlow,
        deletePerfFlow,
        loadPerfFlowSuggestions,
        applyPerfFlowSuggestion,
    };
};

export { createPerformanceModule };
export default createPerformanceModule;
