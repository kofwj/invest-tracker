import api from '../api/index.js';
import { buildDailyPnlRows, formatMoney, summarizeDailyPnl } from '../utils/index.js';
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

function monthStartIso() {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`;
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
    perfWindows,
    perfFlowForm,
    showSyncNotice,
    nextTick,
}) => {
    let perfFlowSubmitting = false;
    const hasPerfFlows = computed(() => Number(perfSummary.value?.flow_count || 0) > 0);

    const perfStoryToneType = computed(() => {
        const t = perfStory.value?.tone;
        if (t === 'positive') return 'success';
        if (t === 'negative') return 'error';
        return 'info';
    });

    /** 普通人核心 3 张卡 + 辅助 */
    const perfPrimaryCards = computed(() => {
        const s = perfSummary.value;
        if (!s) return [];
        const flowReady = Number(s.flow_count || 0) > 0;

        // 优先用“本期”数据（时间范围改变时）。
        // 后端在无起点快照且本期之前已有资金时返回 null（期间收益不可知），
        // 此时必须整组回退到全周期口径，否则会出现「本期」标签配全周期数字。
        const isPeriod = !!s.period_start_date && s.period_gain != null;
        const mainGain = isPeriod ? (s.period_gain ?? s.total_gain) : s.total_gain;
        const mainGainPct = isPeriod ? (s.period_gain_pct ?? s.total_gain_pct) : s.total_gain_pct;
        const mainNet = isPeriod ? (s.period_net_contribution ?? s.net_contribution) : s.net_contribution;

        const gainColor = (mainGain || 0) >= 0 ? 'var(--app-up)' : 'var(--app-down)';

        const cards = [
            {
                label: '现在总资产',
                value: formatMoney(s.total_assets),
                color: 'var(--app-text)',
                main: true,
            },
            {
                label: isPeriod ? '本期净投入' : '累计净投入',
                value: flowReady ? formatMoney(mainNet) : '待录入',
                color: flowReady ? 'var(--app-text)' : 'var(--app-warn)',
            },
            {
                label: isPeriod ? '这段时间赚/亏' : '累计总收益',
                value: flowReady ? formatMoney(mainGain) : '待录入',
                color: flowReady ? gainColor : 'var(--app-warn)',
                main: true,
            },
        ];
        return cards;
    });

    /** 辅助信息（次要） */
    const perfSecondaryCards = computed(() => {
        const s = perfSummary.value;
        if (!s) return [];
        const flowReady = Number(s.flow_count || 0) > 0;
        const floatSum = Number(s.current_unrealized_profit || 0) + Number(s.total_dividend_income || 0);
        const cards = [
            {
                label: '当前仓浮盈+分红',
                value: formatMoney(floatSum),
                color: floatSum >= 0 ? 'var(--app-up)' : 'var(--app-down)',
            },
            {
                label: '今年以来',
                value: formatMoney(s.ytd_gain),
                color: s.ytd_gain >= 0 ? 'var(--app-up)' : 'var(--app-down)',
            },
        ];

        // 距目标收益缺口（约 4% 净投入年化）
        if (flowReady && s.target_gap != null) {
            cards.push({
                label: '距目标收益缺口',
                value: formatMoney(s.target_gap, 2, true),
                color: s.target_gap <= 0 ? 'var(--app-up)' : 'var(--app-down)',
            });
        }
        return cards;
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

    // === 时间轴收益尺卡片（今天/本月/今年/近一年/开仓至今）===
    const perfWindowCards = computed(() => {
        const wins = perfWindows.value || [];
        const active = perfTimelineRange?.value || 'all';
        return wins.map((w) => {
            const gain = Number(w.gain);
            const pct = w.gain_pct != null ? Number(w.gain_pct) : null;
            let tone = 'neutral';
            if (pct != null) tone = pct > 0 ? 'up' : (pct < 0 ? 'down' : 'neutral');
            else if (gain > 0) tone = 'up';
            else if (gain < 0) tone = 'down';
            // staleDays：起点快照距今几天。"今天"这张卡的基准可能已经是几周前
            // （快照没在跑），那时它衡量的根本不是"今天"，必须让前端能标出来。
            const staleDays = w.stale_days == null ? null : Number(w.stale_days);
            return {
                key: w.key,
                label: w.label,
                gain: Number.isFinite(gain) ? gain : null,
                gainPct: pct,
                active: w.key === active,
                tone,
                disabled: gain == null,
                staleDays,
                stale: staleDays != null && staleDays > 1,
                baseDate: w.start_date || null,
            };
        });
    });

    const selectPerfWindow = (key) => setPerfTimelineRange(key);

    // === 每日收益（逐日盈亏）===
    /** 新的在前：[{date, prevDate, change, pct, assets, daysGap, isGap}] */
    const perfDailyRows = computed(() => buildDailyPnlRows(perfTimeline.value));

    /** 最新一条快照日期；没快照时为 null */
    const perfLatestSnapshotDate = computed(() => {
        const rows = perfTimeline.value || [];
        return rows.length ? String(rows[rows.length - 1].date || '') : null;
    });


    const perfDailyStats = computed(() => summarizeDailyPnl(perfDailyRows.value, 30));

    // === 专业组合级指标（portfolio level，非个股）===
    // 从 timeline 计算最大回撤（peak to trough）
    const perfRiskMetrics = computed(() => {
        const rows = perfTimeline.value || [];
        if (!rows || rows.length < 2) return null;
        let peak = -Infinity;
        let maxDD = 0;
        let peakDate = null;
        let troughDate = null;
        let peakVal = 0;
        for (const r of rows) {
            const v = Number(r.total_assets || 0);
            if (v > peak) {
                peak = v;
                peakDate = r.date;
                peakVal = v;
            }
            const dd = peak > 0 ? (peak - v) / peak : 0;
            if (dd > maxDD) {
                maxDD = dd;
                troughDate = r.date;
            }
        }
        // 简单年化波动率近似（日回报标准差 * sqrt(252)），点数少时为 null
        let approxVol = null;
        if (rows.length >= 6) {
            const rets = [];
            for (let i = 1; i < rows.length; i++) {
                const p = Number(rows[i - 1].total_assets || 0);
                const c = Number(rows[i].total_assets || 0);
                if (p > 0) rets.push((c - p) / p);
            }
            if (rets.length >= 3) {
                const mean = rets.reduce((a, b) => a + b, 0) / rets.length;
                const variance = rets.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / rets.length;
                const dailyStd = Math.sqrt(variance);
                approxVol = Number((dailyStd * Math.sqrt(252) * 100).toFixed(1));
            }
        }
        return {
            maxDrawdown: maxDD,
            maxDrawdownPct: Number((maxDD * 100).toFixed(1)),
            peak: roundOrNull(peakVal),
            peakDate,
            troughDate,
            approxVol,
            hasEnoughData: rows.length >= 6,
        };
    });

    function roundOrNull(v) {
        return v == null ? null : Number(Number(v).toFixed(2));
    }

    // 轻量贡献摘要（组合视角，代替详细个股表）
    const perfContributionSummary = computed(() => {
        const rows = perfContribution.value || [];
        if (!rows.length) return { topWinners: [], topLosers: [], byCategory: [] };
        const sorted = [...rows].sort((a, b) => Number(b.total_contribution || 0) - Number(a.total_contribution || 0));
        const topWinners = sorted.filter(r => Number(r.total_contribution || 0) > 0).slice(0, 3);
        const topLosers = [...sorted].filter(r => Number(r.total_contribution || 0) < 0).slice(-3).reverse();
        // 类别汇总（与大类卡片呼应）
        const cat = { '权益': 0, '债基': 0, 'REITs': 0 };
        for (const r of rows) {
            const c = (r.category || '').toString();
            const amt = Number(r.total_contribution || 0);
            if (c.includes('REIT') || c.toUpperCase().includes('REIT')) cat['REITs'] += amt;
            else if (c.includes('债') || c.includes('固收')) cat['债基'] += amt;
            else cat['权益'] += amt;
        }
        const byCategory = Object.entries(cat).map(([name, amount]) => ({ name, amount: Number(amount.toFixed(2)) }));
        return { topWinners, topLosers, byCategory };
    });

    const timelineQuery = () => {
        const range = perfTimelineRange?.value || 'all';
        if (range === 'today') return { start_date: shiftIsoDays(0) };
        if (range === 'month') return { start_date: monthStartIso() };
        if (range === 'ytd') return { start_date: yearStartIso() };
        if (range === '1y') return { start_date: shiftIsoDays(-365) };
        return {};
    };

    // 同一时间只允许一份"同参数"的收益请求在飞：连点刷新/切页重复触发时复用同一
    // 个 Promise，避免后到的响应覆盖先到的（表现为"刷新了但数字又跳回去"）。
    const perfInFlight = new Map();

    async function fetchPerformance() {
        perfLoading.value = true;
        const q = timelineQuery();
        const key = JSON.stringify(q);
        if (perfInFlight.has(key)) return perfInFlight.get(key);

        const task = (async () => {
            // 用 allSettled：以前是 Promise.all，六个接口里任何一个失败（外网抖动、
            // 504、超时）都会整页不更新，只剩按钮转圈 —— 用户看到的"刷新不出来"。
            const results = await Promise.allSettled([
                api.performanceSummary(q),
                api.performanceTimeline(q),
                api.performanceContribution(),
                api.listPortfolioCashFlows(q),
                api.performanceStory(q),
                api.performanceWindows(),
            ]);
            const [sumR, tlR, ctR, flR, stR, winR] = results;
            if (sumR.status === 'fulfilled') perfSummary.value = sumR.value.data;
            if (tlR.status === 'fulfilled') perfTimeline.value = tlR.value.data;
            if (ctR.status === 'fulfilled') perfContribution.value = ctR.value.data;
            if (flR.status === 'fulfilled') perfFlows.value = flR.value.data;
            if (stR.status === 'fulfilled') perfStory.value = stR.value.data;
            if (winR.status === 'fulfilled') perfWindows.value = winR.value.data || [];

            const labels = ['收益汇总', '收益时间轴', '持仓贡献', '组合流水', '收益故事', '时间轴收益尺'];
            const failed = results
                .map((r, i) => (r.status === 'rejected' ? labels[i] : null))
                .filter(Boolean);
            if (failed.length) {
                const firstErr = results.find((r) => r.status === 'rejected');
                const detail = firstErr?.reason?.response?.data?.detail
                    || firstErr?.reason?.message
                    || '未知错误';
                console.error('fetchPerformance', firstErr?.reason);
                showSyncNotice(`收益分析部分刷新失败（${failed.join('、')}）：${detail}`, 'error');
            } else {
                showSyncNotice('收益分析已刷新', 'success');
            }
            return { failed: failed.length };
        })()
            // allSettled 之后理论上不会 reject；兜底保证调用方永远拿到结果而非异常
            .catch((e) => {
                console.error('fetchPerformance', e);
                showSyncNotice('收益分析刷新失败：' + (e?.message || '未知错误'), 'error');
                return { failed: 1 };
            });

        perfInFlight.set(key, task);
        try {
            return await task;
        } finally {
            perfInFlight.delete(key);
            perfLoading.value = false;
        }
    }

    async function setPerfTimelineRange(range) {
        if (perfTimelineRange) perfTimelineRange.value = range || 'all';
        await fetchPerformance();
    }

    async function addPerfFlow() {
        if (perfFlowSubmitting) return false;
        perfFlowSubmitting = true;
        try {
            await api.addPortfolioCashFlow(perfFlowForm.value);
            showSyncNotice('新增成功');
            await fetchPerformance();
            return true;
        } catch (e) {
            showSyncNotice('新增失败: ' + (e.response?.data?.detail || e.message), 'error');
            return false;
        } finally {
            perfFlowSubmitting = false;
        }
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
        if (perfFlowSubmitting) return;
        perfFlowSubmitting = true;
        try {
            await api.addPortfolioCashFlow({
                date: row.date,
                flow_type: row.flow_type,
                amount: row.amount,
                source: row.source || '',
                remark: row.remark || '',
            });
            showSyncNotice('已记入组合流水');
            await fetchPerformance();
        } catch (e) {
            showSyncNotice('写入失败: ' + (e?.response?.data?.detail || e.message), 'error');
        } finally {
            perfFlowSubmitting = false;
        }
    }

    return {
        hasPerfFlows,
        perfStoryToneType,
        perfPrimaryCards,
        perfSecondaryCards,
        perfCards,
        perfCategoryBars,
        displayedPerfContribution,
        perfContributionHeadline,
        perfContributionMix,
        contributionBarStyle,
        fetchPerformance,
        setPerfTimelineRange,
        addPerfFlow,
        updatePerfFlow,
        deletePerfFlow,
        loadPerfFlowSuggestions,
        applyPerfFlowSuggestion,
        // 新增专业组合级指标
        perfRiskMetrics,
        perfContributionSummary,
        // 时间轴收益尺
        perfWindowCards,
        selectPerfWindow,
        // 每日收益
        perfDailyRows,
        perfDailyStats,
        perfLatestSnapshotDate,
    };
};

export { createPerformanceModule };
export default createPerformanceModule;
