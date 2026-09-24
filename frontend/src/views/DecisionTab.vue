<template>
  <PageShell>
    <template #actions>
      <el-tag v-if="marketUpdatedAt" size="small" type="info">更新 {{ marketUpdatedAt }}</el-tag>
      <el-tag v-if="quoteCacheSeconds != null" size="small" type="info">行情缓存 {{ quoteCacheSeconds }}s</el-tag>
      <el-button size="small" :loading="marketLoading || disciplineLoading" @click="refreshDecision">刷新</el-button>
      <el-button size="small" type="warning" :loading="alertChecking" @click="onCheckAlerts">立即检查预警</el-button>
    </template>

    <div v-if="(marketLoading || disciplineLoading) && !marketUpdatedAt" class="sk-metrics" aria-hidden="true">
      <div v-for="i in 6" :key="'dsk'+i" class="sk-block sk-metric"></div>
    </div>

    <!-- ① 今天该看什么：默认展开，第一屏就是结论 -->
    <section class="decision-group" aria-labelledby="decision-group-today">
      <div class="group-head">
        <h2 id="decision-group-today" class="group-title">今天该看什么</h2>
      </div>

      <div class="group-block-title section-title">市场与结论</div>

      <el-card shadow="never" class="merge-card highlight-card">
        <template #header>
          <div class="card-head">
            <span class="section-title">今日看点</span>
            <span class="hint">人话结论，不是买卖指令</span>
          </div>
        </template>
        <ul v-if="marketHighlights && marketHighlights.length" class="market-highlights">
          <li v-for="(line, idx) in marketHighlights" :key="idx">{{ line }}</li>
        </ul>
        <div v-else class="empty-line">暂无看点，点右上角刷新拉行情。</div>
        <div v-if="marketComparisons && marketComparisons.length" class="market-compare">
          <div v-for="(c, i) in marketComparisons" :key="i">{{ c.text }}</div>
        </div>
      </el-card>

      <el-alert
        :title="headline"
        type="info"
        show-icon
        :closable="false"
        class="decision-headline"
      />

      <!-- 行情带：关键指标一行 + 破线摘要一行 -->
      <div class="market-band">
        <div class="band-row">
          <div class="band-label section-title">关键指标</div>
          <!-- 12 个粗估指标：新版排版（发丝线简报网格），不再是一排卡片 -->
          <div class="app-brief cols-4 band-brief">
            <div class="app-brief-cell">
              <div class="k">今日贡献粗估</div>
              <div class="v" :class="Number(signals.today_contrib_estimate || 0) >= 0 ? 'up' : 'down'" :title="formatMoney(signals.today_contrib_estimate || 0, 2, true)">{{ formatMoney(signals.today_contrib_estimate || 0, 2, true) }}</div>
            </div>
            <div class="app-brief-cell">
              <div class="k">组合涨跌粗估</div>
              <div class="v" :class="toneFromNum(signals.portfolio_change_pct_estimate)">{{ pctText(signals.portfolio_change_pct_estimate) }}</div>
            </div>
            <div class="app-brief-cell">
              <div class="k">vs 沪深300</div>
              <div class="v" :class="toneFromNum(vsHs300Diff)">{{ vsHs300Text }}</div>
            </div>
            <div class="app-brief-cell">
              <div class="k">vs 中证A500</div>
              <div class="v" :class="toneFromNum(vsA500Diff)">{{ vsA500Text }}</div>
            </div>
            <div class="app-brief-cell">
              <div class="k">总资产</div>
              <div class="v" :title="formatMoney(totalAssetsNow)">{{ formatMoney(totalAssetsNow) }}</div>
            </div>
            <div class="app-brief-cell">
              <div class="k">权益仓位</div>
              <div class="v" :class="equityTone">{{ equityPctText }}</div>
            </div>
            <div class="app-brief-cell">
              <div class="k">纪律破线</div>
              <div class="v" :class="breachCount ? 'warn' : 'ok'">{{ String(breachCount) }}</div>
            </div>
            <div class="app-brief-cell">
              <div class="k">存款 30 天内到期</div>
              <div class="v" :class="dueSoonCount ? 'warn' : ''">{{ `${dueSoonCount} 笔` }}</div>
            </div>
            <div class="app-brief-cell">
              <div class="k">今日最强</div>
              <div class="v" :class="toneFromNum(topMover?.day_contrib ?? topMover?.change_pct)" :title="topMoverTitle">{{ topMoverName }}</div>
            </div>
            <div class="app-brief-cell">
              <div class="k">今日最弱</div>
              <div class="v" :class="toneFromNum(bottomMover?.day_contrib ?? bottomMover?.change_pct)" :title="bottomMoverTitle">{{ bottomMoverName }}</div>
            </div>
            <div class="app-brief-cell">
              <div class="k">启用预警</div>
              <div class="v" :class="enabledAlertCount ? 'ok' : 'muted'">{{ `${enabledAlertCount} 条` }}</div>
            </div>
            <div class="app-brief-cell">
              <div class="k">指数情绪</div>
              <div class="v" :class="indexBreadthTone">{{ indexBreadthText }}</div>
            </div>
          </div>
        </div>

        <div v-if="breachPreview.length" class="band-row band-breach">
          <div class="band-label section-title">破线摘要</div>
          <ul class="breach-list breach-inline">
            <li v-for="(b, idx) in breachPreview" :key="idx">
              <span class="breach-level" :class="b.level === 'warning' ? 'warn' : 'info'">{{ b.level === 'warning' ? '警告' : '提示' }}</span>
              <span class="breach-text">{{ b.line || b.title || '纪律提醒' }}</span>
            </li>
          </ul>
          <el-button size="small" link type="primary" @click="goTab('allocation')">去结构与目标</el-button>
        </div>

        <div class="decision-jumps">
          <el-button size="small" @click="goTab('allocation')">去结构与目标</el-button>
          <el-button size="small" @click="goTab('deposits')">去存款详情</el-button>
          <el-button size="small" @click="goTab('performance')">去收益分析</el-button>
          <el-button size="small" @click="goTab('holdings')">去持仓</el-button>
        </div>
      </div>
    </section>

    <!-- ② 我的持仓今天怎么样：默认展开 -->
    <section class="decision-group" aria-labelledby="decision-group-holdings">
      <div class="group-head">
        <h2 id="decision-group-holdings" class="group-title">我的持仓今天怎么样</h2>
      </div>

      <el-card shadow="never" class="merge-card">
        <template #header>
          <div class="card-head">
            <span class="section-title">持仓今日贡献（粗估）</span>
            <span class="hint">最多 20 条 · 按绝对贡献排序</span>
          </div>
        </template>
        <el-table :data="holdingsDayRows" stripe size="small" empty-text="暂无持仓或无法估算" v-loading="marketLoading" aria-label="持仓今日贡献">
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

    <!-- ③ 观察与预警：默认收起（el-collapse），功能一个不少 -->
    <section class="decision-group" aria-labelledby="decision-group-observe">
      <el-collapse v-model="observeOpen" class="decision-collapse">
        <el-collapse-item name="observe">
          <template #title>
            <div class="group-head is-in-collapse">
              <h2 id="decision-group-observe" class="group-title">观察与预警</h2>
              <span class="group-hint">
                {{ indexList.length }} 指数 · {{ watchlistCount }} 自选 · {{ alertRuleCount }} 条规则（启用 {{ enabledAlertCount }}）· 默认收起
              </span>
            </div>
          </template>

          <div class="observe-body">
            <el-card shadow="never" class="merge-card">
              <template #header>
                <div class="card-head">
                  <span class="section-title">关键指数</span>
                  <span class="hint">东财延时行情</span>
                </div>
              </template>
              <el-table :data="indexRows" stripe size="small" empty-text="暂无指数数据" v-loading="marketLoading" aria-label="关键指数">
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
                  <div>
                    <div class="section-title">自选关注</div>
                    <div class="hint">额外代码（股票/指数/ETF）；指数可填 secid（如 1.000300）</div>
                  </div>
                  <div class="card-actions">
                    <el-button size="small" @click="addWatchlistRow">添加一行</el-button>
                    <el-button size="small" type="primary" :loading="watchlistSaving" @click="onSaveWatchlist">保存自选</el-button>
                  </div>
                </div>
              </template>
              <el-table :data="watchlistDraft" stripe size="small" empty-text="暂无自选，点「添加一行」" aria-label="自选关注">
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
              <el-table :data="alertRules" stripe size="small" empty-text="暂无规则" aria-label="价格预警规则">
                <el-table-column label="监控" width="118">
                  <template #default="scope">{{
                    scope.row.rule_type === 'portfolio_pnl' ? '组合盈亏'
                      : scope.row.rule_type === 'change_pct' ? '日内涨跌%'
                        : (scope.row.target_type === 'index' ? '指数价' : '持仓价')
                  }}</template>
                </el-table-column>
                <el-table-column prop="name" label="名称" min-width="110" show-overflow-tooltip />
                <el-table-column prop="code" label="代码" width="90" />
                <el-table-column label="条件" width="88">
                  <template #default="scope">{{ scope.row.condition === 'below' ? '≤ 下穿' : '≥ 上穿' }}</template>
                </el-table-column>
                <el-table-column label="阈值" width="100" align="right" header-align="right">
                  <!-- 百分比类规则带符号，按 2 位显示；价格类仍是 4 位 -->
                  <template #default="scope">
                    {{ scope.row.rule_type && scope.row.rule_type !== 'price'
                      ? `${Number(scope.row.threshold).toFixed(2)}%`
                      : Number(scope.row.threshold).toFixed(4) }}
                  </template>
                </el-table-column>
                <el-table-column label="启用" width="72" align="center">
                  <template #default="scope">
                    <el-switch
                      :model-value="Number(scope.row.enabled) === 1 || scope.row.enabled === true"
                      :disabled="!!alertRuleBusy"
                      @change="onToggleAlertEnabled(scope.row)"
                    />
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="140" align="center">
                  <template #default="scope">
                    <el-button type="primary" link @click="openAlertEdit(scope.row)">编辑</el-button>
                    <el-button type="danger" link :loading="alertRuleBusy === 'delete:' + scope.row.id" :disabled="!!alertRuleBusy" @click="onDeleteAlertRule(scope.row)">删除</el-button>
                  </template>
                </el-table-column>
              </el-table>
            </el-card>

            <el-card v-if="triggeredAlerts && triggeredAlerts.length" shadow="never" class="merge-card">
              <template #header><span class="section-title">最近一次检查触发</span></template>
              <el-table :data="triggeredAlerts" stripe size="small" aria-label="最近一次检查触发">
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
                    <el-button size="small" type="danger" plain :loading="alertClearing" @click="onClearAlertEvents">清空</el-button>
                  </div>
                </div>
              </template>
              <el-table :data="alertEvents" stripe size="small" empty-text="暂无触发记录" v-loading="alertEventsLoading" aria-label="预警历史">
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
          </div>
        </el-collapse-item>
      </el-collapse>
    </section>

    <el-dialog v-model="alertEditDialog" :title="alertForm.id ? '编辑预警' : '添加预警'" width="460px" destroy-on-close>
      <el-form label-width="88px">
        <el-form-item label="监控">
          <el-select v-model="alertForm.rule_type" style="width:100%">
            <el-option label="价格（绝对价）" value="price" />
            <el-option label="日内涨跌幅 %" value="change_pct" />
            <el-option label="组合当日盈亏 %" value="portfolio_pnl" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="alertForm.rule_type !== 'portfolio_pnl'" label="类型">
          <el-select v-model="alertForm.target_type" style="width:100%">
            <el-option label="持仓" value="holding" />
            <el-option label="指数" value="index" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="alertForm.rule_type !== 'portfolio_pnl'" label="代码">
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
          <!-- 百分比类阈值是带符号的（below −2 = 跌到 −2%）；:min 必须放开，
               否则 element-plus 会把 −2 clamp 成 0，规则变成"任何下跌日都触发"。 -->
          <el-input-number
            v-model="alertForm.threshold"
            :min="alertForm.rule_type === 'price' ? 0 : -100"
            :max="alertForm.rule_type === 'price' ? undefined : 100"
            :step="alertForm.rule_type === 'price' ? 0.01 : 0.5"
            :precision="alertForm.rule_type === 'price' ? 4 : 2"
            style="width:100%"
          />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="alertForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="alertEditDialog = false">取消</el-button>
        <el-button type="primary" :loading="alertRuleSaving" @click="onSaveAlertRule">保存</el-button>
      </template>
    </el-dialog>
  </PageShell>
