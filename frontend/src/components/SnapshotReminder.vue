<template>
  <div v-if="visible" class="snapshot-reminder" role="status">
    <div class="snapshot-reminder-main">
      <span class="snapshot-reminder-title">今天还没记快照</span>
      <span class="snapshot-reminder-sep">·</span>
      <span class="snapshot-reminder-sub">每日收益会少一天</span>
    </div>
    <el-button
      size="small"
      type="warning"
      plain
      :loading="saving"
      @click="onRetryTodaySnapshot"
    >补记今日快照</el-button>
  </div>
</template>

<script setup>
/**
 * 收盘后的「今天还没记快照」提示。
 *
 * 每日收益依赖服务器 16:40 的定时快照；cron 停了、或当天价格源挂了被后端闸门
 * 拦下，序列就断一天，但界面上看不出来。所以收盘后还没快照就出一条提示，
 * 并给一个手动补记的入口（走和「记录今日快照」一样的 409 → 确认 → force 流程）。
 *
 * 时间判断全部交给 utils/marketTime.js 里的纯函数，方便单测；组件内不写
 * `new Date().getHours() >= 15.5` 这种表达式。
 */
import { computed, onMounted, onUnmounted, ref, unref } from 'vue';
import { ElMessageBox } from 'element-plus';
import { useAppCtx } from '../composables/useAppCtx.js';
import { isAfterMarketClose } from '../utils/marketTime.js';

const props = defineProps({
  /** 测试用：传入固定时间；不传则用本地当前时间（每分钟刷新一次） */
  now: { type: Date, default: null },
});

const { todaySnapshotDone, createSnapshot } = useAppCtx();

const ticking = ref(new Date());
let timer = null;
onMounted(() => {
  if (props.now) return;
  timer = setInterval(() => { ticking.value = new Date(); }, 60000);
});
onUnmounted(() => {
  if (timer) clearInterval(timer);
  timer = null;
});

const visible = computed(
  () => isAfterMarketClose(props.now || ticking.value) && !unref(todaySnapshotDone),
);

const saving = ref(false);

/**
 * 记录今日快照，和 PerformanceTab 里的 postTodaySnapshot 同一套流程：
 * 后端闸门（最新价不是今天的）返回 409，detail 里带基准日期；用户确认后带
 * force 重记一次，取消就什么都不做。非 409 的错误模块层已经提示过，这里只记日志。
 */
async function postTodaySnapshot(force) {
  try {
    return await createSnapshot(force);
  } catch (e) {
    if (e?.response?.status !== 409) throw e;
    const detail = e?.response?.data?.detail || '最新价不是今天的价格，确认后仍要记录今天的快照吗？';
    try {
      await ElMessageBox.confirm(detail, '价格未更新', {
        type: 'warning',
        confirmButtonText: '仍要记录',
        cancelButtonText: '取消',
      });
    } catch (confirmErr) {
      if (confirmErr === 'cancel' || confirmErr === 'close') return undefined;
      throw confirmErr;
    }
    try {
      // 还没支持 force 的实现会再抛一次 409：不再弹第二次确认
      return await createSnapshot(true);
    } catch (retryErr) {
      console.error('createSnapshot(force)', retryErr);
      return undefined;
    }
  }
}

async function onRetryTodaySnapshot() {
  if (saving.value) return;
  saving.value = true;
  try {
    await postTodaySnapshot(false);
  } catch (e) {
    console.error('补记今日快照失败', e);
  } finally {
    saving.value = false;
  }
}
</script>

<style scoped>
.snapshot-reminder {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 14px;
  padding: 8px 14px;
  border-radius: 10px;
  border: 1px solid color-mix(in srgb, var(--app-warn, #c98a2e) 45%, var(--app-border, #e5e7eb));
  background: color-mix(in srgb, var(--app-warn, #c98a2e) 10%, var(--app-surface, #fff));
}
.snapshot-reminder-main {
  display: flex;
  align-items: baseline;
  gap: 6px;
  flex-wrap: wrap;
  font-size: 13px;
}
.snapshot-reminder-title { font-weight: 650; color: var(--app-text, #111); }
.snapshot-reminder-sep { color: var(--app-warn, #c98a2e); }
.snapshot-reminder-sub { color: var(--app-muted, #6b7280); }
</style>
