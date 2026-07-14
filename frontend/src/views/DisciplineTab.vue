<template>
  <div class="discipline-page">
    <div class="discipline-header">
      <div>
        <h3 class="discipline-title">纪律与再平衡</h3>
        <div class="discipline-sub">
          基于真实持仓做纪律检查 + 目标比例建议。默认不改账；草稿确认后才写入真实交易。
        </div>
      </div>
      <div class="discipline-actions">
        <el-button size="small" :loading="disciplineLoading" @click="refreshDiscipline">刷新</el-button>
        <el-button size="small" @click="openPolicyDialog">调整参数</el-button>
        <el-button size="small" type="primary" @click="createDraftsFromReport">建议→草稿</el-button>
      </div>
    </div>

    <el-alert
      :title="summaryText || '加载后显示纪律结论'"
      type="info"
      show-icon
      :closable="false"
      style="margin-bottom: 14px;"
    />

    <el-card v-if="helpNotes.length" shadow="never" style="margin-bottom: 16px;">
      <template #header><span class="section-title">怎么用</span></template>
      <ul class="help-list">
        <li v-for="(line, i) in helpNotes" :key="i">{{ line }}</li>
      </ul>
    </el-card>

    <el-row :gutter="12" style="margin-bottom: 16px;">
      <el-col :xs="12" :sm="8" :md="6">
        <el-card shadow="hover" class="d-metric">
          <div class="d-label">权益占比</div>
          <div class="d-value">{{ fmtPct(snapshot.equity_pct) }}</div>
          <div class="d-sub">目标 {{ fmtPct(targets.equity_pct) }}</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="6">
        <el-card shadow="hover" class="d-metric">
          <div class="d-label">固收占比</div>
          <div class="d-value">{{ fmtPct(snapshot.fixed_income_pct) }}</div>
          <div class="d-sub">目标 {{ fmtPct(targets.fixed_income_pct) }}</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="6">
        <el-card shadow="hover" class="d-metric">
          <div class="d-label">存款占比</div>
          <div class="d-value">{{ fmtPct(snapshot.deposit_pct) }}</div>
          <div class="d-sub">目标 {{ fmtPct(targets.deposit_pct) }}</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="6">
        <el-card shadow="hover" class="d-metric">
          <div class="d-label">总资产</div>
          <div class="d-value" style="font-size:18px;">{{ formatMoney(snapshot.total_assets || 0) }}</div>
          <div class="d-sub">证券现金 {{ formatMoney(snapshot.securities_cash || 0) }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" style="margin-bottom: 16px;" v-loading="disciplineLoading">
      <template #header>
        <span class="section-title">纪律检查</span>
      </template>
      <div class="breach-list">
        <div v-for="(b, i) in breaches" :key="i" class="breach-item" :class="'lv-' + (b.level || 'info')">
          <div class="breach-head">
            <span>{{ b.title }}</span>
            <el-tag size="small" :type="tagType(b.level)">{{ levelLabel(b.level) }}</el-tag>
          </div>
          <div class="breach-text">{{ b.text }}</div>
        </div>
        <el-empty v-if="!breaches.length" description="暂无结果" :image-size="60" />
      </div>
    </el-card>

    <el-card shadow="never" style="margin-bottom: 16px;" v-if="planItems.length">
      <template #header>
        <div>
          <div class="section-title">个人计划</div>
          <div class="hint">A500 分批 / 格力软上限等，只提醒不自动下单；可在参数里改目标金额。</div>
        </div>
      </template>
      <div class="breach-list">
        <div v-for="(p, i) in planItems" :key="i" class="breach-item" :class="'lv-' + (p.level || 'info')">
          <div class="breach-head">
            <span>{{ p.title }}</span>
            <el-tag size="small" :type="tagType(p.level)">{{ levelLabel(p.level) }}</el-tag>
          </div>
          <div class="breach-text">{{ p.text }}</div>
        </div>
      </div>
    </el-card>

    <el-card shadow="never" style="margin-bottom: 16px;">
      <template #header>
        <div>
          <div class="section-title">再平衡建议</div>
          <div class="hint">只读建议；可生成草稿，确认后才入账。券商下单仍需你自己操作。</div>
        </div>
      </template>
      <el-table :data="actions" stripe empty-text="暂无建议" v-loading="disciplineLoading">
        <el-table-column label="方向" width="80">
          <template #default="s">{{ s.row.side === 'sell' ? '卖出' : '买入' }}</template>
        </el-table-column>
        <el-table-column prop="name" label="名称" min-width="120" show-overflow-tooltip />
        <el-table-column prop="code" label="代码" width="100" />
        <el-table-column label="金额" width="120" align="right" header-align="right">
          <template #default="s">{{ formatMoney(s.row.amount) }}</template>
        </el-table-column>
        <el-table-column label="数量" width="100" align="right" header-align="right">
          <template #default="s">{{ s.row.quantity ? Number(s.row.quantity).toFixed(2) : '—' }}</template>
        </el-table-column>
        <el-table-column prop="reason" label="原因" min-width="220" show-overflow-tooltip />
      </el-table>
    </el-card>

    <el-card shadow="never" style="margin-bottom: 16px;">
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;">
          <div>
            <div class="section-title">纪律草稿</div>
            <div class="hint">可编辑数量/金额后再确认；买入金额单默认记为「申购待确认」。</div>
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;">
            <el-button size="small" :loading="disciplineDraftLoading" @click="fetchDisciplineDrafts">刷新草稿</el-button>
            <el-button size="small" type="warning" @click="confirmSelectedDrafts">批量确认</el-button>
          </div>
        </div>
      </template>
      <el-table
        :data="disciplineDrafts"
        stripe
        empty-text="暂无草稿"
        v-loading="disciplineDraftLoading"
        @selection-change="onDraftSelectionChange"
      >
        <el-table-column type="selection" width="48" />
        <el-table-column label="方向" width="80">
          <template #default="s">{{ s.row.side === 'sell' ? '卖出' : '买入' }}</template>
        </el-table-column>
        <el-table-column prop="name" label="名称" min-width="110" />
        <el-table-column prop="code" label="代码" width="100" />
        <el-table-column label="金额" width="110" align="right" header-align="right">
          <template #default="s">{{ formatMoney(s.row.amount) }}</template>
        </el-table-column>
        <el-table-column label="数量" width="90" align="right" header-align="right">
          <template #default="s">{{ s.row.quantity ? Number(s.row.quantity).toFixed(2) : '—' }}</template>
        </el-table-column>
        <el-table-column prop="reason" label="原因" min-width="160" show-overflow-tooltip />
        <el-table-column prop="created_at" label="创建" width="150" />
        <el-table-column label="操作" width="210" align="center">
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
  </div>
</template>

<script setup>
import { computed } from 'vue';
import { useAppCtx } from '../composables/useAppCtx.js';

const {
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
  helpNotes,
  snapshot,
  targets,
  summaryText,
  formatMoney,
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
</script>

<style scoped>
.discipline-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}
.discipline-title { margin: 0 0 4px; font-size: 18px; }
.discipline-sub { font-size: 12px; color: #909399; }
.discipline-actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.section-title { font-size: 16px; font-weight: 700; color: #303133; }
.hint { font-size: 12px; color: #909399; margin-top: 4px; }
.help-list { margin: 0; padding-left: 18px; color: #606266; font-size: 13px; line-height: 1.7; }
.d-metric { margin-bottom: 8px; }
.d-label { font-size: 12px; color: #909399; }
.d-value { font-size: 22px; font-weight: 700; margin: 6px 0 4px; }
.d-sub { font-size: 12px; color: #a8abb2; }
.breach-list { display: grid; gap: 10px; }
.breach-item {
  padding: 12px;
  border-radius: 10px;
  border: 1px solid #ebeef5;
  background: #f8fafc;
}
.breach-item.lv-warning { border-color: #f5dab1; background: #fdf6ec; }
.breach-item.lv-ok { border-color: #e1f3d8; background: #f0f9eb; }
.breach-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
  margin-bottom: 6px;
}
.breach-text { font-size: 12px; color: #606266; line-height: 1.5; }
</style>
