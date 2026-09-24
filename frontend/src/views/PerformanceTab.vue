<template>
  <PageShell>
    <template #actions>
        <el-tag :type="perfSummary?.xirr_status === 'ok' ? 'success' : (hasPerfFlows ? 'info' : 'warning')" size="small">
          {{ perfSummary?.xirr_status === 'ok' ? '年化已算' : (hasPerfFlows ? (perfSummary?.xirr_message || '年化暂不可用') : '外部流水未录入') }}
        </el-tag>
        <el-button size="small" @click="fetchPerformance" :loading="perfLoading">刷新</el-button>
      
    </template>

    <!-- 收盘后还没记快照：提示 + 补记入口 -->
    <SnapshotReminder />
    <!-- 加载骨架 -->
    <div v-if="perfLoading && !perfSummary" class="sk-metrics" aria-hidden="true">
      <div v-for="i in 4" :key="'sk'+i" class="sk-block sk-metric"></div>
    </div>
    <!-- 未录流水强提示 -->
    <el-alert
      v-if="!hasPerfFlows"
      type="warning"
      show-icon
      :closable="false"
      class="perf-flow-alert"
      title="外部资金流水未录入"
    >
      <template #default>
        <div style="margin-top:6px;">
          <el-button size="small" type="warning" @click="scrollToFlows">去录流水</el-button>
          <el-button size="small" :loading="perfSuggestLoading" @click="onLoadFlowSuggest">从银证生成建议</el-button>
        </div>
      </template>
    </el-alert>

    <!-- 结论：一行数字 + 日期（原「一句话故事」那句长文案不再显示） -->
    <el-card shadow="never" class="perf-lede-card">
      <div class="perf-lede-eyebrow">整户相对净投入</div>
      <div class="perf-lede-line">
        <span class="perf-lede-num" :class="ledeToneText ? 'perf-' + ledeToneText : ''">
          {{ formatMoney(perfSummary?.total_gain, 2, true) }} 元
        </span>
        <span class="perf-lede-pct" :class="ledeToneText ? 'perf-' + ledeToneText : ''">
          （{{ formatPercent(perfSummary?.total_gain_pct, 2) }}）
        </span>
        <span class="perf-lede-date">{{ perfSummary?.as_of_date || '今日' }}</span>
      </div>
    </el-card>

    <!-- 核心两数：发丝线分格，不是两张独立卡片 -->
    <div class="perf-num-row">
      <div v-for="m in perfPrimaryCards" :key="m.label" class="perf-num-cell">
        <div class="k">{{ m.label }}</div>
        <div class="v" :class="{ 'is-warn': String(m.color || '').includes('warn') }" :title="String(m.value)">{{ m.value }}</div>
      </div>
    </div>
    <!-- 收益尺：分段控件 + 当前窗口的大数字 -->
    <div class="perf-window-strip" :class="{ 'is-loading': perfLoading && !perfSummary }">
      <div class="perf-seg" role="tablist" aria-label="收益尺时间范围">
        <button
          v-for="w in perfWindowCards"
          :key="w.key"
          type="button"
          role="tab"
          class="perf-seg-btn"
          :class="{ 'is-active': w.active }"
          :aria-selected="!!w.active"
          :disabled="w.disabled"
          @click="selectPerfWindow(w.key)"
        >{{ w.label }}</button>
      </div>
      <div class="perf-seg-out">
        <span class="perf-seg-big" :class="windowTone ? 'perf-' + windowTone : ''">{{ windowGainText }}</span>
        <span class="perf-seg-sub">{{ windowSubText }}</span>
      </div>
    </div>


    <!-- 走势 + 两行简报：红涨绿跌，已剔除转入转出 -->
    <el-card shadow="never" class="perf-daily-card">
      <div class="perf-daily-head">
        <div>
          <div class="perf-section-title">最近 30 个交易日</div>
          <div class="perf-contrib-sub">
            红涨绿跌 · 已剔除转入/转出；<span v-if="perfLatestSnapshotDate">最近一次快照 {{ perfLatestSnapshotDate }}</span><span v-else>还没有任何快照</span>
          </div>
        </div>
        <div class="perf-daily-actions">
          <el-radio-group v-model="dailyRange" size="small">
            <el-radio-button :value="30">近30天</el-radio-button>
            <el-radio-button :value="90">近90天</el-radio-button>
            <el-radio-button :value="0">全部</el-radio-button>
          </el-radio-group>
          <el-button v-if="!todaySnapshotDone" size="small" :loading="dailySnapshotSaving" @click="onCreateTodaySnapshot">记录今日快照</el-button>
        </div>
      </div>

      <el-alert
        v-if="!perfDailyRows.length"
        type="info"
        show-icon
        :closable="false"
        title="还没有可比较的两天快照"
        description="每日收益要连续两天的快照才算得出来。点上面的「记录今日快照」，或让服务器每天定时跑一次快照任务。"
      />

      <template v-else>
        <div id="dailyPnlChart" class="perf-daily-chart"></div>

        <div class="perf-brief">
          <div class="perf-brief-cell">
            <div class="k">近 7 个交易日累计</div>
            <div class="v" :class="monthlyCard.recent7Tone ? 'perf-' + monthlyCard.recent7Tone : ''" :title="monthlyCard.recent7Title">{{ monthlyCard.recent7Text }}</div>
          </div>
          <div class="perf-brief-cell">
            <div class="k">涨 / 跌 天数</div>
            <div class="v">{{ monthlyCard.upDownText }}</div>
          </div>
          <div class="perf-brief-cell">
            <div class="k">最好一天</div>
            <div class="v" :class="monthlyCard.bestTone ? 'perf-' + monthlyCard.bestTone : ''" :title="monthlyCard.bestWorstTitle">{{ monthlyCard.bestText }}</div>
          </div>
          <div class="perf-brief-cell">
            <div class="k">最差一天</div>
            <div class="v" :class="monthlyCard.worstTone ? 'perf-' + monthlyCard.worstTone : ''" :title="monthlyCard.bestWorstTitle">{{ monthlyCard.worstText }}</div>
          </div>
        </div>

        <div class="perf-hairline"></div>

        <div class="perf-brief">
          <div class="perf-brief-cell">
            <div class="k">近 30 日累计</div>
            <div class="v" :class="perfDailyStats.total >= 0 ? 'perf-up' : 'perf-down'">{{ formatMoney(perfDailyStats.total, 2, true) }}</div>
          </div>
          <div class="perf-brief-cell">
            <div class="k">涨 / 跌 天数</div>
            <div class="v">{{ perfDailyStats.upDays }} / {{ perfDailyStats.downDays }}</div>
          </div>
          <div class="perf-brief-cell">
            <div class="k">最好一天</div>
            <div class="v perf-up">{{ dailyBestText }}</div>
          </div>
          <div class="perf-brief-cell">
            <div class="k">最差一天</div>
            <div class="v perf-down">{{ dailyWorstText }}</div>
          </div>
        </div>

        <el-collapse class="perf-detail-collapse">
          <el-collapse-item name="daily" title="每日明细（逐日盈亏）">

        <el-table :data="dailyTableRows" size="small" stripe max-height="320" style="margin-top:10px;" aria-label="每日收益">
          <el-table-column label="日期" width="140">
            <template #default="s">
              <span>{{ s.row.date }}</span>
              <el-tag v-if="s.row.isToday" size="small" style="margin-left: 6px;">实时</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="当日盈亏" width="140" align="right">
            <template #default="s">
              <span :class="s.row.change >= 0 ? 'perf-up' : 'perf-down'">{{ formatMoney(s.row.change, 2, true) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="当日涨跌" width="110" align="right">
            <template #default="s">
              <span :class="s.row.change >= 0 ? 'perf-up' : 'perf-down'">
                {{ s.row.pct != null ? formatPercent(s.row.pct, 2) : '—' }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="期末总资产" align="right">
            <template #default="s">{{ formatMoney(s.row.assets) }}</template>
          </el-table-column>
          <el-table-column label="间隔" width="100" align="center">
            <template #default="s">
              <el-tooltip
                v-if="s.row.isToday"
                :content="s.row.stale
                  ? `基准快照是 ${s.row.baseDate}，这一行实际跨了 ${s.row.daysGap} 天`
                  : `基准是 ${s.row.baseDate || '上一交易日'} 的收盘快照，收盘后再写成正式快照`"
                placement="top"
              >
                <el-tag size="small" :type="s.row.stale ? 'warning' : 'success'">未收盘</el-tag>
              </el-tooltip>
              <el-tag v-else-if="s.row.isGap" size="small" type="warning">{{ s.row.daysGap }}天</el-tag>
              <span v-else class="perf-contrib-sub">1天</span>
            </template>
          </el-table-column>
          <el-table-column label="价格" width="180" align="center">
            <template #default="s">
              <el-tooltip
                v-if="s.row.priceStale"
                :content="`这天的快照按 ${s.row.priceDate || '早先'} 的价格计算，不是当天价`"
                placement="top"
              >
                <el-tag size="small" type="warning">价格未更新</el-tag>
              </el-tooltip>
              <el-tag v-if="s.row.unpricedCount" size="small" type="info">缺价 {{ s.row.unpricedCount }} 只</el-tag>
              <span v-if="!s.row.priceStale && !s.row.unpricedCount" class="perf-contrib-sub">—</span>
            </template>
          </el-table-column>
        </el-table>
          </el-collapse-item>
        </el-collapse>
      </template>
    </el-card>

    <!-- 风险与归因：不折叠，放在明细之前 -->
    <el-card shadow="never" class="perf-risk-card">
      <div class="perf-daily-head">
        <div>
          <div class="perf-section-title">风险与归因</div>
          <div class="perf-contrib-sub">总收益 = 当前总资产 − 累计净投入；贡献只算现在还持有的</div>
        </div>
      </div>
      <div class="perf-brief perf-brief--flush">
        <div class="perf-brief-cell"><div class="k">最大回撤</div><div class="v">{{ riskItems.maxDrawdown }}</div></div>
        <div class="perf-brief-cell"><div class="k">当前离峰值</div><div class="v perf-down">{{ riskItems.underwater }}</div></div>
        <div class="perf-brief-cell"><div class="k">年化波动</div><div class="v">{{ riskItems.vol }}</div></div>
        <div class="perf-brief-cell"><div class="k">滚动 3M / 6M / 1Y</div><div class="v">{{ riskItems.rolling }}</div></div>
        <div class="perf-brief-cell"><div class="k">贡献最多</div><div class="v perf-up" :title="riskItems.topWin">{{ riskItems.topWin }}</div></div>
        <div class="perf-brief-cell"><div class="k">拖累最多</div><div class="v perf-down" :title="riskItems.topLose">{{ riskItems.topLose }}</div></div>
        <div class="perf-brief-cell"><div class="k">权益贡献</div><div class="v perf-up">{{ riskItems.equity }}</div></div>
        <div class="perf-brief-cell"><div class="k">分红占收益</div><div class="v">{{ riskItems.dividendShare }}</div></div>
        <div class="perf-brief-cell"><div class="k">对国债</div><div class="v perf-up">{{ riskItems.vsBond }}</div></div>
        <div class="perf-brief-cell"><div class="k">对货币 ETF</div><div class="v perf-up">{{ riskItems.vsCash }}</div></div>
        <div class="perf-brief-cell"><div class="k">TWR（时间加权）</div><div class="v">{{ riskItems.twr }}</div></div>
        <div class="perf-brief-cell"><div class="k">年化 vs 4% 目标</div><div class="v perf-up">{{ riskItems.vsTarget }}</div></div>
      </div>
    </el-card>

    <!-- 快照明细：默认收起 -->
    <el-collapse class="perf-detail-collapse">
      <el-collapse-item name="snapshots" title="快照明细">
        <SnapshotPanel />
      </el-collapse-item>
    </el-collapse>

    <!-- 资金流水：默认收起；点「去录流水」会自动展开 -->
    <div id="perf-flow-section">
      <el-collapse v-model="flowOpen" class="perf-detail-collapse">
        <el-collapse-item name="flow" title="组合资金流水（外部投入/取出）">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;gap:12px;flex-wrap:wrap;">
            <div class="perf-contrib-sub">仅记录组合外部投入/取出；买卖、银证互转不在此记录。</div>
            <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
              <el-button size="small" @click="onLoadFlowSuggest" :loading="perfSuggestLoading">从银证生成建议</el-button>
              <el-tag size="small">共 {{ perfFlows.length }} 笔</el-tag>
            </div>
          </div>
      <div v-if="perfFlowSuggestions.length" style="margin-bottom:12px;">
        <div class="perf-contrib-sub" style="margin-bottom:8px;">建议草稿</div>
        <el-table :data="perfFlowSuggestions" size="small" stripe aria-label="资金流水建议草稿">
          <el-table-column prop="date" label="日期" width="110" />
          <el-table-column prop="flow_type" label="类型" width="70" />
          <el-table-column label="金额" width="120" align="right">
            <template #default="s">{{ formatMoney(s.row.amount) }}</template>
          </el-table-column>
          <el-table-column prop="remark" label="说明" min-width="180" show-overflow-tooltip />
          <el-table-column label="操作" width="90">
            <template #default="s">
              <el-button type="primary" link size="small" :loading="perfSuggestionApplying" @click="onApplyPerfFlowSuggestion(s.row)">记入</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <el-form :inline="true" size="small" style="margin-bottom: 12px;">
        <el-form-item label="日期">
          <el-date-picker v-model="perfFlowForm.date" type="date" value-format="YYYY-MM-DD" style="width:140px;" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="perfFlowForm.flow_type" style="width:90px;">
            <el-option label="投入" value="投入" />
            <el-option label="取出" value="取出" />
          </el-select>
        </el-form-item>
        <el-form-item label="金额">
          <el-input-number v-model="perfFlowForm.amount" :min="0" :step="10000" style="width:140px;" />
        </el-form-item>
        <el-form-item label="来源">
          <el-input v-model="perfFlowForm.source" placeholder="银行卡/工资" style="width:100px;" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="perfFlowForm.remark" style="width:120px;" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="perfFlowSaving" @click="onSavePerfFlow">{{ perfFlowEditId ? '保存' : '新增' }}</el-button>
          <el-button v-if="perfFlowEditId" @click="cancelPerfFlowEdit">取消</el-button>
        </el-form-item>
      </el-form>
      <el-table :data="perfFlows" stripe size="small" style="width:100%;" aria-label="组合资金流水">
        <el-table-column prop="date" label="日期" width="110" />
        <el-table-column prop="flow_type" label="类型" width="70">
          <template #default="s">
            <el-tag :type="s.row.flow_type === '投入' ? 'danger' : 'success'" size="small">{{ s.row.flow_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="金额" width="130" align="right">
          <template #default="s">{{ formatMoney(s.row.amount) }}</template>
        </el-table-column>
        <el-table-column prop="source" label="来源" width="100" />
        <el-table-column prop="remark" label="备注" min-width="120" />
        <el-table-column label="操作" width="140" align="center">
          <template #default="s">
            <el-button type="primary" size="small" text @click="startPerfFlowEdit(s.row)">编辑</el-button>
            <el-button type="danger" size="small" text :loading="perfFlowDeleting === s.row.id" :disabled="perfFlowDeleting !== null" @click="onDeletePerfFlow(s.row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
        </el-collapse-item>
      </el-collapse>
    </div>

  </PageShell>
</template>

<script setup>
import PageShell from '../components/PageShell.vue';
import SnapshotReminder from '../components/SnapshotReminder.vue';
import SnapshotPanel from '../components/SnapshotPanel.vue';
import { ref, computed, onMounted, watch } from 'vue';
import { ElMessageBox } from 'element-plus';
import { useAppCtx } from '../composables/useAppCtx.js';
import { formatPercent, summarizeDailyPnl } from '../utils/index.js';

const {
  formatMoney, pct,
  perfSummary, perfTimeline, perfContribution, perfFlows, perfStory, perfLoading, perfFlowForm,
  hasPerfFlows,
  perfPrimaryCards,
  fetchPerformance, addPerfFlow, updatePerfFlow, deletePerfFlow,
  loadPerfFlowSuggestions, applyPerfFlowSuggestion,
  showTransactions, goTab,
  // 新专业指标
  perfRiskMetrics,
  perfContributionSummary,
  // 时间轴收益尺
  perfWindowCards,
  selectPerfWindow,
  // 每日收益
  perfDailyRows,
  perfDailyStats,
  perfLatestSnapshotDate,
  perfTodayRow,
  todaySnapshotDone,
  createSnapshot,
} = useAppCtx();

const perfFlowSuggestions = ref([]);
const perfSuggestLoading = ref(false);
const perfFlowEditId = ref(null);
const perfFlowSaving = ref(false);
const perfFlowDeleting = ref(null);
const perfSuggestionApplying = ref(false);

// === 每日收益 ===
const dailyRange = ref(30);
const dailySnapshotSaving = ref(false);

// === 最近 7 个交易日汇总 ===
/**
 * 取 perfDailyRows 的前 7 行。它只包含有快照的日子，所以文案写「最近 7 个交易日」，
 * 不写「最近 7 天」。「本月 / 今年」只在上方收益尺显示，这张卡不重复。
 */
const recentTradingDays = 7;
const recent7DailyStats = computed(() => summarizeDailyPnl(perfDailyRows.value || [], recentTradingDays));
const monthlyCard = computed(() => {
  const s = recent7DailyStats.value;
  const hasRows = s.count > 0;
  return {
    recent7Text: hasRows ? formatMoney(s.total, 2, true) : '—',
    recent7Tone: hasRows ? (s.total >= 0 ? 'up' : 'down') : '',
    recent7Title: hasRows
      ? `按已有快照的最近 ${s.count} 个交易日累计（已剔除转入/转出）`
      : '还没有可比较的两天快照',
    upDownText: hasRows ? `${s.upDays} / ${s.downDays}` : '—',
    // 最好/最差拆成两张卡：合成一行有 35 个字符，在 3 列栅格里会被 ellipsis 切掉后半句
    bestText: s.best ? `${s.best.date.slice(5)} ${formatMoney(s.best.change, 2, true)}` : '—',
    bestTone: s.best ? (s.best.change >= 0 ? 'up' : 'down') : '',
    worstText: s.worst ? `${s.worst.date.slice(5)} ${formatMoney(s.worst.change, 2, true)}` : '—',
    worstTone: s.worst ? (s.worst.change >= 0 ? 'up' : 'down') : '',
    bestWorstTitle: s.best && s.worst
      ? `最好 ${s.best.date} ${formatMoney(s.best.change, 2, true)} / 最差 ${s.worst.date} ${formatMoney(s.worst.change, 2, true)}`
      : '最近 7 个交易日不足两天',
  };
});

/** 展示用：图表按日期升序，表格按日期降序 */
const dailyRowsForRange = computed(() => {
  const all = perfDailyRows.value || [];
  return dailyRange.value > 0 ? all.slice(0, dailyRange.value) : all;
});
const dailyTodayRow = computed(() => {
  const row = perfTodayRow.value;
  return row ? { ...row, isToday: true } : null;
});
const dailyTableRows = computed(() => {
  const rows = dailyRowsForRange.value.map((row) => ({
    ...row,
    ...(priceFlagsByDate.value[String(row.date)] || {}),
  }));
  // 快照一天才写一条，列表天然只到昨天；把"今日（未收盘）"补在最前面，
  // 否则用户打开收益分析看不到今天赚了多少。
  return dailyTodayRow.value ? [dailyTodayRow.value, ...rows] : rows;
});
const dailyChartRows = computed(() => {
  const asc = [...dailyRowsForRange.value].reverse();
  return dailyTodayRow.value ? [...asc, dailyTodayRow.value] : asc;
});
// timeline 里每行的价格新鲜度（后端新增字段 price_stale / price_date / unpriced_count）。
// buildDailyPnlRows 不搬这几个字段，所以按日期在这里补上。
const priceFlagsByDate = computed(() => {
  const map = {};
  for (const r of perfTimeline.value || []) {
    if (!r) continue;
    map[String(r.date || '')] = {
      priceStale: Number(r.price_stale || 0) === 1 || r.price_stale === true,
      priceDate: r.price_date || null,
      unpricedCount: r.unpriced_count == null ? 0 : Number(r.unpriced_count),
    };
  }
  return map;
});

const dailyBestText = computed(() => {
  const b = perfDailyStats.value.best;
  return b ? `${b.date.slice(5)} ${formatMoney(b.change, 2, true)}` : '—';
});
const dailyWorstText = computed(() => {
  const w = perfDailyStats.value.worst;
  return w ? `${w.date.slice(5)} ${formatMoney(w.change, 2, true)}` : '—';
});

async function renderDailyChart() {
  const { renderDailyPnlChartView, waitForChartDom } = await import('../charts/index.js');
  // 卡片在"无快照"时是 v-else 分支，DOM 还没挂上就渲染会静默失败
  await waitForChartDom(['dailyPnlChart']);
  renderDailyPnlChartView(dailyChartRows.value);
}
/**
 * 记录今日快照。
 * 后端闸门：最新价不是今天的 → 409，detail 里带基准日期；用户确认后带 force 重记一次。
 * createSnapshot(force) 由 appCtx 提供（api 层的签名由他人负责）。
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
      // 还没支持 force 的实现会再抛一次 409：这里不再弹第二次确认，错误提示交给模块
      return await createSnapshot(true);
    } catch (retryErr) {
      console.error('createSnapshot(force)', retryErr);
      return undefined;
    }
  }
}

async function onCreateTodaySnapshot() {
  if (dailySnapshotSaving.value) return;
  dailySnapshotSaving.value = true;
  try {
    await postTodaySnapshot(false);
    await fetchPerformance();
  } catch (e) {
    console.error('记录今日快照失败', e);
  } finally {
    dailySnapshotSaving.value = false;
  }
}

// 直接打开 /performance（书签、F5）时，main.js 里按 tab 触发的加载不会跑，
// 页面会一直是空的 —— 这里补一次首屏加载。
onMounted(async () => {
  if (!perfSummary.value) await fetchPerformance();
  await renderDailyChart();
});

watch(dailyChartRows, () => { renderDailyChart(); });

const latestCategoryAlloc = computed(() => {
  const rows = perfContribution.value || [];
  const buckets = { equity: 0, bond: 0, reit: 0 };
  for (const r of rows) {
    const cat = String(r?.category || "").toUpperCase();
    const mv = Number(r?.market_value || 0);
    if (cat.includes("REIT")) {
      buckets.reit += mv;
    } else if (cat.includes("债") || cat.includes("固收") || cat.includes("货币") || cat.includes("现金")) {
      buckets.bond += mv;
    } else {
      buckets.equity += mv;
    }
  }
  return {
    equity: buckets.equity,
    bond: buckets.bond,
    reit: buckets.reit,
    total: buckets.equity + buckets.bond + buckets.reit,
  };
});

const categorySummary = computed(() => {
  const contribList = perfStory.value?.category_contrib || [];
  const alloc = latestCategoryAlloc.value;
  const tot = alloc.total || 1;

  const cMap = {};
  contribList.forEach((c) => { cMap[c.name] = Number(c.amount || 0); });

  const order = ['权益', '债基', 'REITs'];
  return order.map((name) => {
    let allocAmt = 0;
    if (name === '权益') allocAmt = alloc.equity;
    else if (name === '债基') allocAmt = alloc.bond;
    else allocAmt = alloc.reit;

    const allocPct = tot > 0 ? (allocAmt / tot * 100) : 0;
    const contrib = cMap[name] || 0;
    return { name, allocAmt: Math.round(allocAmt), allocPct: Math.round(allocPct * 10) / 10, contrib };
  }).filter((x) => x.allocAmt > 0 || Math.abs(x.contrib) > 0.01);
});

const scrollToFlows = () => {
  // 流水已收进折叠区：先展开，等 DOM 更新后再滚过去
  flowOpen.value = ['flow'];
  setTimeout(() => {
    const el = document.getElementById('perf-flow-section');
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, 60);
};

const startPerfFlowEdit = (row) => {
  if (!row) return;
  perfFlowEditId.value = row.id;
  perfFlowForm.value = {
    date: row.date,
    flow_type: row.flow_type || '投入',
    amount: Number(row.amount || 0),
    source: row.source || '',
    remark: row.remark || '',
  };
};

const cancelPerfFlowEdit = () => {
  perfFlowEditId.value = null;
};

const savePerfFlow = async () => {
  if (perfFlowEditId.value) {
    await updatePerfFlow(perfFlowEditId.value, { ...perfFlowForm.value });
    perfFlowEditId.value = null;
  } else {
    await addPerfFlow();
  }
};

// 防连点：保存/新增走同一个按钮，模块里只有 addPerfFlow 有内部标志（且不可见），
// updatePerfFlow 没有 —— 这里统一用本页的 ref 挡住。
async function onSavePerfFlow() {
  if (perfFlowSaving.value) return;
  perfFlowSaving.value = true;
  try {
    await savePerfFlow();
  } finally {
    perfFlowSaving.value = false;
  }
}

const onLoadFlowSuggest = async () => {
  if (perfSuggestLoading.value) return;
  perfSuggestLoading.value = true;
  try {
    const data = await loadPerfFlowSuggestions();
    perfFlowSuggestions.value = data?.drafts || [];
    scrollToFlows();
  } finally {
    perfSuggestLoading.value = false;
  }
};

const onContribRowClick = (row) => {
  if (!row?.code) return;
  if (typeof showTransactions === 'function') {
    showTransactions(row);
  } else if (typeof goTab === 'function') {
    goTab('holdings');
  }
};

// 删除流水 / 记入建议：模块里的 perfFlowSubmitting 未导出，in-flight 只能在本页兜住。
async function onDeletePerfFlow(id) {
  if (perfFlowDeleting.value !== null) return;
  perfFlowDeleting.value = id;
  try {
    await deletePerfFlow(id);
  } finally {
    perfFlowDeleting.value = null;
  }
}

async function onApplyPerfFlowSuggestion(row) {
  if (perfSuggestionApplying.value) return;
  perfSuggestionApplying.value = true;
  try {
    await applyPerfFlowSuggestion(row);
  } finally {
    perfSuggestionApplying.value = false;
  }
}

// === 结论带 / 收益尺 / 风险归因（新版排版） ===
const flowOpen = ref([]);

const ledeToneText = computed(() => {
  const g = Number(perfSummary.value?.total_gain ?? 0);
  return g > 0 ? 'up' : g < 0 ? 'down' : '';
});

const currentWindow = computed(() => {
  const list = perfWindowCards.value || [];
  return list.find((w) => w.active) || list[list.length - 1] || null;
});
const windowGainText = computed(() => {
  const w = currentWindow.value;
  return w && w.gain != null ? formatMoney(w.gain, 2, true) : '—';
});
const windowTone = computed(() => {
  const g = currentWindow.value ? currentWindow.value.gain : null;
  if (g == null || Number(g) === 0) return '';
  return Number(g) > 0 ? 'up' : 'down';
});
const windowSubText = computed(() => {
  const w = currentWindow.value;
  if (!w) return '暂无快照';
  // 基准快照不是上一交易日时必须写明，不能默认它等于「今天」
  const staleText = w.stale ? `基准 ${String(w.baseDate || '').slice(5)}（${w.staleDays} 天前）` : '';
  const main = w.key === 'all'
    ? `开仓至今 · 距目标收益缺口 ${perfSummary.value?.target_gap == null ? '—' : formatMoney(perfSummary.value.target_gap, 2, true)}`
    : `${w.label || ''} · ${w.gainPct == null ? '无快照' : formatPercent(w.gainPct, 2)}`;
  return [main, staleText].filter(Boolean).join(' · ');
});

/** 风险与归因的 12 个数：取不到就显示 —，不编数 */
const riskItems = computed(() => {
  const s = perfSummary.value || {};
  const rm = perfRiskMetrics.value || {};
  const story = perfStory.value || {};
  const uw = s.underwater || {};
  const roll = s.rolling_returns || {};
  const bench = s.benchmark_relative || {};
  const win = (story.winners || [])[0];
  const lose = (story.losers || [])[0];
  const equityCat = (story.category_contrib || []).find((c) => c && c.name === '权益');
  const pctText = (v) => (v == null ? '—' : Number(v) >= 0 ? '+' + Number(v).toFixed(2) + '%' : Number(v).toFixed(2) + '%');
  const rollText = (roll['3M'] == null && roll['6M'] == null && roll['1Y'] == null)
    ? '—'
    : `${pctText(roll['3M'])} / ${pctText(roll['6M'])} / ${pctText(roll['1Y'])}`;
  const xirr = s.xirr;
  const target = s.target_return_pct;
  return {
    maxDrawdown: rm.maxDrawdownPct == null ? '—' : `${rm.maxDrawdownPct}%`,
    underwater: uw.underwater_pct == null ? '—' : `-${Number(uw.underwater_pct).toFixed(2)}%`,
    vol: rm.approxVol == null ? '—' : `${rm.approxVol}%`,
    rolling: rollText,
    topWin: win ? `${win.name} ${formatMoney(win.amount, 0, true)}` : '—',
    topLose: lose ? `${lose.name} ${formatMoney(lose.amount, 0, true)}` : '—',
    equity: equityCat ? formatMoney(equityCat.amount, 0, true) : '—',
    dividendShare: s.dividend_contrib_pct == null ? '—' : `${Number(s.dividend_contrib_pct).toFixed(1)}%`,
    vsBond: bench.bond ? pctText(bench.bond.relative) : '—',
    vsCash: bench.cash ? pctText(bench.cash.relative) : '—',
    twr: pctText(s.twr),
    vsTarget: (xirr == null || target == null)
      ? '—'
      : `${Number(xirr).toFixed(2)}% · ${Number(xirr) - Number(target) >= 0 ? '+' : ''}${(Number(xirr) - Number(target)).toFixed(2)}pt`,
  };
});
</script>

<style scoped>
.perf-flow-alert { margin-bottom: 14px; }

.perf-month-card { margin-bottom: 14px; }
.perf-daily-card { margin-bottom: 14px; }
.perf-daily-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.perf-daily-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.perf-daily-chart { width: 100%; height: 260px; }
.perf-up { color: var(--app-up); font-variant-numeric: tabular-nums; }
.perf-down { color: var(--app-down); font-variant-numeric: tabular-nums; }
.perf-section-title {
  font-weight: 700;
  font-size: 16px;
  color: var(--app-text);
}
.perf-metric-card.is-secondary {
  background: color-mix(in srgb, var(--app-surface) 92%, var(--app-bg0));
}
.perf-cat-list { display: flex; flex-direction: column; gap: 14px; }
.perf-cat-row { display: grid; grid-template-columns: 72px 1fr 110px; gap: 10px; align-items: center; }
.perf-cat-name { font-size: 13px; color: var(--app-muted); }
.perf-cat-track {
  height: 18px;
  background: color-mix(in srgb, var(--app-border) 80%, var(--app-surface));
  border-radius: 999px;
  overflow: hidden;
}
.perf-cat-fill { height: 100%; border-radius: 999px; background: linear-gradient(90deg, var(--app-up), color-mix(in srgb, var(--app-up) 85%, #fff)); }
.perf-cat-fill.is-pos { background: linear-gradient(90deg, color-mix(in srgb, var(--app-up) 55%, transparent), var(--app-up)); }
.perf-cat-fill.is-neg { background: linear-gradient(90deg, color-mix(in srgb, var(--app-down) 55%, transparent), var(--app-down)); }
.perf-cat-amt { text-align: right; font-weight: 650; font-variant-numeric: tabular-nums; font-size: 13px; }
.perf-contrib-table { cursor: pointer; }

/* 收益尺：一张卡里的分段控件 */
.perf-window-strip {
  background: var(--app-surface, #fff);
  border: 1px solid var(--app-border);
  border-radius: 16px;
  box-shadow: var(--app-shadow-sm);
  padding: 18px 22px;
  margin-bottom: 22px;
}
.perf-seg { display: inline-flex; gap: 2px; padding: 3px; max-width: 100%; overflow-x: auto;
  background: color-mix(in srgb, var(--app-bg0) 70%, var(--app-surface));
  border: 1px solid var(--app-border); border-radius: 10px; }
.perf-seg-btn { font: inherit; font-size: 13px; color: var(--app-muted); background: transparent;
  border: 0; border-radius: 7px; padding: 7px 13px; cursor: pointer; white-space: nowrap; }
.perf-seg-btn.is-active { color: var(--app-text); font-weight: 600; background: var(--app-surface); box-shadow: var(--app-shadow-sm); }
.perf-seg-btn:disabled { opacity: .5; cursor: not-allowed; }
.perf-seg-out { display: flex; align-items: flex-end; gap: 14px; flex-wrap: wrap; margin-top: 18px; }
.perf-seg-big { font-size: 34px; font-weight: 700; line-height: 1; font-variant-numeric: tabular-nums;
  font-family: "SF Mono", Menlo, Consolas, ui-monospace, monospace; letter-spacing: -.02em; }
.perf-seg-sub { font-size: 13px; color: var(--app-muted); padding-bottom: 5px; }
.perf-window-strip.is-loading { opacity: .5; pointer-events: none; }

@media (max-width: 640px) {
  .perf-cat-row { grid-template-columns: 64px 1fr 90px; }
  .perf-seg-big { font-size: 28px; }
  .perf-lede-num { font-size: 26px; }
}

/* 结论带 */
.perf-lede-card { margin-bottom: 22px; }
.perf-lede-eyebrow { font-size: 12px; font-weight: 600; color: var(--app-soft); margin-bottom: 8px; }
.perf-lede-line { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.perf-lede-num { font-size: 30px; font-weight: 700; letter-spacing: -.02em; font-variant-numeric: tabular-nums;
  font-family: "SF Mono", Menlo, Consolas, ui-monospace, monospace; }
.perf-lede-pct { font-size: 18px; font-weight: 600; }
.perf-lede-date { font-size: 13px; color: var(--app-muted); }

/* 核心两数：发丝线分格 */
.perf-num-row { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
  background: var(--app-surface); border: 1px solid var(--app-border); border-radius: 16px;
  box-shadow: var(--app-shadow-sm); margin-bottom: 22px; }
.perf-num-cell { padding: 18px 22px; min-width: 0; }
.perf-num-cell + .perf-num-cell { border-left: 1px solid var(--app-hairline); }
.perf-num-cell .k { font-size: 12px; color: var(--app-muted); margin-bottom: 6px; }
.perf-num-cell .v { font-size: 22px; font-weight: 650; font-variant-numeric: tabular-nums; letter-spacing: -.02em;
  font-family: "SF Mono", Menlo, Consolas, ui-monospace, monospace; overflow-wrap: anywhere; }
.perf-num-cell .v.is-warn { color: var(--app-warn); }

/* 简报网格：走势两行 + 风险与归因 */
.perf-brief { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px;
  margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--app-hairline); }
.perf-brief--flush { margin-top: 0; padding-top: 0; border-top: 0; }
.perf-brief-cell { min-width: 0; }
.perf-brief-cell .k { font-size: 12px; color: var(--app-muted); margin-bottom: 5px; }
.perf-brief-cell .v { font-size: 16px; font-weight: 640; font-variant-numeric: tabular-nums; white-space: nowrap;
  font-family: "SF Mono", Menlo, Consolas, ui-monospace, monospace; overflow: hidden; text-overflow: ellipsis; }
.perf-hairline { height: 1px; background: var(--app-hairline); margin-top: 16px; }
.perf-risk-card { margin-bottom: 22px; }

/* 明细折叠区 */
.perf-detail-collapse { margin-bottom: 14px; }
.perf-detail-collapse :deep(.el-collapse) { border-top: 0; border-bottom: 0; }
.perf-detail-collapse :deep(.el-collapse-item__header) { font-size: 14px; font-weight: 600; padding-left: 2px; }
.perf-detail-collapse :deep(.el-collapse-item__wrap) { border-bottom: 0; }
.perf-detail-collapse :deep(.el-collapse-item__content) { padding-bottom: 8px; }

@media (max-width: 800px) {
  .perf-num-row { grid-template-columns: 1fr; }
  .perf-num-cell + .perf-num-cell { border-left: 0; border-top: 1px solid var(--app-hairline); }
  .perf-brief { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
