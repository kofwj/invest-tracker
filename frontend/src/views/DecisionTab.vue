<template>
  <PageShell
    title="今天该看"
    subtitle="左栏结论，右栏市场详情。只读观察，不改真账。"
  >
    <template #actions>
      <el-tag v-if="marketUpdatedAt" size="small" type="info">更新 {{ marketUpdatedAt }}</el-tag>
      <el-tag v-if="quoteCacheSeconds != null" size="small" type="info">行情缓存 {{ quoteCacheSeconds }}s</el-tag>
      <el-button size="small" :loading="marketLoading || disciplineLoading" @click="refreshDecision">刷新</el-button>
      <el-button size="small" type="warning" :loading="alertChecking" @click="() => checkAlerts(false)">立即检查预警</el-button>
    </template>

    <div class="merge-grid decision-merge">
      <!-- 左：结论 -->
      <section class="merge-pane merge-pane-left">
        <div class="merge-pane-title">结论</div>
        <div class="ledger-metrics cols-2 decision-metrics">
          <MetricCard
            label="今日贡献粗估"
            :value="formatMoney(signals.today_contrib_estimate || 0, 2, true)"
            sub="现价涨跌% × 市值，非记账"
            :tone="Number(signals.today_contrib_estimate || 0) >= 0 ? 'up' : 'down'"
            main
            :title="formatMoney(signals.today_contrib_estimate || 0, 2, true)"
          />
          <MetricCard
            label="组合涨跌粗估"
            :value="signals.portfolio_change_pct_estimate == null
              ? '—'
              : ((signals.portfolio_change_pct_estimate >= 0 ? '+' : '') + Number(signals.portfolio_change_pct_estimate).toFixed(2) + '%')"
            :sub="`投资市值 ${formatMoney(signals.total_market_value || 0)}`"
            :tone="Number(signals.portfolio_change_pct_estimate || 0) >= 0 ? 'up' : 'down'"
          />
          <MetricCard
            label="纪律破线"
            :value="String(breachCount)"
            :sub="summaryText || '暂无纪律摘要'"
            :tone="breachCount ? 'warn' : 'ok'"
          />
          <MetricCard
            label="存款 30 天内到期"
            :value="`${dueSoonCount} 笔`"
            :sub="`金额 ${formatMoney(dueSoonAmount)}`"
            :tone="dueSoonCount ? 'warn' : ''"
          />
        </div>

        <el-alert
          :title="headline"
          type="info"
          show-icon
          :closable="false"
          style="margin-bottom: 12px;"
        />

        <el-card v-if="marketHighlights && marketHighlights.length" shadow="never" class="merge-card">
          <template #header><span class="section-title">今天看点</span></template>
          <ul class="market-highlights">
            <li v-for="(line, idx) in marketHighlights" :key="idx">{{ line }}</li>
          </ul>
          <div v-if="marketComparisons && marketComparisons.length" class="market-compare">
            <div v-for="(c, i) in marketComparisons" :key="i">{{ c.text }}</div>
          </div>
        </el-card>

        <div class="decision-jumps">
          <el-button size="small" @click="goTab('allocation')">去结构与目标</el-button>
          <el-button size="small" @click="goTab('deposits')">去存款详情</el-button>
          <el-button size="small" @click="goTab('performance')">去收益分析</el-button>
        </div>
      </section>

      <!-- 右：市场详情 -->
      <section class="merge-pane merge-pane-right">
        <div class="merge-pane-title">市场详情</div>

        <el-card shadow="never" class="merge-card">
          <template #header>
            <div class="card-head">
              <span class="section-title">关键指数</span>
              <span class="hint">东财延时行情</span>
            </div>
          </template>
          <el-table :data="indexRows" stripe size="small" empty-text="暂无指数数据" v-loading="marketLoading">
            <el-table-column prop="name" label="名称" min-width="100" />
            <el-table-column prop="code" label="代码" width="90" />
            <el-table-column label="最新" width="100" align="right" header-align="right">
              <template #default="scope">
                {{ scope.row.price == null ? '—' : Number(scope.row.price).toFixed(2) }}
              </template>
            </el-table-column>
            <el-table-column label="涨跌%" width="90" align="right" header-align="right">
              <template #default="scope">
                <span :style="{ color: changeColor(scope.row.change_pct) }">
                  {{ formatChangePct(scope.row.change_pct) }}
                </span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <el-card shadow="never" class="merge-card">
          <template #header>
            <div class="card-head">
              <span class="section-title">持仓今日贡献（粗估）</span>
              <span class="hint">最多 20 条</span>
            </div>
          </template>
          <el-table :data="holdingsDayRows" stripe size="small" empty-text="暂无持仓或无法估算" v-loading="marketLoading">
            <el-table-column prop="name" label="名称" min-width="110" show-overflow-tooltip />
            <el-table-column prop="code" label="代码" width="90" />
            <el-table-column label="市值" width="100" align="right" header-align="right">
              <template #default="scope"><span class="num-cell">{{ formatMoney(scope.row.market_value) }}</span></template>
            </el-table-column>
            <el-table-column label="涨跌%" width="88" align="right" header-align="right">
              <template #default="scope">
                <span :style="{ color: changeColor(scope.row.change_pct) }">{{ formatChangePct(scope.row.change_pct) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="本日贡献" width="110" align="right" header-align="right">
              <template #default="scope">
                <span class="num-cell" :style="{ color: changeColor(scope.row.day_contrib) }">
                  {{ scope.row.day_contrib == null ? '—' : formatMoney(scope.row.day_contrib, 2, true) }}
                </span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </section>
    </div>

    <!-- 下方：自选 + 预警（全宽） -->
    <el-card shadow="never" class="merge-card">
      <template #header>
        <div class="card-head">
          <div>
            <div class="section-title">自选关注</div>
            <div class="hint">额外代码（股票/指数/ETF）；指数可填 secid（如 1.000300）</div>
          </div>
          <div class="card-actions">
            <el-button size="small" @click="addWatchlistRow">添加一行</el-button>
            <el-button size="small" type="primary" :loading="watchlistSaving" @click="saveWatchlist">保存自选</el-button>
          </div>
        </div>
      </template>
      <el-table :data="watchlistDraft" stripe size="small" empty-text="暂无自选，点「添加一行」">
        <el-table-column label="代码" min-width="110">
          <template #default="scope">
            <el-input v-model="scope.row.code" size="small" placeholder="代码" />
          </template>
        </el-table-column>
        <el-table-column label="名称" min-width="110">
          <template #default="scope">
            <el-input v-model="scope.row.name" size="small" placeholder="可选" />
          </template>
        </el-table-column>
        <el-table-column label="secid" min-width="110">
          <template #default="scope">
            <el-input v-model="scope.row.secid" size="small" placeholder="指数可选" />
          </template>
        </el-table-column>
        <el-table-column label="行情" width="150" align="right" header-align="right">
          <template #default="scope">
            <span v-if="quoteForWatch(scope.row.code)">
              {{ quoteForWatch(scope.row.code).price == null ? '—' : Number(quoteForWatch(scope.row.code).price).toFixed(2) }}
              <span :style="{ color: changeColor(quoteForWatch(scope.row.code).change_pct), marginLeft: '6px' }">
                {{ formatChangePct(quoteForWatch(scope.row.code).change_pct) }}
              </span>
            </span>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center">
          <template #default="scope">
            <el-button type="danger" link @click="removeWatchlistRow(scope.$index)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="merge-card">
      <template #header>
        <div class="card-head">
          <div>
            <div class="section-title">价格预警规则</div>
            <div class="hint">
              持仓或指数代码，上穿/下穿阈值。同规则默认 {{ alertCooldownMinutes == null ? 240 : alertCooldownMinutes }} 分钟内不重复。
            </div>
          </div>
          <el-button type="primary" size="small" @click="openAlertCreate">添加规则</el-button>
        </div>
      </template>
      <el-table :data="alertRules" stripe size="small" empty-text="暂无规则">
        <el-table-column label="类型" width="80">
          <template #default="scope">{{ scope.row.target_type === 'index' ? '指数' : '持仓' }}</template>
        </el-table-column>
        <el-table-column prop="name" label="名称" min-width="110" show-overflow-tooltip />
        <el-table-column prop="code" label="代码" width="90" />
        <el-table-column label="条件" width="88">
          <template #default="scope">{{ scope.row.condition === 'below' ? '≤ 下穿' : '≥ 上穿' }}</template>
        </el-table-column>
        <el-table-column label="阈值" width="100" align="right" header-align="right">
          <template #default="scope">{{ Number(scope.row.threshold).toFixed(4) }}</template>
        </el-table-column>
        <el-table-column label="启用" width="72" align="center">
          <template #default="scope">
            <el-switch
              :model-value="Number(scope.row.enabled) === 1 || scope.row.enabled === true"
              @change="() => toggleAlertEnabled(scope.row)"
            />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" align="center">
          <template #default="scope">
            <el-button type="primary" link @click="openAlertEdit(scope.row)">编辑</el-button>
            <el-button type="danger" link @click="deleteAlertRule(scope.row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card v-if="triggeredAlerts && triggeredAlerts.length" shadow="never" class="merge-card">
      <template #header><span class="section-title">最近一次检查触发</span></template>
      <el-table :data="triggeredAlerts" stripe size="small">
        <el-table-column prop="message" label="说明" min-width="240" show-overflow-tooltip />
        <el-table-column prop="price" label="触发价" width="100" align="right" header-align="right">
          <template #default="scope">{{ Number(scope.row.price).toFixed(4) }}</template>
        </el-table-column>
        <el-table-column label="涨跌%" width="90" align="right" header-align="right">
          <template #default="scope">
            <span :style="{ color: changeColor(scope.row.change_pct) }">{{ formatChangePct(scope.row.change_pct) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="trigger_time" label="时间" width="160" />
      </el-table>
    </el-card>

    <el-card shadow="never" class="merge-card">
      <template #header>
        <div class="card-head">
          <div>
            <div class="section-title">预警历史</div>
            <div class="hint">来自 alert_events</div>
          </div>
          <div class="card-actions">
            <el-input
              v-model="alertEventCodeFilter"
              clearable
              placeholder="按代码筛选"
              style="width:120px"
              size="small"
              @keyup.enter="fetchAlertEvents"
            />
            <el-date-picker
              v-model="alertEventStartDate"
              type="date"
              value-format="YYYY-MM-DD"
              placeholder="开始"
              size="small"
              style="width:130px"
            />
            <el-date-picker
              v-model="alertEventEndDate"
              type="date"
              value-format="YYYY-MM-DD"
              placeholder="结束"
              size="small"
              style="width:130px"
            />
            <el-button size="small" :loading="alertEventsLoading" @click="fetchAlertEvents">刷新</el-button>
            <el-button size="small" @click="exportAlertEvents">导出</el-button>
            <el-button size="small" type="danger" plain @click="clearAlertEvents">清空</el-button>
          </div>
        </div>
      </template>
      <el-table :data="alertEvents" stripe size="small" empty-text="暂无触发记录" v-loading="alertEventsLoading">
        <el-table-column prop="target_code" label="代码" width="90" />
        <el-table-column prop="message" label="说明" min-width="240" show-overflow-tooltip />
        <el-table-column label="触发价" width="100" align="right" header-align="right">
          <template #default="scope">
            {{ scope.row.triggered_price == null ? '—' : Number(scope.row.triggered_price).toFixed(4) }}
          </template>
        </el-table-column>
        <el-table-column label="阈值" width="90" align="right" header-align="right">
          <template #default="scope">
            {{ scope.row.threshold == null ? '—' : Number(scope.row.threshold).toFixed(4) }}
          </template>
        </el-table-column>
        <el-table-column prop="trigger_time" label="时间" width="160" />
      </el-table>
    </el-card>

    <el-dialog v-model="alertEditDialog" :title="alertForm.id ? '编辑预警' : '添加预警'" width="460px" destroy-on-close>
      <el-form label-width="88px">
        <el-form-item label="类型">
          <el-select v-model="alertForm.target_type" style="width:100%">
            <el-option label="持仓" value="holding" />
            <el-option label="指数" value="index" />
          </el-select>
        </el-form-item>
        <el-form-item label="代码">
          <el-input v-model="alertForm.code" placeholder="如 159352 或 000300" />
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="alertForm.name" placeholder="可选" />
        </el-form-item>
        <el-form-item label="条件">
          <el-select v-model="alertForm.condition" style="width:100%">
            <el-option label="上穿 ≥ 阈值" value="above" />
            <el-option label="下穿 ≤ 阈值" value="below" />
          </el-select>
        </el-form-item>
        <el-form-item label="阈值">
          <el-input-number v-model="alertForm.threshold" :min="0" :step="0.01" :precision="4" style="width:100%" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="alertForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="alertEditDialog = false">取消</el-button>
        <el-button type="primary" @click="saveAlertRule">保存</el-button>
      </template>
    </el-dialog>
  </PageShell>
</template>

<script setup>
import PageShell from '../components/PageShell.vue';
import MetricCard from '../components/MetricCard.vue';
import { computed, onMounted } from 'vue';
import { useAppCtx } from '../composables/useAppCtx.js';

const {
  goTab,
  marketSignals,
  marketLoading,
  refreshMarket,
  breaches,
  summaryText,
  disciplineLoading,
  refreshDiscipline,
  depositRows,
  formatMoney,
  alertChecking,
  alertEventsLoading,
  alertRules,
  alertEvents,
  alertEventCodeFilter,
  alertEventStartDate,
  alertEventEndDate,
  watchlistDraft,
  watchlistSaving,
  alertForm,
  alertEditDialog,
  triggeredAlerts,
  indexRows,
  watchlistRows,
  holdingsDayRows,
  marketHighlights,
  marketComparisons,
  marketUpdatedAt,
  quoteCacheSeconds,
  alertCooldownMinutes,
  openAlertCreate,
  openAlertEdit,
  saveAlertRule,
  deleteAlertRule,
  toggleAlertEnabled,
  checkAlerts,
  fetchAlertEvents,
  exportAlertEvents,
  clearAlertEvents,
  addWatchlistRow,
  removeWatchlistRow,
  saveWatchlist,
} = useAppCtx();

const breachCount = computed(() => {
  const list = breaches?.value ?? breaches ?? [];
  return Array.isArray(list) ? list.length : 0;
});

const dueSoonRows = computed(() => {
  const rows = depositRows?.value ?? depositRows ?? [];
  return (Array.isArray(rows) ? rows : [])
    .filter((d) => d.daysLeft !== null && d.daysLeft !== undefined && Number(d.daysLeft) <= 30)
    .slice()
    .sort((a, b) => Number(a.daysLeft) - Number(b.daysLeft))
    .slice(0, 12);
});

const dueSoonCount = computed(() => dueSoonRows.value.length);
const dueSoonAmount = computed(() => dueSoonRows.value.reduce((s, r) => s + Number(r.amount || 0), 0));
const signals = computed(() => marketSignals?.value ?? marketSignals ?? {});

const headline = computed(() => {
  const parts = [];
  const sig = signals.value || {};
  if (sig.portfolio_vs_market) parts.push(sig.portfolio_vs_market);
  if (breachCount.value) parts.push(`纪律破线 ${breachCount.value} 条`);
  if (dueSoonCount.value) parts.push(`存款近 30 天到期 ${dueSoonCount.value} 笔`);
  return parts.length ? parts.join(' · ') : '先刷新：看贡献、纪律、存款到期，再决定要不要动手。';
});

const formatChangePct = (v) => {
  if (v === null || v === undefined || v === '') return '—';
  const n = Number(v);
  if (Number.isNaN(n)) return '—';
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`;
};

const changeColor = (v) => {
  if (v === null || v === undefined || v === '') return '#909399';
  const n = Number(v);
  if (Number.isNaN(n) || n === 0) return '#909399';
  return n > 0 ? '#F56C6C' : '#67C23A';
};

const quoteForWatch = (code) => {
  const c = String(code || '').trim();
  if (!c) return null;
  const rows = watchlistRows?.value ?? watchlistRows ?? [];
  return (Array.isArray(rows) ? rows : []).find((x) => String(x.code) === c) || null;
};

async function refreshDecision() {
  await Promise.all([
    typeof refreshMarket === 'function' ? refreshMarket() : Promise.resolve(),
    typeof refreshDiscipline === 'function' ? refreshDiscipline() : Promise.resolve(),
  ]);
}

onMounted(() => {
  refreshDecision();
  if (typeof fetchAlertEvents === 'function') fetchAlertEvents();
});
</script>

<style scoped>
.merge-grid {
  display: grid;
  grid-template-columns: minmax(280px, 0.95fr) minmax(0, 1.15fr);
  gap: 14px;
  margin-bottom: 14px;
  align-items: start;
}
.merge-pane {
  min-width: 0;
  border: 1px solid var(--app-border);
  border-radius: 14px;
  background: var(--app-surface);
  padding: 14px;
}
.merge-pane-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--app-muted);
  margin-bottom: 10px;
  letter-spacing: 0.02em;
}
.decision-metrics { margin-bottom: 10px; }
.merge-card { margin-bottom: 14px; }
.section-title { font-size: 15px; font-weight: 700; color: var(--app-text); }
.hint { font-size: 12px; color: var(--app-soft); margin-top: 2px; }
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
  flex-wrap: wrap;
}
.card-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.decision-jumps {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 4px;
}
.market-highlights {
  margin: 0;
  padding-left: 18px;
  color: var(--app-text);
  line-height: 1.7;
  font-size: 13px;
}
.market-compare {
  margin-top: 8px;
  font-size: 12px;
  color: var(--app-muted);
  line-height: 1.5;
}
.muted { color: var(--app-soft); }
@media (max-width: 960px) {
  .merge-grid { grid-template-columns: 1fr; }
}
</style>
