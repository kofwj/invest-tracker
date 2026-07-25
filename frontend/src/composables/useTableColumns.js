import { computed, ref, watch } from 'vue';

/**
 * 表格列显隐 + localStorage 记忆。
 * @param {string} storageKey
 * @param {{ key: string, label: string, defaultVisible?: boolean }[]} columnDefs
 */
export function useTableColumns(storageKey, columnDefs) {
  const defaults = {};
  for (const col of columnDefs) {
    defaults[col.key] = col.defaultVisible !== false;
  }

  const load = () => {
    try {
      const raw = localStorage.getItem(storageKey);
      if (!raw) return { ...defaults };
      const parsed = JSON.parse(raw);
      if (!parsed || typeof parsed !== 'object') return { ...defaults };
      return { ...defaults, ...parsed };
    } catch {
      return { ...defaults };
    }
  };

  const visibility = ref(load());

  watch(
    visibility,
    (val) => {
      try {
        localStorage.setItem(storageKey, JSON.stringify(val));
      } catch {
        /* ignore quota */
      }
    },
    { deep: true },
  );

  const isVisible = (key) => visibility.value[key] !== false;

  const toggle = (key, on) => {
    visibility.value = {
      ...visibility.value,
      [key]: typeof on === 'boolean' ? on : !isVisible(key),
    };
  };

  const reset = () => {
    visibility.value = { ...defaults };
  };

  const optionalColumns = computed(() =>
    columnDefs.filter((c) => c.defaultVisible === false || c.optional),
  );

  const allToggleColumns = computed(() =>
    columnDefs.filter((c) => c.toggleable !== false),
  );

  return {
    visibility,
    isVisible,
    toggle,
    reset,
    optionalColumns,
    allToggleColumns,
    columnDefs,
  };
}

/** 分类标签颜色（中文分类名） */
export function categoryTagType(cat) {
  const c = String(cat || '');
  if (/权益|股票|ETF|指数|港股|A股/.test(c)) return 'danger';
  if (/固收|债券|债基|货币/.test(c)) return 'success';
  if (/存款|现金|货币基金/.test(c)) return 'info';
  if (/REIT|地产|黄金|商品/.test(c)) return 'warning';
  return '';
}

/** 盈亏色：A股习惯 红涨绿跌 */
export function pnlColor(n) {
  const v = Number(n);
  if (!Number.isFinite(v) || v === 0) return '#606266';
  return v > 0 ? '#F56C6C' : '#67C23A';
}
