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

const renderSnapshotChartsView = (snapshots = []) => {
    const trendDom = document.getElementById('snapshotTrendChart');
    const structDom = document.getElementById('snapshotStructureChart');
    if (!trendDom || !structDom) return false;

    snapshotTrendChart = ensureChart(snapshotTrendChart, 'snapshotTrendChart');
    snapshotStructureChart = ensureChart(snapshotStructureChart, 'snapshotStructureChart');
    if (!snapshotTrendChart || !snapshotStructureChart) return false;

    const rowsAsc = [...snapshots].sort((a, b) => String(a.date).localeCompare(String(b.date)));
    const dates = rowsAsc.map(r => r.date);
    snapshotTrendChart.setOption({
        tooltip: { trigger: 'axis', valueFormatter: v => formatMoney(v) },
        legend: { top: 0 },
        grid: { left: 70, right: 24, top: 48, bottom: 36 },
        xAxis: { type: 'category', data: dates },
        yAxis: { type: 'value', axisLabel: { formatter: v => (v / 10000).toFixed(0) + '万' } },
        series: [
            { name: '总资产', type: 'line', smooth: true, data: rowsAsc.map(r => r.total_assets) },
            { name: '投资账户市值', type: 'line', smooth: true, data: rowsAsc.map(r => r.total_market_value) },
            { name: '现金+存款+在途', type: 'line', smooth: true, data: rowsAsc.map(r => Number(r.bank_balance || 0) + Number(r.securities_cash || 0) + Number(r.pending_purchase || 0)) },
        ],
    });
    const latest = rowsAsc[rowsAsc.length - 1] || {};
    snapshotStructureChart.setOption({
        tooltip: { trigger: 'item', formatter: p => `${p.name}: ${formatMoney(p.value)} (${p.percent}%)` },
        series: [{
            type: 'pie',
            radius: ['38%', '68%'],
            data: [
                { name: '投资账户市值', value: Number(latest.total_market_value || 0) },
                { name: '银行存款', value: Number(latest.bank_balance || 0) },
                { name: '证券现金', value: Number(latest.securities_cash || 0) },
                { name: '申购在途', value: Number(latest.pending_purchase || 0) },
            ],
        }],
    });
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

    const macroData = macroAllocationAnalysis.map(x => ({ name: x.group, value: Number(x.amount || 0) })).filter(x => x.value > 0);
    const categoryData = allocationAnalysis.map(x => ({ name: x.category, value: Number(x.market_value || 0) })).filter(x => x.value > 0);

    allocationChart.setOption({
        title: { text: '权益 / 固收 / 存款', left: 'center' },
        tooltip: { trigger: 'item', formatter: params => `${params.name}: ${formatMoney(params.value)} (${params.percent}%)` },
        legend: { bottom: 0 },
        series: [{ type: 'pie', radius: ['38%', '66%'], center: ['50%', '46%'], data: macroData }],
    }, true);
    categoryChart.setOption({
        title: { text: '细分类别占比', left: 'center' },
        tooltip: { trigger: 'item', formatter: params => `${params.name}: ${formatMoney(params.value)} (${params.percent}%)` },
        legend: { bottom: 0 },
        series: [{ type: 'pie', radius: ['34%', '64%'], center: ['50%', '46%'], data: categoryData }],
    }, true);

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
    const data = perfTimeline;
    perfTimelineChart.setOption({
        tooltip: { trigger: 'axis' },
        legend: { data: ['总资产', '净投入', '总收益'], top: 0 },
        grid: { left: 60, right: 30, top: 40, bottom: 30 },
        xAxis: { type: 'category', data: data.map(d => d.date) },
        yAxis: { type: 'value', axisLabel: { formatter: v => (v / 10000).toFixed(0) + '万' } },
        series: [
            { name: '总资产', type: 'line', data: data.map(d => d.total_assets), smooth: true, lineStyle: { width: 2 }, itemStyle: { color: '#409EFF' } },
            { name: '净投入', type: 'line', data: data.map(d => d.net_contribution), smooth: true, lineStyle: { width: 2, type: 'dashed' }, itemStyle: { color: '#909399' } },
            { name: '总收益', type: 'line', data: data.map(d => d.total_gain), smooth: true, lineStyle: { width: 1.5 }, itemStyle: { color: '#E6A23C' } },
        ],
    });
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
};

export default {
    renderSnapshotChartsView,
    renderAllocationChartsView,
    renderPerfTimelineChartView,
    waitForChartDom,
    resizeAllCharts,
};
