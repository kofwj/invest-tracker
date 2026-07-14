<template>
  <div class="broker-page">
    <div class="broker-header">
      <div>
        <h3 class="broker-title">券商对账单</h3>
        <div class="broker-sub">
          上传券商持仓 CSV/Excel，对照本系统差异；勾选后写入「持仓校正」（自动备份，并自动重扫）。
        </div>
      </div>
    </div>

    <el-alert
      title="怎么用"
      type="info"
      show-icon
      :closable="false"
      class="broker-alert"
      description="1）券商 App 导出持仓表 CSV/Excel；2）可选填券商证券现金；3）上传预览；4）勾选 → 应用校正。应用后会自动重扫。"
    />

    <el-card shadow="never" class="broker-card">
      <div class="broker-toolbar">
        <div class="broker-toolbar-left">
          <span class="broker-label">校正锚点日</span>
          <el-date-picker
            v-model="brokerAsOfDate"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="默认今天"
            size="small"
            style="width: 150px"
          />
          <span class="broker-label">券商证券现金</span>
          <el-input-number
            v-model="brokerCashInput"
            :min="0"
            :controls="false"
            placeholder="可选"
            size="small"
            style="width: 130px"
          />
          <el-upload
            :auto-upload="false"
            :show-file-list="false"
            accept=".csv,.xlsx,.xls,text/csv,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            :on-change="onBrokerFileChange"
            :disabled="brokerLoading"
          >
            <el-button type="primary" :loading="brokerLoading">上传预览</el-button>
          </el-upload>
        </div>
        <div class="broker-toolbar-right" v-if="brokerResult">
          <el-tag type="info">{{ brokerResult.summary_text }}</el-tag>
          <el-button size="small" @click="selectAllSuggestions" :disabled="!brokerResult.suggestions?.length">全选建议</el-button>
          <el-button size="small" @click="clearBrokerSelection">清空勾选</el-button>
          <el-button
            type="warning"
            size="small"
            :loading="brokerLoading"
            :disabled="!brokerSelected.length"
            @click="applySelectedCorrections"
          >
            应用勾选校正（{{ brokerSelected.length }}）
          </el-button>
        </div>
      </div>

      <div v-if="brokerResult?.parse" class="broker-parse-meta">
        识别字段：{{ (brokerResult.parse.mapped_fields || []).join('、') || '—' }}
        · 格式 {{ brokerResult.parse.format || 'csv' }}
        · 券商行数 {{ brokerResult.broker_count }} · 系统持仓 {{ brokerResult.app_count }}
        <span v-if="brokerResult.filename"> · 文件 {{ brokerResult.filename }}</span>
      </div>

      <el-alert
        v-if="brokerResult?.cash"
        :title="brokerResult.cash.text"
        :type="brokerResult.cash.status === 'match' ? 'success' : 'warning'"
        show-icon
        :closable="false"
        style="margin-bottom: 12px"
      />

      <el-empty v-if="!brokerResult" description="还没上传文件。支持 CSV / Excel；列：证券代码、证券名称、数量、成本价" />

      <template v-else>
        <el-alert
          v-if="!brokerResult.diff_count"
          title="与当前系统持仓数量/成本一致（在容差内）"
          type="success"
          show-icon
          :closable="false"
          style="margin-bottom: 12px"
        />
        <el-table
          v-else
          :data="brokerResult.diffs"
          stripe
          size="small"
          class="table-scroll"
          style="width: 100%"
          empty-text="无差异"
        >
          <el-table-column prop="code" label="代码" width="90" />
          <el-table-column prop="name" label="名称" min-width="110" show-overflow-tooltip />
          <el-table-column label="状态" width="100">
            <template #default="s">
              <el-tag :type="statusType(s.row.status)" size="small">{{ statusLabel(s.row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="券商数量" width="100" align="right">
            <template #default="s">{{ s.row.broker_quantity ?? '—' }}</template>
          </el-table-column>
          <el-table-column label="系统数量" width="100" align="right">
            <template #default="s">{{ s.row.app_quantity ?? '—' }}</template>
          </el-table-column>
          <el-table-column label="数量差" width="90" align="right">
            <template #default="s">
              <span :style="{ color: Number(s.row.quantity_diff || 0) === 0 ? '#909399' : '#E6A23C' }">
                {{ s.row.quantity_diff }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="券商成本" width="100" align="right">
            <template #default="s">{{ s.row.broker_avg_cost ?? '—' }}</template>
          </el-table-column>
          <el-table-column label="系统成本" width="100" align="right">
            <template #default="s">{{ s.row.app_avg_cost ?? '—' }}</template>
          </el-table-column>
          <el-table-column label="原因" min-width="160">
            <template #default="s">{{ (s.row.reasons || []).join('；') }}</template>
          </el-table-column>
        </el-table>

        <div v-if="brokerResult.suggestions?.length" class="broker-suggest-block">
          <div class="broker-suggest-title">校正建议（以券商为准；仅系统有的会建议数量改为 0）</div>
          <el-table
            :data="brokerResult.suggestions"
            stripe
            size="small"
            class="table-scroll"
            style="width: 100%"
            @selection-change="onBrokerSelectionChange"
          >
            <el-table-column type="selection" width="42" />
            <el-table-column prop="code" label="代码" width="90" />
            <el-table-column prop="name" label="名称" min-width="100" show-overflow-tooltip />
            <el-table-column prop="date" label="校正日" width="110" />
            <el-table-column prop="actual_quantity" label="校正数量" width="100" align="right" />
            <el-table-column prop="actual_avg_cost" label="校正成本" width="100" align="right" />
            <el-table-column prop="actual_total_dividend" label="累计分红" width="100" align="right" />
            <el-table-column label="状态" width="100">
              <template #default="s">
                <el-tag :type="statusType(s.row.status)" size="small">{{ statusLabel(s.row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="remark" label="备注" min-width="120" show-overflow-tooltip />
          </el-table>
        </div>
      </template>
    </el-card>
  </div>
</template>

<script setup>
import { useAppCtx } from '../composables/useAppCtx.js';

const {
  brokerResult,
  brokerLoading,
  brokerSelected,
  brokerAsOfDate,
  brokerCashInput,
  statusLabel,
  statusType,
  onBrokerFileChange,
  onBrokerSelectionChange,
  selectAllSuggestions,
  clearBrokerSelection,
  applySelectedCorrections,
} = useAppCtx();
</script>