</template>

<script setup>
import PageShell from '../components/PageShell.vue';
import { computed, onMounted, ref } from 'vue';
import { useAppCtx } from '../composables/useAppCtx.js';
import { formatPercent } from '../utils/index.js';

const {
  goTab,
  dashboard,
  marketSignals,
  marketLoading,
  refreshMarket,
  breaches,
  summaryText,
  snapshot,
  targets,
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

const signals = computed(() => marketSignals?.value ?? marketSignals ?? {});
const disciplineSnap = computed(() => snapshot?.value ?? snapshot ?? {});
const disciplineTargets = computed(() => targets?.value ?? targets ?? {});

const breachList = computed(() => {
  const list = breaches?.value ?? breaches ?? [];
  return Array.isArray(list) ? list : [];
});
/** 真正需要看的：去掉 level=ok 的状态项 */
const attentionBreaches = computed(() =>
  breachList.value.filter((b) => {
    const level = String(b?.level || '').toLowerCase();
    return level && level !== 'ok';
  }),
);
const breachCount = computed(() => attentionBreaches.value.length);
const breachPreview = computed(() =>
  attentionBreaches.value.slice(0, 5).map((b) => ({
    ...b,
    line: [b.title, b.text || b.message || b.rule].filter(Boolean).join('：'),
  })),
);

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

const totalAssetsNow = computed(() => {
  const fromDash = Number((dashboard?.value ?? dashboard)?.total_assets || 0);
  if (fromDash > 0) return fromDash;
  return Number(disciplineSnap.value.total_assets || 0);
});

const equityPct = computed(() => Number(disciplineSnap.value.equity_pct ?? NaN));
const defensivePct = computed(() => Number(disciplineSnap.value.defensive_pct ?? NaN));
const equityPctText = computed(() => (Number.isFinite(equityPct.value) ? `${equityPct.value.toFixed(1)}%` : '—'));
const defensivePctText = computed(() => (Number.isFinite(defensivePct.value) ? `${defensivePct.value.toFixed(1)}%` : '—'));
const targetEquity = computed(() => Number(disciplineTargets.value.equity_pct ?? NaN));
const targetEquityText = computed(() => (Number.isFinite(targetEquity.value) ? `${targetEquity.value.toFixed(0)}%` : '—'));
const equityTone = computed(() => {
  if (!Number.isFinite(equityPct.value) || !Number.isFinite(targetEquity.value)) return '';
  const band = Number(disciplineTargets.value.band_pct ?? 5);
  const gap = Math.abs(equityPct.value - targetEquity.value);
  if (gap > band) return 'warn';
  return 'ok';
});

const comparisonMap = computed(() => {
  const list = marketComparisons?.value ?? marketComparisons ?? [];
  const map = {};
  (Array.isArray(list) ? list : []).forEach((c) => {
    if (c?.benchmark) map[c.benchmark] = c;
  });
  return map;
});

const vsHs300 = computed(() => comparisonMap.value['沪深300'] || null);
const vsA500 = computed(() => comparisonMap.value['中证A500'] || null);
const vsHs300Diff = computed(() => (vsHs300.value ? Number(vsHs300.value.diff_pct) : null));
const vsA500Diff = computed(() => (vsA500.value ? Number(vsA500.value.diff_pct) : null));
const vsHs300Text = computed(() => {
  if (vsHs300Diff.value === null || Number.isNaN(vsHs300Diff.value)) return '—';
  const n = vsHs300Diff.value;
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}pt`;
});
const vsA500Text = computed(() => {
  if (vsA500Diff.value === null || Number.isNaN(vsA500Diff.value)) return '—';
  const n = vsA500Diff.value;
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}pt`;
});
const vsHs300Sub = computed(() => {
  if (!vsHs300.value) return '缺组合或指数涨跌';
  return `组合 ${pctText(vsHs300.value.portfolio_pct)} · 指数 ${pctText(vsHs300.value.benchmark_pct)}`;
});
const vsA500Sub = computed(() => {
  if (!vsA500.value) return '缺组合或指数涨跌';
  return `组合 ${pctText(vsA500.value.portfolio_pct)} · 指数 ${pctText(vsA500.value.benchmark_pct)}`;
});

