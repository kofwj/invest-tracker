<template>
  <PageShell
    title="结构与目标"
    subtitle="左栏结构诊断，右栏改目标尺子与纪律。改参数只提醒，不自动买卖。"
  >
    <template #actions>
      <el-tag type="info" effect="plain">总资产 {{ formatMoney(dashboard.total_assets) }}</el-tag>
      <el-button size="small" :loading="allocationStoryLoading || disciplineLoading" @click="refreshAll">刷新诊断</el-button>
      <el-button size="small" @click="openPolicyDialog">调整参数</el-button>
      <el-button size="small" type="primary" @click="createDraftsFromReport">建议→草稿</el-button>
    </template>

    <div class="ledger-metrics cols-4">
      <MetricCard
        label="权益资产占比"
        :value="`${Number(displayEquityPct).toFixed(1)}%`"
        :sub="`权益金额 ${formatMoney(displayEquityAmount)} · 目标 ${fmtPct(targets.equity_pct)}`"
        :tone="equityTone"
        main
        :title="`${Number(displayEquityPct).toFixed(1)}%`"
      />
      <MetricCard
        label="防守占比"
        :value="`${Number(displayDefensivePct).toFixed(1)}%`"
        :sub="`固收+存款等 ${formatMoney(displayDefensiveAmount)}`"
        color="var(--app-primary)"
        :title="`${Number(displayDefensivePct).toFixed(1)}%`"
      />
      <MetricCard
        label="组合预计年化"
        :value="`${Number(portfolioExpectedReturn || 0).toFixed(2)}%`"
        sub="按各资产预计收益加权"
        color="var(--app-warn)"
      />
      <MetricCard
        label="需关注问题"
        :value="String(issueWarnCount)"
        :sub="story?.discipline_summary || summaryText || '暂无纪律摘要'"
        :tone="issueWarnCount ? 'warn' : 'ok'"
      />
    </div>

    <el-card shadow="never" class="story-hero merge-card" v-loading="allocationStoryLoading">
      <div class="story-hero-head">
        <div>
          <div class="story-kicker">配置结论</div>
          <div class="story-headline">{{ storyHeadline }}</div>
        </div>
        <el-tag :type="severityTagType" effect="light">{{ severityLabel }}</el-tag>
      </div>
      <ul v-if="storyBullets.length" class="story-bullets">
        <li v-for="(b, i) in storyBullets" :key="i">{{ b }}</li>
      </ul>
    </el-card>

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
            <el-empty v-if="!(allocationHealth || []).length" description="诊断加载中或暂无数据" :image-size="48" />
          </div>
        </el-card>

        <el-card shadow="never" class="merge-card" header="问题清单" v-if="storyIssues.length">
          <div class="issue-list">
            <div v-for="(iss, i) in storyIssues" :key="iss.id + '-' + i" class="issue-item" :class="'lv-' + (iss.level || 'info')">
              <div class="issue-head">
                <span>{{ iss.title }}</span>
                <el-tag size="small" :type="tagType(iss.level)">{{ levelLabel(iss.level) }}</el-tag>
              </div>
              <div class="issue-text">{{ iss.text }}</div>
              <div v-if="iss.action_hint" class="hint">{{ iss.action_hint }}</div>
            </div>
          </div>
        </el-card>

        <div class="diag-grid" v-if="homoGroups.length || story?.profit_dependency || story?.liquidity">
          <el-card shadow="never" class="merge-card diag-card" header="同质化粗分" v-if="homoGroups.length">
            <div class="hint" style="margin-bottom:8px;">{{ story?.homogeneity?.note || '名称/品类关键词粗分，不是官方行业' }}</div>
            <div class="homo-list">
              <div v-for="g in homoGroups" :key="g.tag" class="homo-item">
                <div class="homo-head">
                  <span>{{ g.tag }}</span>
                  <el-tag size="small" :type="tagType(g.level)" effect="plain">
                    占总 {{ Number(g.pct_of_total || 0).toFixed(1) }}%
                  </el-tag>
                </div>
                <div class="hint">{{ (g.names || []).join('、') }}</div>
              </div>
            </div>
          </el-card>

          <el-card shadow="never" class="merge-card diag-card" header="收益依赖">
            <div class="risk-text">{{ story?.profit_dependency?.text || '加载中…' }}</div>
          </el-card>

          <el-card shadow="never" class="merge-card diag-card" header="流动性（30 天）">
            <div class="risk-text">{{ story?.liquidity?.text || '加载中…' }}</div>
            <div class="liq-metrics" v-if="story?.liquidity">
              <span>证券现金 {{ formatMoney(story.liquidity.securities_cash) }}</span>
              <span>近端存款 {{ formatMoney(story.liquidity.deposit_due_30d_amount) }}</span>
              <span>可挪约 {{ formatMoney(story.liquidity.deployable_30d) }}</span>
            </div>
          </el-card>
        </div>

        <el-card shadow="never" class="merge-card">
          <template #header>
            <div>
              <div class="section-title">权益情景粗估</div>
              <div class="hint">假设粗估，不是预测：只动权益市值，固收/存款/现金不变</div>
            </div>
          </template>
          <el-table :data="storyScenarios" size="small" stripe empty-text="暂无">
            <el-table-column prop="label" label="情景" min-width="120" />
            <el-table-column label="粗估盈亏" min-width="110" align="right" header-align="right">
              <template #default="s">
                <span class="num-cell" :class="Number(s.row.estimated_pnl) >= 0 ? 'num-up' : 'num-down'">
                  {{ formatMoney(s.row.estimated_pnl, 0, true) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="粗估总资产" min-width="120" align="right" header-align="right">
              <template #default="s">
                <span class="num-cell">{{ formatMoney(s.row.estimated_total_assets) }}</span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <el-card shadow="never" class="merge-card" header="资产大类汇总">
          <el-table :data="macroAllocationAnalysis" stripe size="small" class="allocation-table" style="width: 100%">
            <el-table-column prop="group" label="大类" width="80" align="center" header-align="center" />
            <el-table-column label="金额" min-width="110" align="right" header-align="right">
              <template #default="scope"><span class="num-cell">{{ formatMoney(scope.row.amount) }}</span></template>
            </el-table-column>
            <el-table-column label="占比" width="88" align="center" header-align="center">
              <template #default="scope">{{ Number(scope.row.percentage || 0).toFixed(1) }}%</template>
            </el-table-column>
            <el-table-column label="持仓浮盈" min-width="100" align="right" header-align="right">
              <template #default="scope">
                <span class="num-cell" :class="(scope.row.profit >= 0) ? 'num-up' : 'num-down'">
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

        <el-card shadow="never" class="merge-card target-panel" v-loading="disciplinePresetLoading">
          <div class="preset-row">
            <div class="preset-row-label">目标尺子</div>
            <div class="preset-seg" role="group" aria-label="目标尺子">
              <button
                v-for="p in (disciplinePresets || [])"
                :key="p.id"
                type="button"
                class="preset-seg-btn"
                :class="{ active: p.id === disciplinePresetActiveId || p.active }"
                :disabled="disciplinePresetLoading || p.id === disciplinePresetActiveId || p.active"
                :title="presetTitle(p)"
                @click="applyDisciplinePreset(p.id)"
              >{{ p.label }}</button>
            </div>
          </div>
          <div class="preset-meta">
            <span class="preset-meta-main">当前 · {{ activePresetLabel }}</span>
            <span class="preset-meta-sub">{{ activePresetHint }}</span>
          </div>
          <div class="hint preset-guard">只改目标与安全带；优先加仓 / 禁开 / 格力上限不动</div>

          <div class="gap-list" style="margin-top: 12px;">
            <div v-for="row in gapRows" :key="row.key" class="gap-row">
              <div class="gap-row-head">
                <span class="gap-label">{{ row.label }}</span>
                <span class="gap-nums">
                  <b class="gap-actual">{{ fmtPct(row.actual) }}</b>
                  <span class="gap-arrow">→</span>
                  目标 {{ fmtPct(row.target) }}
                  <template v-if="row.gapAmt">
                    · {{ formatMoney(Math.abs(row.gapAmt), 0) }}{{ row.gapAmt > 0 ? '偏少' : '偏多' }}
                  </template>
                </span>
              </div>
              <el-progress
                :percentage="Math.min(Math.max(Number(row.actual || 0), 0), 100)"
                :stroke-width="8"
                :color="row.barColor"
              />
            </div>
            <div class="hint">带宽 ±{{ fmtPct(bandPct) }}；超出才出再平衡建议</div>
          </div>
        </el-card>

        <el-card shadow="never" class="merge-card" v-loading="disciplineLoading">
          <template #header><span class="section-title">纪律检查</span></template>
          <div class="breach-list">
            <div v-for="(b, i) in visibleBreaches" :key="i" class="breach-item" :class="'lv-' + (b.level || 'info')">
              <div class="breach-head">
                <span>{{ b.title }}</span>
                <el-tag size="small" :type="tagType(b.level)">{{ levelLabel(b.level) }}</el-tag>
              </div>
              <div class="breach-text">{{ b.text }}</div>
            </div>
            <el-empty v-if="!visibleBreaches.length" description="暂无非正常提醒" :image-size="56" />
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
        <el-button @click="cancelPolicy">取消</el-button>
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
  allocationStory,
  allocationStoryLoading,
  fetchAllocationStory,
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
  cancelPolicy,
  savePolicy,
  createDraftsFromReport,
  openDraftEdit,
  saveDraftEdit,
  deleteDraft,
  confirmDraft,
  confirmSelectedDrafts,
  onDraftSelectionChange,
  fetchDisciplineDrafts,
  disciplinePresets,
  disciplinePresetActiveId,
  disciplinePresetLoading,
  applyDisciplinePreset,
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

const story = computed(() => allocationStory?.value ?? allocationStory ?? null);

const storyHeadline = computed(() => {
  const h = story.value?.headline;
  if (h) return h;
  return allocationSummary?.value?.comment || summaryText?.value || '加载结构与纪律…';
});

const storyBullets = computed(() => {
  const b = story.value?.bullets;
  return Array.isArray(b) ? b : [];
});

const storyIssues = computed(() => {
  const list = story.value?.issues;
  return Array.isArray(list) ? list : [];
});

const issueWarnCount = computed(() => storyIssues.value.filter((x) => x.level === 'warning').length);

const severityLabel = computed(() => {
  const s = story.value?.severity || 'ok';
  if (s === 'warning') return '需关注';
  if (s === 'info') return '有提示';
  return '大致合适';
});

const severityTagType = computed(() => {
  const s = story.value?.severity || 'ok';
  if (s === 'warning') return 'warning';
  if (s === 'info') return 'info';
  return 'success';
});

const equityTone = computed(() => {
  const list = allocationHealth?.value ?? allocationHealth ?? [];
  const arr = Array.isArray(list) ? list : [];
  const item = arr.find((x) => x.code === 'equity_band' || x.label === '权益波动暴露');
  if (item?.level === 'warning' || item?.status === '偏高') return 'warn';
  if (item?.status === '偏低') return 'info';
  return '';
});

const displayEquityPct = computed(() => {
  const s = story.value?.snapshot;
  if (s && s.equity_pct != null) return Number(s.equity_pct);
  return Number(allocationSummary?.value?.equityRatio || 0);
});
const displayEquityAmount = computed(() => {
  const s = story.value?.snapshot;
  if (s && s.equity_mv != null) return Number(s.equity_mv);
  return Number(allocationSummary?.value?.equityAmount || 0);
});
const displayDefensivePct = computed(() => {
  const s = story.value?.snapshot;
  if (s && s.defensive_pct != null) return Number(s.defensive_pct);
  return Number(allocationSummary?.value?.defensiveRatio || 0);
});
const displayDefensiveAmount = computed(() => {
  const s = story.value?.snapshot;
  if (s) return Number(s.fixed_mv || 0) + Number(s.deposit_mv || 0);
  return Number(allocationSummary?.value?.defensiveAmount || 0);
});

const bandPct = computed(() => Number(targets?.value?.band_pct ?? story.value?.policy?.rebalance_band_pct ?? 3));

const gapRows = computed(() => {
  const snap = snapshot?.value ?? snapshot ?? {};
  const t = targets?.value ?? targets ?? {};
  const gaps = story.value?.gaps || {};
  const rows = [
    { key: 'equity', label: '权益', actual: snap.equity_pct, target: t.equity_pct, gapAmt: gaps.equity_amount || 0 },
    { key: 'fi', label: '固收', actual: snap.fixed_income_pct, target: t.fixed_income_pct, gapAmt: gaps.fixed_income_amount || 0 },
    { key: 'dep', label: '存款', actual: snap.deposit_pct, target: t.deposit_pct, gapAmt: gaps.deposit_amount || 0 },
  ];
  return rows.map((r) => {
    const actual = Number(r.actual || 0);
    const target = Number(r.target || 0);
    const diff = Math.abs(actual - target);
    let barColor = 'var(--app-primary)';
    if (diff > bandPct.value) barColor = 'var(--app-warn)';
    return { ...r, actual, target, barColor };
  });
});

const visibleBreaches = computed(() => {
  const list = breaches?.value ?? breaches ?? [];
  if (!Array.isArray(list)) return [];
  return list.filter((b) => b.level !== 'ok');
});

const homoGroups = computed(() => story.value?.homogeneity?.groups || []);
const storyScenarios = computed(() => story.value?.scenarios || []);

const activePresetLabel = computed(() => {
  const id = disciplinePresetActiveId?.value ?? disciplinePresetActiveId;
  const list = disciplinePresets?.value ?? disciplinePresets ?? [];
  const arr = Array.isArray(list) ? list : [];
  const hit = arr.find((p) => p.id === id || p.active);
  if (hit) return hit.label;
  return id ? String(id) : '自定义';
});

const activePresetHint = computed(() => {
  const list = disciplinePresets?.value ?? disciplinePresets ?? [];
  const arr = Array.isArray(list) ? list : [];
  const id = disciplinePresetActiveId?.value ?? disciplinePresetActiveId;
  const hit = arr.find((p) => p.id === id || p.active);
  if (hit) {
    const t = hit.targets || {};
    return `权益 ${Number(t.equity_pct || 0).toFixed(0)} · 固收 ${Number(t.fixed_income_pct || 0).toFixed(0)} · 存款 ${Number(t.deposit_pct || 0).toFixed(0)}`;
  }
  const t = targets?.value ?? targets ?? {};
  if (t.equity_pct != null) {
    return `权益 ${Number(t.equity_pct || 0).toFixed(0)} · 固收 ${Number(t.fixed_income_pct || 0).toFixed(0)} · 存款 ${Number(t.deposit_pct || 0).toFixed(0)}（手调）`;
  }
  return '手调参数，未匹配三套预设';
});

const presetTitle = (p) => {
  if (!p) return '';
  const t = p.targets || {};
  const ratio = `权益 ${Number(t.equity_pct || 0).toFixed(0)}% / 固收 ${Number(t.fixed_income_pct || 0).toFixed(0)}% / 存款 ${Number(t.deposit_pct || 0).toFixed(0)}%`;
  return [p.summary, ratio, p.detail].filter(Boolean).join(' · ');
};

const refreshAll = async () => {
  const tasks = [];
  if (typeof refreshDiscipline === 'function') tasks.push(refreshDiscipline());
  if (typeof fetchAllocationStory === 'function') tasks.push(fetchAllocationStory());
  if (typeof fetchDisciplineDrafts === 'function') tasks.push(fetchDisciplineDrafts());
  await Promise.all(tasks);
};

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
  refreshAll();
});

