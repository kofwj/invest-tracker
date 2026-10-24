/**
 * DataTable 的窄屏卡片参数。
 *
 * 断点写在 JS 而不是 CSS 里，是因为卡片分支换的是 DOM 而不是样式：窄屏必须真的
 * 卸载 el-table，否则屏幕阅读器会把同一份数据读两遍，DOM 体积也翻倍。
 * 640 沿用 styles.css 里已有的移动端断点，不新增第四档。
 */
export const CARD_QUERY = '(max-width: 640px)';

/**
 * 卡片列表的 key，与 el-table 的 `row-key` 同一语义：
 * 字符串 → 取该字段；函数 → 直接调用；没给 → 退回索引。
 */
export function cardKeyOf(row, index, rowKey) {
  if (typeof rowKey === 'function') return rowKey(row);
  if (rowKey) return row?.[rowKey] ?? index;
  return index;
}