const dayRows = computed(() => {
  const rows = holdingsDayRows?.value ?? holdingsDayRows ?? [];
  return Array.isArray(rows) ? rows : [];
});
const withContrib = computed(() => dayRows.value.filter((r) => r && r.day_contrib != null));
const topMover = computed(() => {
  if (!withContrib.value.length) return null;
  return withContrib.value.reduce((best, r) => (Number(r.day_contrib) > Number(best.day_contrib) ? r : best));
});
const bottomMover = computed(() => {
  if (!withContrib.value.length) return null;
  return withContrib.value.reduce((worst, r) => (Number(r.day_contrib) < Number(worst.day_contrib) ? r : worst));
});
const topMoverName = computed(() => topMover.value?.name || topMover.value?.code || '—');
const bottomMoverName = computed(() => bottomMover.value?.name || bottomMover.value?.code || '—');
const topMoverSub = computed(() => {
  const r = topMover.value;
  if (!r) return '暂无持仓贡献';
  return `${formatMoney(r.day_contrib, 2, true)} · ${pctText(r.change_pct)}`;
});
const bottomMoverSub = computed(() => {
  const r = bottomMover.value;
  if (!r) return '暂无持仓贡献';
  return `${formatMoney(r.day_contrib, 2, true)} · ${pctText(r.change_pct)}`;
});
const topMoverTitle = computed(() => (topMover.value ? `${topMoverName.value} ${topMoverSub.value}` : ''));
const bottomMoverTitle = computed(() => (bottomMover.value ? `${bottomMoverName.value} ${bottomMoverSub.value}` : ''));

