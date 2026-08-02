import * as echarts from 'echarts/core';
import { BarChart, CandlestickChart, LineChart, PieChart } from 'echarts/charts';
import {
    DataZoomComponent,
    TitleComponent,
    TooltipComponent,
    LegendComponent,
    GridComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { formatMoney } from '../utils/index.js';

echarts.use([
    BarChart,
    CandlestickChart,
    LineChart,
    PieChart,
    DataZoomComponent,
    TitleComponent,
    TooltipComponent,
    LegendComponent,
    GridComponent,
    CanvasRenderer,
]);

let allocationChart = null;
let categoryChart = null;
let snapshotTrendChart = null;
let snapshotStructureChart = null;
let perfTimelineChart = null;
let overviewWeekChart = null;

/** 从 CSS token 读色；ECharts 不吃 var()，必须解析成实际色值 */
const cssVar = (name, fallback) => {
    if (typeof window === 'undefined' || !window.getComputedStyle) return fallback;
    try {
        const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
        return v || fallback;
    } catch (_) {
        return fallback;
    }
};

const isDarkTheme = () => {
    if (typeof document === 'undefined') return false;
    const root = document.documentElement;
    if (root.classList.contains('dark')) return true;
    if (root.dataset.theme === 'dark') return true;
    return false;
};

const lightPieColors = ['#2f6f7e', '#3d9a5f', '#c98a2e', '#d64545', '#6b7fd7', '#3b7ea6', '#b08968', '#2a9d8f'];
const darkPieColors = ['#5aa8b8', '#6ecf8e', '#e0b15a', '#f07178', '#9b8afb', '#6ba8c9', '#d4a574', '#7dd3c0'];

/** 账本图表统一调色：标题/图例/轴线跟主题，避免夜间深字看不清 */
const readTheme = () => {
    const dark = isDarkTheme();
    return {
        dark,
        text: cssVar('--app-text', dark ? '#f3f5f7' : '#1c2430'),
        muted: cssVar('--app-muted', dark ? '#8b949e' : '#667085'),
        soft: cssVar('--app-soft', dark ? '#6b7280' : '#98a2b3'),
        border: cssVar('--app-border', dark ? 'rgba(255,255,255,0.12)' : '#e4e9ee'),
        surface: cssVar('--app-surface', dark ? '#14191d' : '#ffffff'),
        primary: cssVar('--app-primary', dark ? '#5aa8b8' : '#2f6f7e'),
        up: cssVar('--app-up', dark ? '#f07178' : '#d64545'),
        down: cssVar('--app-down', dark ? '#6ecf8e' : '#3d9a5f'),
        warn: cssVar('--app-warn', dark ? '#e0b15a' : '#c98a2e'),
        info: cssVar('--app-info', dark ? '#6ba8c9' : '#3b7ea6'),
        pieColors: dark ? darkPieColors : lightPieColors,
        tooltipBg: dark ? 'rgba(20,25,29,0.94)' : 'rgba(255,255,255,0.96)',
        tooltipBorder: dark ? 'rgba(255,255,255,0.12)' : '#e4e9ee',
    };
};

/** 确保 echarts 实例挂在当前 DOM 上（lazy tab / 异步组件会换掉节点） */
const ensureChart = (instance, domId) => {
    const el = document.getElementById(domId);
    if (!el) return null;
    if (instance) {
        const oldEl = typeof instance.getDom === 'function' ? instance.getDom() : null;
        if (oldEl === el && el.isConnected) return instance;
        try { instance.dispose(); } catch (_) { /* ignore */ }
    }
    return echarts.init(el);
};

const baseTooltip = (t, extra = {}) => ({
    backgroundColor: t.tooltipBg,
    borderColor: t.tooltipBorder,
    borderWidth: 1,
    textStyle: { color: t.text, fontSize: 12 },
    ...extra,
});

/**
 * 扇形图：底部图例 + 扇区只标「够大」的百分比，小块不画外侧字 → 防叠。
 * 详情靠 hover tooltip。
 */
const pieSeriesOption = (data, t, { radius = ['40%', '66%'], center = ['50%', '44%'] } = {}) => ({
    type: 'pie',
    radius,
    center,
    data,
    color: t.pieColors,
    minShowLabelAngle: 8,
    avoidLabelOverlap: true,
    itemStyle: {
        borderColor: t.surface,
        borderWidth: 2,
    },
    label: {
        show: true,
        position: 'inside',
        formatter: (p) => (Number(p.percent) >= 8 ? `${Math.round(p.percent)}%` : ''),
        color: '#fff',
        fontSize: 11,
        fontWeight: 700,
        textBorderColor: 'rgba(0,0,0,0.25)',
        textBorderWidth: 1,
    },
    labelLine: { show: false },
    emphasis: {
        scale: true,
        scaleSize: 4,
        label: {
            show: true,
            formatter: '{b}\n{d}%',
            fontSize: 12,
            fontWeight: 700,
            color: '#fff',
        },
    },
});

const pieChartOption = (title, data, t, seriesOpts = {}) => ({
    color: t.pieColors,
    title: {
        text: title,
        left: 'center',
        top: 4,
        textStyle: { color: t.text, fontSize: 13, fontWeight: 650 },
    },
    tooltip: baseTooltip(t, {
        trigger: 'item',
        formatter: (p) => `${p.name}<br/>${formatMoney(p.value)}（${p.percent}%）`,
    }),
    legend: {
        type: data.length > 5 ? 'scroll' : 'plain',
        orient: 'horizontal',
        bottom: 2,
        left: 'center',
        itemWidth: 10,
        itemHeight: 10,
        itemGap: 12,
        textStyle: { color: t.muted, fontSize: 11 },
        pageTextStyle: { color: t.muted },
        pageIconColor: t.primary,
        pageIconInactiveColor: t.soft,
    },
    series: [pieSeriesOption(data, t, seriesOpts)],
});

const renderSnapshotChartsView = (snapshots = []) => {
    const trendDom = document.getElementById('snapshotTrendChart');
    const structDom = document.getElementById('snapshotStructureChart');
    if (!trendDom || !structDom) return false;

    snapshotTrendChart = ensureChart(snapshotTrendChart, 'snapshotTrendChart');
    snapshotStructureChart = ensureChart(snapshotStructureChart, 'snapshotStructureChart');
    if (!snapshotTrendChart || !snapshotStructureChart) return false;

    const t = readTheme();
    const rowsAsc = [...snapshots].sort((a, b) => String(a.date).localeCompare(String(b.date)));
    const dates = rowsAsc.map((r) => r.date);
    snapshotTrendChart.setOption({
        color: [t.primary, t.info, t.down],
        tooltip: baseTooltip(t, { trigger: 'axis', valueFormatter: (v) => formatMoney(v) }),
        legend: {
            top: 0,
            textStyle: { color: t.muted, fontSize: 11 },
        },
        grid: { left: 70, right: 24, top: 48, bottom: 36 },
        xAxis: {
            type: 'category',
            data: dates,
            axisLabel: { color: t.muted },
            axisLine: { lineStyle: { color: t.border } },
        },
        yAxis: {
            type: 'value',
            axisLabel: { color: t.muted, formatter: (v) => `${(v / 10000).toFixed(0)}万` },
            splitLine: { lineStyle: { color: t.border, type: 'dashed' } },
        },
        series: [
            { name: '总资产', type: 'line', smooth: true, data: rowsAsc.map((r) => r.total_assets) },
            { name: '投资账户市值', type: 'line', smooth: true, data: rowsAsc.map((r) => r.total_market_value) },
            {
                name: '现金+存款+在途',
                type: 'line',
                smooth: true,
                data: rowsAsc.map(
                    (r) => Number(r.bank_balance || 0) + Number(r.securities_cash || 0) + Number(r.pending_purchase || 0),
                ),
            },
        ],
    }, true);

    const latest = rowsAsc[rowsAsc.length - 1] || {};
    const structData = [
        { name: '投资账户市值', value: Number(latest.total_market_value || 0) },
        { name: '银行存款', value: Number(latest.bank_balance || 0) },
        { name: '证券现金', value: Number(latest.securities_cash || 0) },
        { name: '申购在途', value: Number(latest.pending_purchase || 0) },
    ].filter((x) => x.value > 0);

    snapshotStructureChart.setOption(
        pieChartOption('资产结构', structData, t, { radius: ['38%', '68%'], center: ['50%', '46%'] }),
        true,
    );
    try {
        snapshotTrendChart.resize();
        snapshotStructureChart.resize();
    } catch (_) { /* ignore */ }
    return true;
};

const renderAllocationChartsView = (macroAllocationAnalysis = [], allocationAnalysis = []) => {
    const chartDom = document.getElementById('allocationChart');
    const catDom = document.getElementById('categoryChart');
    // lazy tab 首次切换时异步组件可能尚未挂载
    if (!chartDom || !catDom) return false;

    allocationChart = ensureChart(allocationChart, 'allocationChart');
    categoryChart = ensureChart(categoryChart, 'categoryChart');
    if (!allocationChart || !categoryChart) return false;

    const t = readTheme();
    const macroData = macroAllocationAnalysis
        .map((x) => ({ name: x.group, value: Number(x.amount || 0) }))
        .filter((x) => x.value > 0);
    const categoryData = allocationAnalysis
        .map((x) => ({ name: x.category, value: Number(x.market_value || 0) }))
        .filter((x) => x.value > 0);

    allocationChart.setOption(
        pieChartOption('权益 / 固收 / 存款', macroData, t, {
            radius: ['40%', '68%'],
            center: ['50%', '44%'],
        }),
        true,
    );
    categoryChart.setOption(
        pieChartOption('细分类别占比', categoryData, t, {
            radius: ['36%', '64%'],
            center: ['50%', '44%'],
        }),
        true,
    );

    // 容器从 display:none 切过来时宽高可能为 0，强制重算
    try {
        allocationChart.resize();
        categoryChart.resize();
    } catch (_) { /* ignore */ }
    return true;
};

const renderPerfTimelineChartView = (perfTimeline = []) => {
    const el = document.getElementById('perfTimelineChart');
    if (!el || !perfTimeline.length) return false;
    if (perfTimelineChart) {
        try { perfTimelineChart.dispose(); } catch (_) { /* ignore */ }
        perfTimelineChart = null;
    }
    perfTimelineChart = echarts.init(el);
    const t = readTheme();
    const data = perfTimeline;
    perfTimelineChart.setOption({
        color: [t.primary, t.muted, t.warn],
        tooltip: baseTooltip(t, { trigger: 'axis' }),
        legend: {
            data: ['总资产', '净投入', '总收益'],
            top: 0,
            textStyle: { color: t.muted, fontSize: 11 },
        },
        grid: { left: 60, right: 30, top: 40, bottom: 30 },
        xAxis: {
            type: 'category',
            data: data.map((d) => d.date),
            axisLabel: { color: t.muted },
            axisLine: { lineStyle: { color: t.border } },
        },
        yAxis: {
            type: 'value',
            axisLabel: { color: t.muted, formatter: (v) => `${(v / 10000).toFixed(0)}万` },
            splitLine: { lineStyle: { color: t.border, type: 'dashed' } },
        },
        series: [
            {
                name: '总资产',
                type: 'line',
                data: data.map((d) => d.total_assets),
                smooth: true,
                lineStyle: { width: 2 },
                itemStyle: { color: t.primary },
            },
            {
                name: '净投入',
                type: 'line',
                data: data.map((d) => d.net_contribution),
                smooth: true,
                lineStyle: { width: 2, type: 'dashed' },
                itemStyle: { color: t.muted },
            },
            {
                name: '总收益',
                type: 'line',
                data: data.map((d) => d.total_gain),
                smooth: true,
                lineStyle: { width: 1.5 },
                itemStyle: { color: t.warn },
            },
        ],
    }, true);
    try { perfTimelineChart.resize(); } catch (_) { /* ignore */ }
    return true;
};

/** 总览右上：近半月总资产曲线（单线 + 面积，Y 轴贴合波动） */
const renderOverviewWeekChartView = (rows = []) => {
    const el = document.getElementById('overviewWeekChart');
    if (!el) return false;
    overviewWeekChart = ensureChart(overviewWeekChart, 'overviewWeekChart');
    if (!overviewWeekChart) return false;

    const t = readTheme();
    const seriesRows = [...(rows || [])]
        .filter((r) => r && r.date != null)
        .sort((a, b) => String(a.date).localeCompare(String(b.date)));

    if (!seriesRows.length) {
        overviewWeekChart.clear();
        overviewWeekChart.setOption({
            title: {
                text: '暂无近半月快照',
                left: 'center',
                top: 'middle',
                textStyle: { color: t.muted, fontSize: 12, fontWeight: 500 },
            },
        }, true);
        try { overviewWeekChart.resize(); } catch (_) { /* ignore */ }
        return true;
    }

    const values = seriesRows.map((r) => Number(r.total_assets || 0));
    const first = values[0] || 0;
    const last = values[values.length - 1] || 0;
    const lineColor = last >= first ? t.up : t.down;
    const minV = Math.min(...values);
    const maxV = Math.max(...values);
    const span = Math.max(maxV - minV, Math.abs(maxV) * 0.002, 1);
    const pad = span * 0.18;

    const shortDate = (d) => {
        const s = String(d || '');
        return s.length >= 10 ? s.slice(5) : s;
    };

    overviewWeekChart.setOption({
        color: [lineColor],
        animationDuration: 280,
        grid: { left: 8, right: 8, top: 18, bottom: 22, containLabel: true },
        tooltip: baseTooltip(t, {
            trigger: 'axis',
            formatter: (params) => {
                const p = Array.isArray(params) ? params[0] : params;
                if (!p) return '';
                const idx = p.dataIndex;
                const row = seriesRows[idx] || {};
                const cur = Number(row.total_assets || p.value || 0);
                const base = first;
                const delta = cur - base;
                const pct = base ? (delta / base) * 100 : null;
                const pctText = pct === null ? '' : `（${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%）`;
                const liveTag = row.live ? ' · 实时' : '';
                return `${row.date || p.name}${liveTag}<br/>总资产 ${formatMoney(cur)}<br/>较期初 ${formatMoney(delta, 2, true)}${pctText}`;
            },
        }),
        xAxis: {
            type: 'category',
            boundaryGap: false,
            data: seriesRows.map((r) => r.date),
            axisLabel: {
                color: t.muted,
                fontSize: 10,
                formatter: shortDate,
                hideOverlap: true,
            },
            axisTick: { show: false },
            axisLine: { lineStyle: { color: t.border } },
        },
        yAxis: {
            type: 'value',
            min: minV - pad,
            max: maxV + pad,
            splitNumber: 3,
            axisLabel: {
                color: t.muted,
                fontSize: 10,
                formatter: (v) => {
                    const n = Number(v) / 10000;
                    if (Math.abs(n) >= 100) return `${n.toFixed(0)}万`;
                    if (Math.abs(n) >= 10) return `${n.toFixed(1)}万`;
                    return `${n.toFixed(2)}万`;
                },
            },
            splitLine: { lineStyle: { color: t.border, type: 'dashed', opacity: 0.7 } },
            axisLine: { show: false },
            axisTick: { show: false },
        },
        series: [
            {
                name: '总资产',
                type: 'line',
                smooth: 0.35,
                symbol: seriesRows.length <= 8 ? 'circle' : 'none',
                symbolSize: 6,
                showSymbol: seriesRows.length <= 8,
                data: values,
                lineStyle: { width: 2.2, color: lineColor },
                itemStyle: { color: lineColor },
                areaStyle: {
                    color: {
                        type: 'linear',
                        x: 0,
                        y: 0,
                        x2: 0,
                        y2: 1,
                        colorStops: [
                            { offset: 0, color: lineColor + '33' },
                            { offset: 1, color: lineColor + '05' },
                        ],
                    },
                },
            },
        ],
    }, true);
    try { overviewWeekChart.resize(); } catch (_) { /* ignore */ }
    return true;
};

/**
 * 等待图表容器出现（应对 el-tab-pane lazy + defineAsyncComponent 的挂载延迟）
 * @returns {Promise<boolean>} 是否在超时前找到节点
 */
const waitForChartDom = (ids, { timeoutMs = 2500, intervalMs = 50 } = {}) => {
    const list = Array.isArray(ids) ? ids : [ids];
    const start = Date.now();
    return new Promise((resolve) => {
        const tick = () => {
            if (list.every((id) => document.getElementById(id))) {
                resolve(true);
                return;
            }
            if (Date.now() - start >= timeoutMs) {
                resolve(false);
                return;
            }
            setTimeout(tick, intervalMs);
        };
        tick();
    });
};

/** 窗口缩放时重算所有已挂载图表尺寸 */
const resizeAllCharts = () => {
    [
        allocationChart,
        categoryChart,
        snapshotTrendChart,
        snapshotStructureChart,
        perfTimelineChart,
        overviewWeekChart,
    ].forEach((c) => {
        try {
            if (c && typeof c.resize === 'function') c.resize();
        } catch (_) { /* ignore */ }
    });
};

let klineChart = null;

/**
 * 渲染 K线图（日K + 成交量）。
 * @param {HTMLElement} el
 * @param {Array<{date,open,high,low,close,volume}>} rows 升序
 */
const renderKlineChartView = (el, rows) => {
    if (!el) return null;
    if (klineChart) {
        try { klineChart.dispose(); } catch (_) {}
        klineChart = null;
    }
    if (!rows || !rows.length) {
        klineChart = echarts.init(el);
        klineChart.setOption({
            title: { text: '暂无日K数据，点"刷新K线"重试', left: 'center', top: 'middle', textStyle: { color: '#999', fontSize: 14 } },
        });
        return klineChart;
    }
    const theme = readTheme();
    const dates = rows.map(r => r.date);
    const ohlc = rows.map(r => [Number(r.open), Number(r.close), Number(r.low), Number(r.high)]);
    const volumes = rows.map(r => Number(r.volume || 0));

    klineChart = echarts.init(el);
    klineChart.setOption({
        backgroundColor: theme.surface,
        animation: false,
        tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'cross' },
            backgroundColor: theme.surface,
            borderColor: theme.border,
            textStyle: { color: theme.text },
            valueFormatter: (val, series) => series === 0 ? Array.isArray(val) ? `开 ${val[0]} / 高 ${val[3]} / 低 ${val[2]} / 收 ${val[1]}` : val : val,
        },
        axisPointer: { link: [{ xAxisIndex: 'all' }] },
        grid: [
            { left: 60, right: 20, top: 30, height: '62%' },
            { left: 60, right: 20, top: '76%', height: '16%' },
        ],
        xAxis: [
            { type: 'category', data: dates, scale: true, boundaryGap: false, splitLine: { show: false }, axisLabel: { color: theme.muted, fontSize: 10 } },
            { type: 'category', gridIndex: 1, data: dates, scale: true, boundaryGap: false, splitLine: { show: false }, axisLabel: { show: false } },
        ],
        yAxis: [
            { scale: true, splitLine: { lineStyle: { color: theme.border } }, axisLabel: { color: theme.muted, fontSize: 10 } },
            { gridIndex: 1, splitNumber: 2, axisLabel: { show: false }, splitLine: { show: false } },
        ],
        dataZoom: [
            { type: 'inside', xAxisIndex: [0, 1], start: 60, end: 100 },
            { show: true, type: 'slider', xAxisIndex: [0, 1], bottom: 8, height: 16, start: 60, end: 100, textStyle: { color: theme.muted } },
        ],
        series: [
            {
                name: '日K',
                type: 'candlestick',
                data: ohlc,
                itemStyle: {
                    color: theme.up,
                    color0: theme.down,
                    borderColor: theme.up,
                    borderColor0: theme.down,
                },
            },
            {
                name: '成交量',
                type: 'bar',
                xAxisIndex: 1,
                yAxisIndex: 1,
                data: volumes,
                itemStyle: { color: theme.muted, opacity: 0.35 },
            },
        ],
    });
    return klineChart;
};

let chartResizeBound = false;
const ensureChartResizeListener = () => {
    if (chartResizeBound || typeof window === 'undefined') return;
    chartResizeBound = true;
    window.addEventListener('resize', () => {
        resizeAllCharts();
    });
};
ensureChartResizeListener();

export {
    renderSnapshotChartsView,
    renderAllocationChartsView,
    renderPerfTimelineChartView,
    renderOverviewWeekChartView,
    renderKlineChartView,
    waitForChartDom,
    resizeAllCharts,
    readTheme,
};

export default {
    renderSnapshotChartsView,
    renderAllocationChartsView,
    renderPerfTimelineChartView,
    renderOverviewWeekChartView,
    renderKlineChartView,
    waitForChartDom,
    resizeAllCharts,
    readTheme,
};