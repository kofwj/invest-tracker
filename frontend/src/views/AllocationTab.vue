<template>
  <PageShell
    title="结构与目标"
    subtitle="左栏看当前结构，右栏看纪律目标与建议。改参数只提醒，不自动买卖。"
  >
    <template #actions>
      <el-tag type="info" effect="plain">总资产 {{ formatMoney(dashboard.total_assets) }}</el-tag>
      <el-button size="small" :loading="disciplineLoading" @click="refreshDiscipline">刷新纪律</el-button>
      <el-button size="small" @click="openPolicyDialog">调整参数</el-button>
      <el-button size="small" type="primary" @click="createDraftsFromReport">建议→草稿</el-button>
    </template>

    <div class="ledger-metrics cols-4">
      <MetricCard
        label="权益资产占比"
        :value="`${Number(allocationSummary?.equityRatio || 0).toFixed(1)}%`"
        :sub="`权益金额 ${formatMoney(allocationSummary?.equityAmount || 0)} · 目标 ${fmtPct(targets.equity_pct)}`"
        :color="Number(allocationSummary?.equityRatio || 0) > 55 ? 'var(--app-warn)' : ''"
        main
        :title="`${Number(allocationSummary?.equityRatio || 0).toFixed(1)}%`"
      />
      <MetricCard
        label="固收 + 存款占比"
        :value="`${Number(allocationSummary?.defensiveRatio || 0).toFixed(1)}%`"
        :sub="`防守资产 ${formatMoney(allocationSummary?.defensiveAmount || 0)}`"
        color="var(--app-primary)"
        :title="`${Number(allocationSummary?.defensiveRatio || 0).toFixed(1)}%`"
      />
      <MetricCard
        label="组合预计年化"
        :value="`${Number(portfolioExpectedReturn || 0).toFixed(2)}%`"
        sub="按各资产预计收益加权"
        color="var(--app-warn)"
      />
      <MetricCard
        label="纪律破线"
        :value="String(breachCount)"
        :sub="summaryText || '暂无纪律摘要'"
        :tone="breachCount ? 'warn' : 'ok'"
      />
    </div>

    <el-alert
      :title="topBanner"
      type="info"
      show-icon
      :closable="false"
      style="margin-bottom: 14px;"
    />

    <div class="merge-grid structure-merge">
      <!-- 左：结构 -->
      <section class="merge-pane">
        <div class="merge-pane-title">当前结构</div>

        <el-row :gutter="12" style="margin-bottom: 12px;">
          <el-col :span="12">
            <el-card shadow="never" header="大类资产结构">
              <div id="allocationChart" class="chart-container"></div>
            </el-card>
          </el-col>
          <el-col :span="12">
            <el-card shadow="never" header="细分类别占比">
              <div id="categoryChart" class="chart-container"></div>
            </el-card>
          </el-col>
        </el-row>

        <el-card shadow="never" class="merge-card" header="配置健康检查">
          <div class="allocation-risk-list">
            <div v-for="item in (allocationHealth || [])" :key="item.label" class="allocation-risk-item">
              <div class="allocation-risk-head">
                <span>{{ item.label }}</span>
                <el-tag :type="item.type" effect="light">{{ item.status }}</el-tag>
              </div>
              <div class="risk-text">{{ item.text }}</div>
            </div>
          </div>
        </el-card>

        <el-card shadow="never" class="merge-card" header="资产大类汇总">
          <el-table :data="macroAllocationAnalysis" stripe size="small" class="allocation-table" style="width: 100%">
            <el-table-column prop="group" label="大类" width="80" align="center" header-align="center" />
            <el-table-column label="金额" min-width="110" align="right" header-align="right">
              <template #default="scope"><span class="num-cell">{{ formatMoney(scope.row.amount) }}</span></template>
            </el-table-column>
            <el-table-column label="占比" width="72" align="center" header-align="center">
              <template #default="scope">{{ scope.row.percentage?.toFixed(1) }}%</template>
            </el-table-column>
            <el-table-column label="持仓浮盈" min-width="100" align="right" header-align="right">
              <template #default="scope">
                <span class="num-cell" :class="(scope.row.profit >= 0 ) ? 'num-up' : 'num-down'">
                  {{ formatMoney(scope.row.profit, 2, true) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="预计年化" width="88" align="center" header-align="center">
              <template #default="scope">
                <span class="num-info" style="font-weight:700;">{{ scope.row.expected_return?.toFixed(2) }}%</span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </section>

      <!-- 右：目标与纪律 -->
      <section class="merge-pane">
        <div class="merge-pane-title">目标与纪律</div>

        <div class="target-strip">
          <div class="target-card">
            <div class="d-label">权益</div>
            <div class="d-value">{{ fmtPct(snapshot.equity_pct) }}</div>
            <div class="d-sub">目标 {{ fmtPct(targets.equity_pct) }}</div>
          </div>
          <div class="target-card">
            <div class="d-label">固收</div>
            <div class="d-value">{{ fmtPct(snapshot.fixed_income_pct) }}</div>
            <div class="d-sub">目标 {{ fmtPct(targets.fixed_income_pct) }}</div>
          </div>
          <div class="target-card">
            <div class="d-label">存款</div>
            <div class="d-value">{{ fmtPct(snapshot.deposit_pct) }}</div>
            <div class="d-sub">目标 {{ fmtPct(targets.deposit_pct) }}</div>
          </div>
        </div>

        <el-card shadow="never" class="merge-card" v-loading="disciplineLoading">
          <template #header><span class="section-title">纪律检查</span></template>
          <div class="breach-list">
            <div v-for="(b, i) in breaches" :key="i" class="breach-item" :class="'lv-' + (b.level || 'info')">
              <div class="breach-head">
                <span>{{ b.title }}</span>
                <el-tag size="small" :type="tagType(b.level)">{{ levelLabel(b.level) }}</el-tag>
              </div>
              <div class="breach-text">{{ b.text }}</div>
            </div>
            <el-empty v-if="!breaches.length" description="暂无结果" :image-size="56" />
          </div>
        </el-card>

        <el-card shadow="never" class="merge-card" v-if="planItems.length">
          <template #header>
            <div>
              <div class="section-title">个人计划</div>
              <div class="hint">A500 分批 / 格力软上限等，只提醒不自动下单</div>
            </div>
          </template>
          <div class="breach-list">
            <div v-for="(p, i) in planItems" :key="i" class="breach-item" :class="'lv-' + (p.level || 'info')">
              <div class="breach-head">
                <span>{{ p.title }}</span>
                <el-tag size="small" :type="tagType(p.level)">{{ levelLabel(p.level) }}</el-tag>
              </div>
              <div class="breach-text">{{ p.text }}</div>
              <div v-if="p.target_amount" class="plan-progress" style="margin-top:8px;">
                <el-progress
                  :percentage="Math.min(Number(p.progress_pct || 0), 100)"
                  :stroke-width="10"
                  :status="Number(p.remaining_amount || 0) <= 0 ? 'success' : undefined"
                />
                <div class="hint" style="margin-top:4px;" v-if="p.suggested_next_amount">
                  建议下次约 {{ formatMoney(p.suggested_next_amount) }}
                </div>
              </div>
            </div>
          </div>
        </el-card>

        <el-card shadow="never" class="merge-card">
          <template #header>
            <div>
              <div class="section-title">再平衡建议</div>
              <div class="hint">只读建议；可生成草稿，确认后才入账</div>
            </div>
          </template>
          <el-table :data="actions" stripe size="small" empty-text="暂无建议" v-loading="disciplineLoading">
            <el-table-column label="方向" width="72">
              <template #default="s">{{ s.row.side === 'sell' ? '卖出' : '买入' }}</template>
            </el-table-column>
            <el-table-column prop="name" label="名称" min-width="100" show-overflow-tooltip />
            <el-table-column prop="code" label="代码" width="88" />
            <el-table-column label="金额" width="100" align="right" header-align="right">
              <template #default="s"><span class="num-cell">{{ formatMoney(s.row.amount) }}</span></template>
            </el-table-column>
            <el-table-column prop="reason" label="原因" min-width="140" show-overflow-tooltip />
          </el-table>
        </el-card>
      </section>
    </div>

    <el-card shadow="never" class="merge-card" header="细分类别明细">
      <el-table :data="allocationAnalysis" stripe size="small" class="allocation-table" style="width: 100%">
        <el-table-column prop="category" label="资产类别" width="110" align="center" header-align="center" />
        <el-table-column label="市值/金额" min-width="120" align="right" header-align="right">
          <template #default="scope"><span class="num-cell">{{ formatMoney(scope.row.market_value) }}</span></template>
        </el-table-column>
        <el-table-column label="总资产占比" width="100" align="center" header-align="center">
          <template #default="scope">{{ scope.row.percentage?.toFixed(1) }}%</template>
        </el-table-column>
        <el-table-column label="持仓浮盈" min-width="110" align="right" header-align="right">
          <template #default="scope">
            <span class="num-cell" :class="(scope.row.profit >= 0 ) ? 'num-up' : 'num-down'">
              {{ formatMoney(scope.row.profit, 2, true) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="全周期盈亏" min-width="110" align="right" header-align="right">
          <template #default="scope">
            <span class="num-cell" :class="((scope.row.lifetime_profit || 0) >= 0 ) ? 'num-up' : 'num-down'">
              {{ formatMoney(scope.row.lifetime_profit || 0, 2, true) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="浮盈率" width="90" align="center" header-align="center">
          <template #default="scope">
            <span :class="(scope.row.profit_rate >= 0 ) ? 'num-up' : 'num-down'">
              {{ scope.row.profit_rate >= 0 ? '+' : '' }}{{ scope.row.profit_rate?.toFixed(2) }}%
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="count" label="标的数" width="72" align="center" header-align="center" />
        <el-table-column label="预计年化" width="90" align="center" header-align="center">
          <template #default="scope">
            <span class="num-info" style="font-weight:700;">{{ scope.row.expected_annual_return?.toFixed(1) }}%</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="merge-card">
      <template #header>
        <div class="card-head">
          <div>
            <div class="section-title">纪律草稿</div>
            <div class="hint">可编辑后再确认；买入金额单默认「申购待确认」</div>
          </div>
          <div class="card-actions">
            <el-button size="small" :loading="disciplineDraftLoading" @click="fetchDisciplineDrafts">刷新草稿</el-button>
            <el-button size="small" type="warning" @click="confirmSelectedDrafts">批量确认</el-button>
          </div>
        </div>
      </template>
      <el-table
        :data="disciplineDrafts"
        stripe
        size="small"
        empty-text="暂无草稿"
        v-loading="disciplineDraftLoading"
        @selection-change="onDraftSelectionChange"
      >
        <el-table-column type="selection" width="44" />
        <el-table-column label="方向" width="72">
          <template #default="s">{{ s.row.side === 'sell' ? '卖出' : '买入' }}</template>
        </el-table-column>
        <el-table-column prop="name" label="名称" min-width="100" />
        <el-table-column prop="code" label="代码" width="90" />
        <el-table-column label="金额" width="100" align="right" header-align="right">
          <template #default="s"><span class="num-cell">{{ formatMoney(s.row.amount) }}</span></template>
        </el-table-column>
        <el-table-column label="数量" width="88" align="right" header-align="right">
          <template #default="s">{{ s.row.quantity ? Number(s.row.quantity).toFixed(2) : '—' }}</template>
        </el-table-column>
        <el-table-column prop="reason" label="原因" min-width="140" show-overflow-tooltip />
        <el-table-column prop="created_at" label="创建" width="140" />
        <el-table-column label="操作" width="200" align="center">
          <template #default="s">
            <el-button type="primary" link @click="openDraftEdit(s.row)">编辑</el-button>
            <el-button type="primary" link @click="confirmDraft(s.row)">确认入账</el-button>
            <el-button type="danger" link @click="deleteDraft(s.row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="disciplinePolicyDialog" title="纪律 / 目标参数" width="560px" destroy-on-close>
      <el-alert
        title="改参数只影响提醒和建议，不会自动买卖。权益/固收/存款三项目标合计应约 100%。"
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 12px;"
      />
      <el-form label-width="130px" v-if="disciplinePolicy">
        <el-form-item label="权益下限%">
          <el-input-number v-model="disciplinePolicy.equity_min_pct" :min="0" :max="100" :step="1" />
        </el-form-item>
        <el-form-item label="权益上限%">
          <el-input-number v-model="disciplinePolicy.equity_max_pct" :min="0" :max="100" :step="1" />
        </el-form-item>
        <el-form-item label="防守下限%">
          <el-input-number v-model="disciplinePolicy.defensive_min_pct" :min="0" :max="100" :step="1" />
        </el-form-item>
        <el-form-item label="单票上限%">
          <el-input-number v-model="disciplinePolicy.single_holding_max_pct" :min="1" :max="100" :step="1" />
        </el-form-item>
        <el-form-item label="目标权益%">
          <el-input-number v-model="disciplinePolicy.targets.equity_pct" :min="0" :max="100" :step="1" />
        </el-form-item>
        <el-form-item label="目标固收%">
          <el-input-number v-model="disciplinePolicy.targets.fixed_income_pct" :min="0" :max="100" :step="1" />
        </el-form-item>
        <el-form-item label="目标存款%">
          <el-input-number v-model="disciplinePolicy.targets.deposit_pct" :min="0" :max="100" :step="1" />
        </el-form-item>
        <el-form-item label="再平衡带宽%">
          <el-input-number v-model="disciplinePolicy.rebalance_band_pct" :min="0" :max="20" :step="0.5" />
        </el-form-item>
        <el-form-item label="优先加仓代码">
          <el-input v-model="disciplinePolicy.preferred_buy_code" />
        </el-form-item>
        <el-form-item label="优先加仓名称">
          <el-input v-model="disciplinePolicy.preferred_buy_name" />
        </el-form-item>
        <el-form-item label="格力上限%">
          <el-input-number v-model="greeLimitPct" :min="1" :max="100" :step="1" />
        </el-form-item>
        <el-form-item label="A500计划金额">
          <el-input-number
            v-model="disciplinePolicy.plans.a500_batch_target_amount"
            :min="0"
            :step="10000"
            :controls="true"
          />
        </el-form-item>
        <el-form-item label="格力软上限%">
          <el-input-number v-model="disciplinePolicy.plans.gree_soft_max_pct" :min="0" :max="100" :step="1" />
        </el-form-item>
        <el-form-item label="防守额外品类">
          <el-select
            v-model="disciplinePolicy.defensive_extra_categories"
            multiple
            filterable
            allow-create
            default-first-option
            placeholder="如 黄金 / REITs（可选）"
            style="width: 100%"
          >
            <el-option label="黄金" value="黄金" />
            <el-option label="REITs" value="REITs" />
            <el-option label="港股ETF" value="港股ETF" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="disciplinePolicyDialog = false">取消</el-button>
        <el-button type="primary" @click="savePolicy">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="disciplineDraftEditDialog" title="编辑纪律草稿" width="440px" destroy-on-close>
      <el-form label-width="90px" v-if="disciplineDraftEditForm">
        <el-form-item label="标的">
          <span>{{ disciplineDraftEditForm.name }}（{{ disciplineDraftEditForm.code }}）</span>
        </el-form-item>
        <el-form-item label="方向">
          <span>{{ disciplineDraftEditForm.side === 'sell' ? '卖出' : '买入' }}</span>
        </el-form-item>
        <el-form-item label="数量">
          <el-input-number v-model="disciplineDraftEditForm.quantity" :min="0" :step="1" :precision="4" style="width:100%" />
        </el-form-item>
        <el-form-item label="价格">
          <el-input-number v-model="disciplineDraftEditForm.price" :min="0" :step="0.01" :precision="4" style="width:100%" />
        </el-form-item>
        <el-form-item label="金额">
          <el-input-number v-model="disciplineDraftEditForm.amount" :min="0.01" :step="100" :precision="2" style="width:100%" />
        </el-form-item>
        <el-form-item label="账户">
          <el-input v-model="disciplineDraftEditForm.account" />
        </el-form-item>
        <el-form-item label="原因">
          <el-input v-model="disciplineDraftEditForm.reason" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="disciplineDraftEditDialog = false">取消</el-button>
        <el-button type="primary" @click="saveDraftEdit">保存</el-button>
      </template>
    </el-dialog>
  </PageShell>
</template>

<script setup>
import PageShell from '../components/PageShell.vue';
import MetricCard from '../components/MetricCard.vue';
import { computed, onMounted, watch, nextTick } from 'vue';
import { useAppCtx } from '../composables/useAppCtx.js';

const {
  dashboard,
  allocationAnalysis,
  macroAllocationAnalysis,
  allocationSummary,
  allocationHealth,
  portfolioExpectedReturn,
  formatMoney,
  disciplineDrafts,
  disciplinePolicy,
  disciplineLoading,
  disciplineDraftLoading,
  disciplinePolicyDialog,
  disciplineDraftEditDialog,
  disciplineDraftEditForm,
  refreshDiscipline,
  openPolicyDialog,
  savePolicy,
  createDraftsFromReport,
  openDraftEdit,
  saveDraftEdit,
  deleteDraft,
  confirmDraft,
  confirmSelectedDrafts,
  onDraftSelectionChange,
  fetchDisciplineDrafts,
  breaches,
  actions,
  planItems,
  snapshot,
  targets,
  summaryText,
  resolvedTheme,
} = useAppCtx();

if (disciplinePolicy.value && !disciplinePolicy.value.targets) {
  disciplinePolicy.value.targets = { equity_pct: 45, fixed_income_pct: 30, deposit_pct: 25 };
}
if (disciplinePolicy.value && !disciplinePolicy.value.plans) {
  disciplinePolicy.value.plans = { a500_batch_target_amount: 200000, gree_soft_max_pct: 15 };
}
if (disciplinePolicy.value && !Array.isArray(disciplinePolicy.value.defensive_extra_categories)) {
  disciplinePolicy.value.defensive_extra_categories = [];
}
if (disciplinePolicy.value && !Array.isArray(disciplinePolicy.value.named_limits)) {
  disciplinePolicy.value.named_limits = [{ code: '000651', name: '格力电器', max_pct: 15 }];
}

const greeLimitPct = computed({
  get() {
    const limits = disciplinePolicy.value?.named_limits || [];
    const g = limits.find((x) => String(x.code) === '000651');
    return g?.max_pct ?? 15;
  },
  set(v) {
    const n = Number(v);
    if (!disciplinePolicy.value) return;
    const limits = Array.isArray(disciplinePolicy.value.named_limits)
      ? [...disciplinePolicy.value.named_limits]
      : [];
    const idx = limits.findIndex((x) => String(x.code) === '000651');
    if (idx >= 0) limits[idx] = { ...limits[idx], max_pct: n };
    else limits.push({ code: '000651', name: '格力电器', max_pct: n });
    disciplinePolicy.value.named_limits = limits;
    if (!disciplinePolicy.value.plans) disciplinePolicy.value.plans = {};
    disciplinePolicy.value.plans.gree_soft_max_pct = n;
  },
});

const breachCount = computed(() => {
  const list = breaches?.value ?? breaches ?? [];
  return Array.isArray(list) ? list.length : 0;
});

const topBanner = computed(() => {
  const a = allocationSummary?.value?.comment || allocationSummary?.comment || '';
  const d = summaryText?.value || summaryText || '';
  if (a && d) return `${a} · ${d}`;
  return a || d || '加载结构与纪律…';
});

const fmtPct = (v) => {
  if (v === null || v === undefined || v === '') return '—';
  const n = Number(v);
  if (Number.isNaN(n)) return '—';
  return `${n.toFixed(1)}%`;
};

const tagType = (lv) => {
  if (lv === 'warning') return 'warning';
  if (lv === 'ok') return 'success';
  return 'info';
};

const levelLabel = (lv) => {
  if (lv === 'warning') return '提醒';
  if (lv === 'ok') return '正常';
  return '说明';
};

const paintCharts = async () => {
  const { renderAllocationChartsView, waitForChartDom } = await import('../charts/index.js');
  const ready = await waitForChartDom(['allocationChart', 'categoryChart']);
  if (!ready) return;
  await nextTick();
  renderAllocationChartsView(macroAllocationAnalysis.value, allocationAnalysis.value);
};

onMounted(() => {
  paintCharts();
  if (typeof refreshDiscipline === 'function') refreshDiscipline();
  if (typeof fetchDisciplineDrafts === 'function') fetchDisciplineDrafts();
});

watch(
  [macroAllocationAnalysis, allocationAnalysis],
  () => {
    paintCharts();
  },
  { deep: true },
);

// 切日/夜主题后重画，否则 ECharts 标题图例仍是旧色
watch(
  () => resolvedTheme?.value ?? resolvedTheme,
  () => {
    paintCharts();
  },
);
</script>

<style scoped>
.merge-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(280px, 0.95fr);
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
  color: var(--app-text);
}
.merge-pane-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--app-muted);
  margin-bottom: 10px;
}
.merge-card { margin-bottom: 12px; }
.section-title { font-size: 15px; font-weight: 700; color: var(--app-text); }
.hint { font-size: 12px; color: var(--app-soft); margin-top: 2px; }
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
  flex-wrap: wrap;
}
.card-actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.allocation-risk-list { display: grid; gap: 10px; }
.allocation-risk-item {
  padding: 10px 12px;
  border: 1px solid var(--app-border);
  border-radius: 10px;
  background: color-mix(in srgb, var(--app-surface) 88%, var(--app-bg0));
  color: var(--app-text);
}
.allocation-risk-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
  margin-bottom: 4px;
  color: var(--app-text);
}
.risk-text { font-size: 12px; color: var(--app-muted); line-height: 1.5; }
.target-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 12px;
}
.target-card {
  border: 1px solid var(--app-border);
  border-radius: 10px;
  padding: 10px 12px;
  background: color-mix(in srgb, var(--app-surface) 88%, var(--app-bg0));
  color: var(--app-text);
}
.d-label { font-size: 12px; color: var(--app-muted); }
.d-value { font-size: 20px; font-weight: 700; margin: 4px 0 2px; color: var(--app-text); }
.d-sub { font-size: 12px; color: var(--app-soft); }
.breach-list { display: grid; gap: 10px; }
.breach-item {
  padding: 12px;
  border-radius: 10px;
  border: 1px solid var(--app-border);
  background: color-mix(in srgb, var(--app-surface) 88%, var(--app-bg0));
  color: var(--app-text);
}
.breach-item.lv-warning {
  border-color: color-mix(in srgb, var(--app-warn) 35%, var(--app-border));
  background: var(--app-warn-soft);
}
.breach-item.lv-ok {
  border-color: color-mix(in srgb, var(--app-ok) 30%, var(--app-border));
  background: var(--app-ok-soft);
}
.breach-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
  margin-bottom: 6px;
  color: var(--app-text);
}
.breach-text { font-size: 12px; color: var(--app-muted); line-height: 1.5; }
/* 给底部图例留位，避免挤在扇区上 */
.chart-container { height: 260px; min-height: 220px; width: 100%; }
@media (max-width: 960px) {
  .merge-grid { grid-template-columns: 1fr; }
  .target-strip { grid-template-columns: 1fr; }
}
</style>