const alertRuleList = computed(() => {
  const list = alertRules?.value ?? alertRules ?? [];
  return Array.isArray(list) ? list : [];
});
const alertRuleCount = computed(() => alertRuleList.value.length);
const enabledAlertCount = computed(() => alertRuleList.value.filter((r) => Number(r.enabled) === 1 || r.enabled === true).length);
const watchlistCount = computed(() => {
  const rows = watchlistDraft?.value ?? watchlistDraft ?? [];
  return Array.isArray(rows) ? rows.filter((x) => String(x.code || '').trim()).length : 0;
});

const indexList = computed(() => {
  const rows = indexRows?.value ?? indexRows ?? [];
  return Array.isArray(rows) ? rows : [];
});
const indexBreadth = computed(() => {
  const withChg = indexList.value.filter((r) => r && r.change_pct != null && !Number.isNaN(Number(r.change_pct)));
  const up = withChg.filter((r) => Number(r.change_pct) > 0).length;
  const down = withChg.filter((r) => Number(r.change_pct) < 0).length;
  const flat = withChg.length - up - down;
  return { up, down, flat, total: withChg.length };
});
const indexBreadthText = computed(() => {
  const b = indexBreadth.value;
  if (!b.total) return '—';
  return `${b.up} 涨 / ${b.down} 跌`;
});
const indexBreadthSub = computed(() => {
  const b = indexBreadth.value;
  if (!b.total) return '暂无指数';
  const best = indexList.value
    .filter((r) => r.change_pct != null)
    .slice()
    .sort((a, c) => Number(c.change_pct) - Number(a.change_pct))[0];
  const worst = indexList.value
    .filter((r) => r.change_pct != null)
    .slice()
    .sort((a, c) => Number(a.change_pct) - Number(c.change_pct))[0];
  if (!best || !worst) return `共 ${b.total} 个指数`;
  return `强 ${best.name || best.code} ${pctText(best.change_pct)} · 弱 ${worst.name || worst.code} ${pctText(worst.change_pct)}`;
});
const indexBreadthTone = computed(() => {
  const b = indexBreadth.value;
  if (!b.total) return '';
  if (b.up > b.down) return 'up';
  if (b.down > b.up) return 'down';
  return 'muted';
});

