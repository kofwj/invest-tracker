<template>
  <div class="data-table" v-loading="loading">
    <div
      v-if="useCards"
      class="data-table-cards"
      role="list"
      :aria-label="label || undefined"
    >
      <div
        v-for="(row, index) in list"
        :key="cardKeyOf(row, index, rowKey)"
        class="data-card"
        role="listitem"
      >
        <slot name="card" :row="row" :index="index" />
      </div>
      <el-empty v-if="!list.length" :description="emptyText" :image-size="70" />
    </div>
    <slot v-else />
  </div>
</template>

<script setup>
/**
 * 表格的响应式外壳：宽屏原样透传，窄屏换成卡片列表。
 *
 * 透传是有意为之——全仓两百多列里有一半是 `#default` 插槽，把列抽象成配置对象等于
 * 重写所有表格模板。这里只负责「换布局」，桌面端的 DOM 一个节点都不多。
 *
 * 没给 `#card` 时窄屏也保持表格（横向滚动），等于改造前的样子：迁移可以停在任意
 * 一步，没覆盖的表不会变差。
 */
import { computed, useSlots } from 'vue';
import { useMediaQuery } from '../composables/useMediaQuery.js';
import { CARD_QUERY, cardKeyOf } from '../modules/dataTable.js';

const props = defineProps({
  /** 窄屏卡片的数据源；宽屏由默认插槽里的 el-table 自己拿 data */
  rows: { type: Array, default: () => [] },
  /** 加载态挂在外壳上：窄屏 el-table 被卸载后，卡片列表否则会完全没有加载态 */
  loading: { type: Boolean, default: false },
  /** 窄屏卡列表为空时的文案；宽屏沿用 el-table 自己的 empty-text */
  emptyText: { type: String, default: '暂无数据' },
  /** 与 el-table 的 row-key 同语义（字段名或函数），用来给卡片做 key */
  rowKey: { type: [String, Function], default: '' },
  /** 卡片列表的可访问名称，例如「持仓明细」 */
  label: { type: String, default: '' },
});

const slots = useSlots();
const isNarrow = useMediaQuery(CARD_QUERY);

const useCards = computed(() => isNarrow.value && !!slots.card);
const list = computed(() => (Array.isArray(props.rows) ? props.rows : []));
</script>

<style scoped>
/* 不给宽屏分支加任何盒模型规则：外层这层 div 必须对原表格隐形，
   只留 min-width 防止它在 flex 容器里被内容撑破。 */
.data-table {
  min-width: 0;
}

.data-table-cards {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.data-card {
  padding: 10px 12px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
}
</style>
