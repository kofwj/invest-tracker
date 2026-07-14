<template>
  <div class="market-page">
    <div class="market-page-header">
      <div>
        <h3 class="market-page-title">市场摘要</h3>
        <div class="market-page-subtitle">
          只读观察：关键指数 + 持仓今日贡献粗估 + 价格阈值预警。不改真实账本。
        </div>
      </div>
      <div class="market-page-actions">
        <el-tag v-if="marketUpdatedAt" size="small" type="info">更新 {{ marketUpdatedAt }}</el-tag>
        <el-button size="small" :loading="marketLoading" @click="refreshMarket">刷新摘要</el-button>
        <el-button size="small" type="warning" :loading="alertChecking" @click="checkAlerts">立即检查预警</el-button>
      </div>
    </div>

    <el-alert
      :title="marketSignals.portfolio_vs_market || '加载后显示持仓与大盘对比说明'"
      type="info"
      show-icon
      :closable="false"
      style="margin-bottom: 14px;"
    />

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
            <div style="font-size:12px;color:#909399;margin-top:4px;">持仓或指数代码，上穿/下穿阈值。仅手动「立即检查」，暂不自动推送。</div>
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

    <el-card v-if="triggeredAlerts && triggeredAlerts.length" shadow="never">
      <template #header>
        <span class="allocation-section-title">最近一次检查触发</span>
      </template>
      <el-table :data="triggeredAlerts" stripe>
        <el-table-column prop="message" label="说明" min-width="260" show-overflow-tooltip />
        <el-table-column prop="price" label="触发价" width="110" align="right" header-align="right">
          <template #default="scope">{{ Number(scope.row.price).toFixed(4) }}</template>
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
  alertRules,
  alertForm,
  alertEditDialog,
  triggeredAlerts,
  indexRows,
  holdingsDayRows,
  marketSignals,
  marketUpdatedAt,
  refreshMarket,
  openAlertCreate,
  openAlertEdit,
  saveAlertRule,
  deleteAlertRule,
  toggleAlertEnabled,
  checkAlerts,
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
</style>