const headline = computed(() => {
  const parts = [];
  const sig = signals.value || {};
  if (sig.portfolio_vs_market) parts.push(sig.portfolio_vs_market);
  if (breachCount.value) parts.push(`纪律破线 ${breachCount.value} 条`);
  if (dueSoonCount.value) parts.push(`存款近 30 天到期 ${dueSoonCount.value} 笔`);
  if (Number.isFinite(equityPct.value) && Number.isFinite(targetEquity.value)) {
    const gap = equityPct.value - targetEquity.value;
    if (Math.abs(gap) >= Number(disciplineTargets.value.band_pct ?? 5)) {
      parts.push(`权益仓位 ${equityPct.value.toFixed(1)}%（目标 ${targetEquity.value.toFixed(0)}%）`);
    }
  }
  return parts.length ? parts.join(' · ') : '先刷新：看贡献、对大盘、仓位、纪律、存款到期，再决定要不要动手。';
});

function pctText(v) {
  if (v === null || v === undefined || v === '') return '—';
  const n = Number(v);
  if (Number.isNaN(n)) return '—';
  return formatPercent(n, 2);
}

function toneFromNum(v) {
  if (v === null || v === undefined || v === '') return '';
  const n = Number(v);
  if (Number.isNaN(n) || n === 0) return 'muted';
  return n > 0 ? 'up' : 'down';
}