watch(
  [macroAllocationAnalysis, allocationAnalysis],
  () => {
    paintCharts();
  },
  { deep: true },
);

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
}
.card-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.story-hero {
  margin-bottom: 14px;
  border: 1px solid var(--app-border);
  background:
    linear-gradient(135deg, color-mix(in srgb, var(--app-primary) 12%, transparent), transparent 55%),
    var(--app-surface);
}
.story-hero-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 8px;
}
.story-kicker {
  font-size: 12px;
  font-weight: 600;
  color: var(--app-muted);
  margin-bottom: 4px;
}
.story-headline {
  font-size: 18px;
  font-weight: 750;
  line-height: 1.45;
  color: var(--app-text);
}
.story-bullets {
  margin: 0;
  padding-left: 18px;
  color: var(--app-muted);
  font-size: 13px;
  line-height: 1.6;
}
.target-panel {
  border: 1px solid var(--app-border);
}
.preset-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}
.preset-row-label {
  font-size: 13px;
  font-weight: 700;
  color: var(--app-text);
  flex: 0 0 auto;
}
.preset-seg {
  display: inline-flex;
  padding: 3px;
  border-radius: 10px;
  background: color-mix(in srgb, var(--app-bg0) 70%, var(--app-surface));
  border: 1px solid var(--app-border);
  gap: 2px;
  flex: 1 1 auto;
  min-width: 0;
  max-width: 100%;
}
.preset-seg-btn {
  flex: 1 1 0;
  min-width: 0;
  border: 0;
  background: transparent;
  color: var(--app-muted);
  font-size: 13px;
  font-weight: 600;
  line-height: 1.2;
  padding: 7px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: background .15s ease, color .15s ease;
}
.preset-seg-btn:hover:not(:disabled) {
  color: var(--app-text);
  background: color-mix(in srgb, var(--app-surface) 80%, transparent);
}
.preset-seg-btn.active {
  color: var(--app-text);
  background: var(--app-surface);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--app-primary) 35%, var(--app-border));
  font-weight: 750;
}
.preset-seg-btn:disabled:not(.active) {
  opacity: .55;
  cursor: not-allowed;
}
.preset-seg-btn.active:disabled {
  cursor: default;
  opacity: 1;
}
.preset-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 8px 12px;
  margin-top: 10px;
}
.preset-meta-main {
  font-size: 13px;
  font-weight: 650;
  color: var(--app-text);
}
.preset-meta-sub {
  font-size: 12px;
  color: var(--app-muted);
  font-variant-numeric: tabular-nums;
}
.preset-guard { margin-top: 6px; }
.gap-label { min-width: 2.5em; }
.gap-actual {
  font-variant-numeric: tabular-nums;
  color: var(--app-text);
  font-weight: 700;
}
.gap-arrow {
  margin: 0 4px;
  color: var(--app-soft);
  font-weight: 500;
}
.diag-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}
.diag-grid .diag-card { margin-bottom: 0; }
.gap-list { display: grid; gap: 12px; }
.gap-row-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text);
  margin-bottom: 6px;
}
.gap-nums { font-weight: 500; color: var(--app-muted); font-size: 12px; }
.issue-list, .homo-list { display: grid; gap: 10px; }
.issue-item, .homo-item {
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid var(--app-border);
  background: color-mix(in srgb, var(--app-surface) 88%, var(--app-bg0));
}
.issue-item.lv-warning { border-color: color-mix(in srgb, var(--app-warn) 45%, var(--app-border)); }
.issue-head, .homo-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: var(--app-text);
  margin-bottom: 4px;
}
.issue-text, .risk-text { font-size: 13px; color: var(--app-muted); line-height: 1.5; }
.liq-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 8px;
  font-size: 12px;
  color: var(--app-soft);
}
.breach-list { display: grid; gap: 10px; }
.breach-item {
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid var(--app-border);
  background: color-mix(in srgb, var(--app-surface) 88%, var(--app-bg0));
}
.breach-item.lv-warning { border-color: color-mix(in srgb, var(--app-warn) 40%, var(--app-border)); }
.breach-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: var(--app-text);
  margin-bottom: 4px;
}
.breach-text { font-size: 12px; color: var(--app-muted); line-height: 1.5; }
.chart-container { height: 260px; min-height: 220px; width: 100%; }
@media (max-width: 960px) {
  .merge-grid { grid-template-columns: 1fr; }
  .preset-row { flex-direction: column; align-items: stretch; }
  .preset-seg { width: 100%; }
  .diag-grid { grid-template-columns: 1fr; }
}
</style>
