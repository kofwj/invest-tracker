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

const renderSnapshotChartsView = (snapshots = []) => {
    const trendDom = document.getElementById('snapshotTrendChart');
    const structDom = document.getElementById('snapshotStructureChart');
    if (!trendDom || !structDom) return;
    if (!snapshotTrendChart) snapshotTrendChart = echarts.init(trendDom);
    if (!snapshotStructureChart) snapshotStructureChart = echarts.init(structDom);
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
};

const renderAllocationChartsView = (macroAllocationAnalysis = [], allocationAnalysis = []) => {
    if (!allocationChart) {
        const chartDom = document.getElementById('allocationChart');
        if (chartDom) allocationChart = echarts.init(chartDom);
    }
    if (!categoryChart) {
        const catDom = document.getElementById('categoryChart');
        if (catDom) categoryChart = echarts.init(catDom);
    }

    const macroData = macroAllocationAnalysis.map(x => ({ name: x.group, value: Number(x.amount || 0) })).filter(x => x.value > 0);
    const categoryData = allocationAnalysis.map(x => ({ name: x.category, value: Number(x.market_value || 0) })).filter(x => x.value > 0);

    if (allocationChart) {
        allocationChart.setOption({
            title: { text: '权益 / 固收 / 存款', left: 'center' },
            tooltip: { trigger: 'item', formatter: params => `${params.name}: ${formatMoney(params.value)} (${params.percent}%)` },
            legend: { bottom: 0 },
            series: [{ type: 'pie', radius: ['38%', '66%'], center: ['50%', '46%'], data: macroData }],
        });
    }
    if (categoryChart) {
        categoryChart.setOption({
            title: { text: '细分类别占比', left: 'center' },
            tooltip: { trigger: 'item', formatter: params => `${params.name}: ${formatMoney(params.value)} (${params.percent}%)` },
            legend: { bottom: 0 },
            series: [{ type: 'pie', radius: ['34%', '64%'], center: ['50%', '46%'], data: categoryData }],
        });
    }
};

const renderPerfTimelineChartView = (perfTimeline = []) => {
    const el = document.getElementById('perfTimelineChart');
    if (!el || !perfTimeline.length) return;
    if (perfTimelineChart) perfTimelineChart.dispose();
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
};

export {
    renderSnapshotChartsView,
    renderAllocationChartsView,
    renderPerfTimelineChartView,
};

export default {
    renderSnapshotChartsView,
    renderAllocationChartsView,
    renderPerfTimelineChartView,
};
