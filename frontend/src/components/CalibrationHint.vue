<template>
  <!--
    「现在总资产」底下那行小字：距上次校准 N 天 · 上次差额 Y 元。
    会计口径的差额本来就该是可见的一项，所以这里不藏：点开就能填实测值、把差额吃成平差。
  -->
  <div v-if="calibration" class="ov-cal-hint" :data-level="level">
    <button type="button" class="ov-cal-link" :title="linkTitle" @click="openDialog">
      {{ calibration.hint }}
    </button>
    <span v-if="adjustmentText" class="ov-cal-adj" :title="`看板总资产里含一笔记账平差 ${adjustmentText}（不摊回持仓/流水）`">
      · 平差 {{ adjustmentText }}
    </span>
  </div>

  <el-dialog v-model="dialogVisible" title="总资产校准" width="440px" append-to-body>
    <p class="ov-cal-tip">
      把券商 App + 银行里看到的实际总额填进来。差额会记成一条独立可见的「记账平差」，
      不改动任何持仓、现金或流水；下次再校准一次就会自动收敛。
    </p>
    <el-form label-width="92px" @submit.prevent>
      <el-form-item label="实测总资产">
        <el-input
          v-model="manualInput"
          inputmode="decimal"
          placeholder="例如 1021800"
          @keyup.enter="submit"
        />
      </el-form-item>
      <el-form-item label="备注">
        <el-input v-model="noteInput" placeholder="可留空，例如「券商 + 招行 11 月底」" />
      </el-form-item>
    </el-form>
    <p class="ov-cal-current">
      当前看板 {{ money(displayedTotal) }}
      <template v-if="pendingGap !== null">，差额 <span class="num" :class="gapTone">{{ money(pendingGap, 2, true) }}</span> 记入平差</template>
    </p>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="submit">确认校准</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
/**
 * 总资产校准入口。
 *
 * 个人账本真正的失效方式不是算错，而是「看板 1,024,500 / 券商 App 1,021,800」这种偏差
 * 一天天攒着，攒到懒得找那 2,700 块为止。所以这条通道只做一件事：让用户把实测总额填进来，
 * 差额落成一笔可见的平差（后端 settings.total_assets_adjustment），看板立刻对齐实盘。
 *
 * 数据来源是 dashboard.calibration（/dashboard 已经带了，不再单独请求）；
 * 校准动作走 POST /snapshots/reconcile/apply，成功后 refresh 一次 dashboard。
 * 拿不到 ctx 的字段时整块不渲染 —— 首页不能因为一条提示而白屏。
 */
import { computed, ref, unref } from 'vue';
import { ElMessage } from 'element-plus';
import api from '../api/index.js';
import { useAppCtx } from '../composables/useAppCtx.js';

const ctx = useAppCtx();
const dashboard = ctx.dashboard;

/** ctx.formatMoney 在单测里可能没给，兜底成同签名的朴素实现 */
const money = (value, digits = 2, signed = false) => {
    if (typeof ctx.formatMoney === 'function') return ctx.formatMoney(value, digits, signed);
    if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
    const num = Number(value);
    return `${signed && num >= 0 ? '+' : ''}${num.toFixed(digits)}`;
};

const calibration = computed(() => unref(dashboard)?.calibration || null);
const level = computed(() => calibration.value?.level || 'never');
const adjustment = computed(() => Number(calibration.value?.adjustment || 0));
const adjustmentText = computed(() => (
    Math.abs(adjustment.value) >= 0.005 ? money(adjustment.value, 2, true) : ''
));

const displayedTotal = computed(() => Number(unref(dashboard)?.total_assets || 0));

const linkTitle = computed(() => {
    const parts = ['填一次券商 + 银行的实际总额，差额会记成可见的记账平差'];
    const last = calibration.value?.last_manual_total_assets;
    if (last !== null && last !== undefined) parts.push(`上次填的是 ${money(last)}`);
    if (last !== undefined && calibration.value?.last_calibration_date) {
        parts.push(`日期 ${calibration.value.last_calibration_date}`);
    }
    return parts.join(' · ');
});

const dialogVisible = ref(false);
const saving = ref(false);
const manualInput = ref('');
const noteInput = ref('');

/** 「1,021,800」这种手抄格式也要能认 */
const parseAmount = (raw) => {
    const cleaned = String(raw ?? '').replace(/[,，\s¥￥]/g, '');
    if (!cleaned) return null;
    const value = Number(cleaned);
    if (!Number.isFinite(value) || value < 0) return null;
    return value;
};

const pendingGap = computed(() => {
    const value = parseAmount(manualInput.value);
    if (value === null) return null;
    return Math.round((value - displayedTotal.value) * 100) / 100;
});

const gapTone = computed(() => {
    if (pendingGap.value === null || Math.abs(pendingGap.value) < 0.005) return '';
    return pendingGap.value > 0 ? 'is-up' : 'is-down';
});

function openDialog() {
    // 预填当前看板值：用户只需要把对不上的部分改掉，比从空框开始填轻松
    const base = Math.round(displayedTotal.value * 100) / 100;
    manualInput.value = String(base);
    noteInput.value = '';
    dialogVisible.value = true;
}

async function submit() {
    if (saving.value) return;
    const value = parseAmount(manualInput.value);
    if (value === null) {
        ElMessage.warning('请填一个有效的金额（不小于 0）');
        return;
    }
    saving.value = true;
    try {
        const { data } = await api.applyTotalAssetCalibration({
            manual_total_assets: value,
            note: noteInput.value.trim(),
        });
        ElMessage.success(`已校准：本次差额 ${money(data?.gap, 2, true)}`);
        dialogVisible.value = false;
        if (typeof ctx.fetchData === 'function') await ctx.fetchData();
    } catch (e) {
        const detail = e?.response?.data?.detail || '校准失败，稍后再试';
        ElMessage.error(detail);
    } finally {
        saving.value = false;
    }
}
</script>

<style scoped>
.ov-cal-hint {
    margin-top: 5px;
    display: flex;
    align-items: baseline;
    gap: 4px;
    flex-wrap: wrap;
    font-size: 12px;
    color: var(--app-muted, #6b7280);
}
.ov-cal-link {
    padding: 0;
    border: 0;
    background: none;
    font: inherit;
    color: inherit;
    text-align: left;
    cursor: pointer;
    text-decoration: underline dotted;
    text-underline-offset: 2px;
}
.ov-cal-link:hover { color: var(--app-text, #111); }
/* 该对账了：只把这一行染成警示色，不动总资产本身 */
.ov-cal-hint[data-level='due'] .ov-cal-link { color: var(--app-warn, #c98a2e); }
.ov-cal-hint[data-level='overdue'] .ov-cal-link { color: var(--app-danger, #c0392b); font-weight: 600; }
.ov-cal-adj { color: var(--app-soft, #9ca3af); }
.ov-cal-tip {
    margin: 0 0 12px;
    font-size: 13px;
    line-height: 1.6;
    color: var(--app-muted, #6b7280);
}
.ov-cal-current {
    margin: 4px 0 0;
    font-size: 12px;
    color: var(--app-muted, #6b7280);
}
.ov-cal-current .num.is-up { color: var(--app-up, #c0392b); }
.ov-cal-current .num.is-down { color: var(--app-down, #1f8a4c); }
</style>
