// Vitest mock for ECharts — tests only exercise pure helpers (analyzeKlineTrend),
// so we stub the chart init/use modules to keep import side-effects out of node env.
const noop = () => {};
const fakeChart = { setOption: noop, dispose: noop, resize: noop };

export const init = noop;
export const use = noop;
export const BarChart = {};
export const CandlestickChart = {};
export const LineChart = {};
export const PieChart = {};
export const DataZoomComponent = {};
export const TitleComponent = {};
export const TooltipComponent = {};
export const LegendComponent = {};
export const GridComponent = {};
export const CanvasRenderer = {};
export default { init: () => fakeChart, use: noop };