const formatChangePct = (v) => pctText(v);

const changeColor = (v) => {
  if (v === null || v === undefined || v === '') return 'var(--app-muted)';
  const n = Number(v);
  if (Number.isNaN(n) || n === 0) return 'var(--app-muted)';
  return n > 0 ? 'var(--app-up)' : 'var(--app-down)';
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

// 清空预警历史是 DELETE，模块里没有 in-flight 标志，本页包一层防连点。
const alertClearing = ref(false);

async function onClearAlertEvents() {
  if (alertClearing.value) return;
  alertClearing.value = true;
  try {
    await clearAlertEvents();
  } finally {
    alertClearing.value = false;
  }
}

// 写操作防连点：alertChecking / watchlistSaving 是模块里同步置位的现成标志，复用它做入口闸门；
// 预警规则的增删改模块里没有标志，用本页 ref 兜住（同一行按钮转圈、其余行禁用）。
const alertRuleBusy = ref('');
const alertRuleSaving = ref(false);

// 第三组「观察与预警」默认收起：空数组 = 全部折叠；里面 5 个区块的功能与请求一个都没删。
const observeOpen = ref([]);

async function onCheckAlerts() {
  if (alertChecking?.value) return;
  await checkAlerts(false);
}

async function onSaveWatchlist() {
  if (watchlistSaving?.value) return;
  await saveWatchlist();
}

async function runAlertRuleWrite(key, fn) {
  if (alertRuleBusy.value) return;
  alertRuleBusy.value = key;
  try {
    await fn();
  } finally {
    if (alertRuleBusy.value === key) alertRuleBusy.value = '';
  }
}

const onToggleAlertEnabled = (row) => runAlertRuleWrite(`toggle:${row?.id}`, () => toggleAlertEnabled(row));
const onDeleteAlertRule = (row) => runAlertRuleWrite(`delete:${row?.id}`, () => deleteAlertRule(row));

async function onSaveAlertRule() {
  if (alertRuleSaving.value) return;
  alertRuleSaving.value = true;
  try {
    await saveAlertRule();
  } finally {
    alertRuleSaving.value = false;
  }
}

onMounted(() => {
  refreshDecision();
  if (typeof fetchAlertEvents === 'function') fetchAlertEvents();
});
</script>

<style scoped>
/* 三组区块：① 今天该看什么 ② 我的持仓今天怎么样 ③ 观察与预警（默认收起） */
.decision-group { margin-bottom: 18px; }
.decision-group:last-of-type { margin-bottom: 0; }
.group-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 10px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--app-border);
}
.group-title {
  margin: 0;
  font-size: 16px;
  font-weight: 800;
  color: var(--app-text);
  letter-spacing: 0.01em;
}
.group-hint { font-size: 12px; color: var(--app-soft); }
.group-block-title { margin-bottom: 8px; }
/* 折叠标题栏里的组标题：边框交给 el-collapse 自己的分隔线 */
.group-head.is-in-collapse {
  margin-bottom: 0;
  padding-bottom: 0;
  border-bottom: none;
  width: 100%;
}
/* 行情带：一行关键指标 + 一行破线摘要，窄屏横向滚动，信息不裁 */
.market-band {
  border: 1px solid var(--app-border);
  border-radius: 14px;
  background: var(--app-surface);
  padding: 10px 12px;
}
.band-row {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.band-row + .band-row {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--app-border);
}
/* 破线摘要行：和其它行情行区分开 */
.band-breach { border-left: 3px solid var(--app-warn); padding-left: 10px; }
.band-label { flex: 0 0 auto; font-size: 12.5px; white-space: nowrap; }
.band-brief { flex: 1 1 auto; min-width: 0; }
.breach-inline {
  display: flex;
  flex-wrap: nowrap;
  gap: 14px;
  flex: 1 1 auto;
  min-width: 0;
  margin: 0;
  padding: 0;
  list-style: none;
  overflow-x: auto;
}
.breach-inline li {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  white-space: nowrap;
}
.breach-text { color: var(--app-text); }
.decision-collapse { border: none; }
.decision-collapse :deep(.el-collapse-item__header) {
  height: auto;
  min-height: 46px;
  padding: 6px 2px;
  border-bottom: 1px solid var(--app-border);
  background: transparent;
}
.decision-collapse :deep(.el-collapse-item__wrap) { border: none; background: transparent; }
.decision-collapse :deep(.el-collapse-item__content) { padding: 14px 2px 2px; }
.observe-body .merge-card:last-child { margin-bottom: 0; }
.decision-headline { margin-bottom: 12px; }
.merge-card { margin-bottom: 14px; }
.highlight-card {
  border-color: color-mix(in srgb, var(--app-primary) 28%, var(--app-border));
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--app-primary) 6%, var(--app-surface)), var(--app-surface));
}
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
  line-height: 1.75;
  font-size: 13.5px;
}
.market-compare {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--app-border);
  font-size: 12px;
  color: var(--app-muted);
  line-height: 1.55;
}
.breach-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 8px;
}
.breach-list li {
  font-size: 12.5px;
  color: var(--app-text);
  line-height: 1.45;
  display: flex;
  gap: 8px;
  align-items: flex-start;
}
.breach-level {
  flex: 0 0 auto;
  font-size: 11px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 999px;
  border: 1px solid var(--app-border);
  color: var(--app-muted);
}
.breach-level.warn {
  color: var(--app-warn);
  background: var(--app-warn-soft);
  border-color: color-mix(in srgb, var(--app-warn) 30%, var(--app-border));
}
.breach-level.info {
  color: var(--app-info);
  background: var(--app-info-soft);
  border-color: color-mix(in srgb, var(--app-info) 30%, var(--app-border));
}
.empty-line {
  font-size: 13px;
  color: var(--app-muted);
  padding: 4px 0;
}
.muted { color: var(--app-soft); }
@media (max-width: 1100px) {
  .band-row { flex-wrap: wrap; }
  .band-brief { width: 100%; }
  .breach-inline { width: 100%; }
}
</style>
