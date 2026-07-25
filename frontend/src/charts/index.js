import * as echarts from 'echarts/core';
import { LineChart, PieChart } from 'echarts/charts';
import {
    TitleComponent,
    TooltipComponent,
    LegendComponent,
    GridComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { formatMoney } from '../utils/index.js';

echarts.use([
    LineChart,
    PieChart,
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
    ].forEach((c) => {
        try {
            if (c && typeof c.resize === 'function') c.resize();
        } catch (_) { /* ignore */ }
    });
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
    waitForChartDom,
    resizeAllCharts,
    readTheme,
};

export default {
    renderSnapshotChartsView,
    renderAllocationChartsView,
    renderPerfTimelineChartView,
    waitForChartDom,
    resizeAllCharts,
};
