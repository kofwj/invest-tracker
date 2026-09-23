/**
 * 交易时段相关的纯函数。
 *
 * 这些判断被组件用到，但要单独可测（且不受测试运行时钟影响），所以只做成
 * `(now = new Date()) => boolean` 的纯函数，**不在组件里直接读全局时间**。
 */

/** 收盘线：15:30（含）之后视为"早已收盘"，当天该有快照了 */
const MARKET_CLOSE_MINUTES = 15 * 60 + 30;

/** 一天中的第几分钟（0-1439） */
const minutesOfDay = (now = new Date()) => {
  const d = now instanceof Date ? now : new Date(now);
  return d.getHours() * 60 + d.getMinutes();
};

/**
 * 本地时间是否已过收盘线（≥ 15:30）。
 * 边界：15:30 返回 true，15:29 返回 false。
 */
const isAfterMarketClose = (now = new Date()) => minutesOfDay(now) >= MARKET_CLOSE_MINUTES;

export { MARKET_CLOSE_MINUTES, minutesOfDay, isAfterMarketClose };
