<template>
  <div class="market-page">
    <div class="market-page-header">
      <div>
        <h3 class="market-page-title">市场摘要</h3>
        <div class="market-page-subtitle">
          只读观察：关键指数 + 自选 + 持仓今日贡献 + 价格预警。不改真实账本。
          交易日 cron 可自动检查；飞书推送需 FEISHU_ALERT_WEBHOOK；同规则默认冷却
          {{ alertCooldownMinutes == null ? 240 : alertCooldownMinutes }} 分钟。
        </div>
      </div>
      <div class="market-page-actions">
        <el-tag v-if="marketUpdatedAt" size="small" type="info">更新 {{ marketUpdatedAt }}</el-tag>
        <el-tag v-if="quoteCacheSeconds != null" size="small" type="info">行情缓存 {{ quoteCacheSeconds }}s</el-tag>
        <el-button size="small" :loading="marketLoading" @click="refreshMarket">刷新摘要</el-button>
        <el-button size="small" type="warning" :loading="alertChecking" @click="() => checkAlerts(false)">立即检查预警</el-button>
      </div>
    </div>

    <el-alert
      :title="marketSignals.portfolio_vs_market || '加载后显示持仓与大盘对比说明'"
      type="info"
      show-icon
      :closable="false"
      style="margin-bottom: 14px;"
    />

    <el-card v-if="marketHighlights && marketHighlights.length" shadow="never" style="margin-bottom: 16px;">
      <template #header>
        <span class="allocation-section-title">今天看点</span>
      </template>
      <ul class="market-highlights">
        <li v-for="(line, idx) in marketHighlights" :key="idx">{{ line }}</li>
      </ul>
      <div v-if="marketComparisons && marketComparisons.length" style="margin-top: 8px; font-size: 12px; color: #606266;">
        <div v-for="(c, i) in marketComparisons" :key="i">{{ c.text }}</div>
      </div>
    </el-card>

    <el-row :gutter="12" style="margin-bottom: 16px;">
      <el-col :xs="12" :sm="8" :md="6">
        <el-card shadow="hover" class="market-metric-card">
          <div class="market-metric-label">今日贡献粗估</div>
          <div class="market-metric-value" :style="{ color: (marketSignals.today_contrib_estimate || 0) >= 0 ? '#F56C6C' : '#67C23A' }">
            {{ formatMoney(marketSignals.today_contrib_estimate || 0, 2, true) }}
          </div>
          <div class="market-metric-sub">用现价涨跌% × 市值估算，非账本记账</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="6">
        <el-card shadow="hover" class="market-metric-card">
          <div class="market-metric-label">组合涨跌粗估</div>
          <div class="market-metric-value">
            {{ marketSignals.portfolio_change_pct_estimate == null ? '—' : ((marketSignals.portfolio_change_pct_estimate >= 0 ? '+' : '') + Number(marketSignals.portfolio_change_pct_estimate).toFixed(2) + '%') }}
          </div>
          <div class="market-metric-sub">投资市值 {{ formatMoney(marketSignals.total_market_value || 0) }}</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="6">
        <el-card shadow="hover" class="market-metric-card">
          <div class="market-metric-label">持仓浮盈（账本）</div>
          <div class="market-metric-value" :style="{ color: (marketSignals.total_profit || 0) >= 0 ? '#F56C6C' : '#67C23A' }">
            {{ formatMoney(marketSignals.total_profit || 0, 2, true) }}
          </div>
          <div class="market-metric-sub">与首页同一口径</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="6">
        <el-card shadow="hover" class="market-metric-card">
          <div class="market-metric-label">全周期盈亏（账本）</div>
          <div class="market-metric-value" :style="{ color: (marketSignals.lifetime_profit || 0) >= 0 ? '#F56C6C' : '#67C23A' }">
            {{ formatMoney(marketSignals.lifetime_profit || 0, 2, true) }}
          </div>
          <div class="market-metric-sub">摊薄成本路径</div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" style="margin-bottom: 16px;">
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;">
          <span class="allocation-section-title">关键指数</span>
          <span style="font-size:12px;color:#909399;">来源东财延时行情，失败时价格可为空</span>
        </div>
      </template>
      <el-table :data="indexRows" stripe empty-text="暂无指数数据" v-loading="marketLoading">
        <el-table-column prop="name" label="名称" min-width="120" />
        <el-table-column prop="code" label="代码" width="100" />
        <el-table-column label="最新" width="120" align="right" header-align="right">
          <template #default="scope">
            {{ scope.row.price == null ? '—' : Number(scope.row.price).toFixed(2) }}
          </template>
        </el-table-column>
        <el-table-column label="涨跌%" width="110" align="right" header-align="right">
          <template #default="scope">
            <span :style="{ color: changeColor(scope.row.change_pct) }">
              {{ formatChangePct(scope.row.change_pct) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" style="margin-bottom: 16px;">
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;">
          <div>
            <div class="allocation-section-title">自选关注</div>
            <div style="font-size:12px;color:#909399;margin-top:4px;">额外代码（股票/指数/ETF），不替代默认指数。指数建议填 secid（如 1.000300）。</div>
          </div>
          <div style="display:flex;gap:8px;">
            <el-button size="small" @click="addWatchlistRow">添加一行</el-button>
            <el-button size="small" type="primary" :loading="watchlistSaving" @click="saveWatchlist">保存自选</el-button>
          </div>
        </div>
      </template>
      <el-table :data="watchlistDraft" stripe empty-text="暂无自选，点「添加一行」">
        <el-table-column label="代码" min-width="120">
          <template #default="scope">
            <el-input v-model="scope.row.code" size="small" placeholder="代码" />
          </template>
        </el-table-column>
        <el-table-column label="名称" min-width="120">
          <template #default="scope">
            <el-input v-model="scope.row.name" size="small" placeholder="可选" />
          </template>
        </el-table-column>
        <el-table-column label="secid" min-width="120">
          <template #default="scope">
            <el-input v-model="scope.row.secid" size="small" placeholder="指数可选" />
          </template>
        </el-table-column>
        <el-table-column label="行情" width="160" align="right" header-align="right">
          <template #default="scope">
            <span v-if="quoteForWatch(scope.row.code)">
              {{ quoteForWatch(scope.row.code).price == null ? '—' : Number(quoteForWatch(scope.row.code).price).toFixed(2) }}
              <span :style="{ color: changeColor(quoteForWatch(scope.row.code).change_pct), marginLeft: '6px' }">
                {{ formatChangePct(quoteForWatch(scope.row.code).change_pct) }}
              </span>
            </span>
            <span v-else style="color:#c0c4cc;">—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="90" align="center">
          <template #default="scope">
            <el-button type="danger" link @click="removeWatchlistRow(scope.$index)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" style="margin-bottom: 16px;">
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;">
          <span class="allocation-section-title">持仓今日贡献粗估（按绝对值排序）</span>
          <span style="font-size:12px;color:#909399;">最多显示 20 条</span>
        </div>
      </template>
      <el-table :data="holdingsDayRows" stripe empty-text="暂无持仓或无法估算" v-loading="marketLoading">
        <el-table-column prop="name" label="名称" min-width="120" show-overflow-tooltip />
        <el-table-column prop="code" label="代码" width="100" />
        <el-table-column label="市值" width="120" align="right" header-align="right">
          <template #default="scope">{{ formatMoney(scope.row.market_value) }}</template>
        </el-table-column>
        <el-table-column label="现价" width="100" align="right" header-align="right">
          <template #default="scope">{{ scope.row.price == null ? '—' : Number(scope.row.price).toFixed(4) }}</template>
        </el-table-column>
        <el-table-column label="涨跌%" width="100" align="right" header-align="right">
          <template #default="scope">
            <span :style="{ color: changeColor(scope.row.change_pct) }">{{ formatChangePct(scope.row.change_pct) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本日贡献" width="120" align="right" header-align="right">
          <template #default="scope">
            <span :style="{ color: changeColor(scope.row.day_contrib) }">
              {{ scope.row.day_contrib == null ? '—' : formatMoney(scope.row.day_contrib, 2, true) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="source" label="价格源" width="80" />
      </el-table>
    </el-card>

    <el-card shadow="never" style="margin-bottom: 16px;">
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;">
          <div>
            <div class="allocation-section-title">价格预警规则</div>
            <div style="font-size:12px;color:#909399;margin-top:4px;">
              持仓或指数代码，上穿/下穿阈值。同规则默认 {{ alertCooldownMinutes == null ? 240 : alertCooldownMinutes }} 分钟内不重复记录/推送。
            </div>
          </div>
          <el-button type="primary" size="small" @click="openAlertCreate">添加规则</el-button>
        </div>
      </template>
      <el-table :data="alertRules" stripe empty-text="暂无规则">
        <el-table-column label="类型" width="90">
          <template #default="scope">{{ scope.row.target_type === 'index' ? '指数' : '持仓' }}</template>
        </el-table-column>
        <el-table-column prop="name" label="名称" min-width="120" show-overflow-tooltip />
        <el-table-column prop="code" label="代码" width="100" />
        <el-table-column label="条件" width="90">
          <template #default="scope">{{ scope.row.condition === 'below' ? '≤ 下穿' : '≥ 上穿' }}</template>
        </el-table-column>
        <el-table-column label="阈值" width="110" align="right" header-align="right">
          <template #default="scope">{{ Number(scope.row.threshold).toFixed(4) }}</template>
        </el-table-column>
        <el-table-column label="启用" width="80" align="center">
          <template #default="scope">
            <el-switch
              :model-value="Number(scope.row.enabled) === 1 || scope.row.enabled === true"
              @change="() => toggleAlertEnabled(scope.row)"
            />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" align="center">
          <template #default="scope">
            <el-button type="primary" link @click="openAlertEdit(scope.row)">编辑</el-button>
            <el-button type="danger" link @click="deleteAlertRule(scope.row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card v-if="triggeredAlerts && triggeredAlerts.length" shadow="never" style="margin-bottom: 16px;">
      <template #header>
        <span class="allocation-section-title">最近一次检查触发</span>
      </template>
      <el-table :data="triggeredAlerts" stripe>
        <el-table-column prop="message" label="说明" min-width="280" show-overflow-tooltip />
        <el-table-column prop="price" label="触发价" width="110" align="right" header-align="right">
          <template #default="scope">{{ Number(scope.row.price).toFixed(4) }}</template>
        </el-table-column>
        <el-table-column label="涨跌%" width="100" align="right" header-align="right">
          <template #default="scope">
            <span :style="{ color: changeColor(scope.row.change_pct) }">{{ formatChangePct(scope.row.change_pct) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="trigger_time" label="时间" width="180" />
      </el-table>
    </el-card>

    <el-card shadow="never" style="margin-bottom: 16px;">
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;">
          <div>
            <div class="allocation-section-title">预警历史</div>
            <div style="font-size:12px;color:#909399;margin-top:4px;">来自 alert_events，支持代码/日期筛选、导出、清空</div>
          </div>
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
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
              placeholder="开始日期"
              size="small"
              style="width:140px"
            />
            <el-date-picker
              v-model="alertEventEndDate"
              type="date"
              value-format="YYYY-MM-DD"
              placeholder="结束日期"
              size="small"
              style="width:140px"
            />
            <el-button size="small" :loading="alertEventsLoading" @click="fetchAlertEvents">刷新历史</el-button>
            <el-button size="small" @click="exportAlertEvents">导出 CSV</el-button>
            <el-button size="small" type="danger" plain @click="clearAlertEvents">清空</el-button>
          </div>
        </div>
      </template>
      <el-table :data="alertEvents" stripe empty-text="暂无触发记录" v-loading="alertEventsLoading">
        <el-table-column prop="target_code" label="代码" width="100" />
        <el-table-column prop="message" label="说明" min-width="280" show-overflow-tooltip />
        <el-table-column label="触发价" width="110" align="right" header-align="right">
          <template #default="scope">
            {{ scope.row.triggered_price == null ? '—' : Number(scope.row.triggered_price).toFixed(4) }}
          </template>
        </el-table-column>
        <el-table-column label="阈值" width="100" align="right" header-align="right">
          <template #default="scope">
            {{ scope.row.threshold == null ? '—' : Number(scope.row.threshold).toFixed(4) }}
          </template>
        </el-table-column>
        <el-table-column prop="trigger_time" label="时间" width="180" />
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
  </div>
</template>

<script setup>
import { useAppCtx } from '../composables/useAppCtx.js';

const {
  marketLoading,
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
  marketSignals,
  marketHighlights,
  marketComparisons,
  marketUpdatedAt,
  quoteCacheSeconds,
  alertCooldownMinutes,
  refreshMarket,
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
  formatMoney,
} = useAppCtx();

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
  return (watchlistRows.value || []).find((x) => String(x.code) === c) || null;
};
</script>

<style scoped>
.market-page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}
.market-page-title {
  margin: 0 0 4px;
  font-size: 18px;
}
.market-page-subtitle {
  font-size: 12px;
  color: #909399;
}
.market-page-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.market-metric-card {
  margin-bottom: 8px;
}
.market-metric-label {
  font-size: 12px;
  color: #909399;
}
.market-metric-value {
  font-size: 20px;
  font-weight: 600;
  margin: 6px 0 4px;
}
.market-metric-sub {
  font-size: 12px;
  color: #a8abb2;
}
.market-highlights {
  margin: 0;
  padding-left: 18px;
  color: #303133;
  line-height: 1.7;
  font-size: 13px;
}
</style>
