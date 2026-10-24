<template>
  <PageShell>
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
            :on-change="onBrokerUpload"
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
            :loading="brokerLoading || applying"
            :disabled="!brokerSelected.length || applying"
            @click="onApplySelectedCorrections"
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
        <DataTable
          v-else
          :rows="brokerResult.diffs"
          row-key="code"
          empty-text="无差异"
          label="券商与系统持仓差异明细"
        >
        <el-table
          :data="brokerResult.diffs"
          stripe
          size="small"
          class="table-scroll"
          style="width: 100%"
          aria-label="券商与系统持仓差异明细"
          empty-text="无差异"
        >
          <el-table-column prop="code" label="代码" width="90" fixed="left" />
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
              <span :class="Number(s.row.quantity_diff || 0) === 0 ? 'num-muted' : 'num-warn'">
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
        <template #card="{ row }">
          <div class="m-card">
            <div class="m-card-row">
              <div class="m-card-title">
                <span>{{ row.name || row.code }}</span>
                <span class="m-card-sub" style="margin-left: 6px;">{{ row.code }}</span>
              </div>
              <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
            </div>
            <div class="m-card-metrics" style="margin-top: 6px;">
              <div class="m-card-metric">
                <span class="m-card-metric-label">券商/系统数量</span>
                <span class="m-card-metric-val">{{ row.broker_quantity ?? '—' }} / {{ row.app_quantity ?? '—' }}</span>
              </div>
              <div class="m-card-metric">
                <span class="m-card-metric-label">数量差</span>
                <span class="m-card-metric-val" :class="Number(row.quantity_diff || 0) === 0 ? 'num-muted' : 'num-warn'">
                  {{ row.quantity_diff }}
                </span>
              </div>
            </div>
            <div class="m-card-metrics" style="margin-top: 4px;">
              <div class="m-card-metric">
                <span class="m-card-metric-label">券商成本</span>
                <span class="m-card-metric-val">{{ row.broker_avg_cost ?? '—' }}</span>
              </div>
              <div class="m-card-metric">
                <span class="m-card-metric-label">系统成本</span>
                <span class="m-card-metric-val">{{ row.app_avg_cost ?? '—' }}</span>
              </div>
            </div>
            <div v-if="row.reasons && row.reasons.length" class="m-card-sub" style="margin-top: 6px;">
              {{ row.reasons.join('；') }}
            </div>
          </div>
        </template>
        </DataTable>

        <div v-if="brokerResult.suggestions?.length" class="broker-suggest-block">
          <div class="broker-suggest-title">校正建议（以券商为准；仅系统有的会建议数量改为 0）</div>
          <DataTable :rows="brokerResult.suggestions" row-key="code" label="券商对账校正建议明细">
          <el-table
            :data="brokerResult.suggestions"
            stripe
            size="small"
            class="table-scroll"
            style="width: 100%"
            aria-label="券商对账校正建议明细"
            @selection-change="onBrokerSelectionChange"
          >
            <el-table-column type="selection" width="42" fixed="left" />
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
          </DataTable>
        </div>
      </template>
    </el-card>

    <el-card shadow="never" class="broker-card" style="margin-top: 14px">
      <template #header>
        <div class="ops-card-head">
          <div>
            <div class="ops-section-title">对账历史</div>
            <div class="ops-hint">每次预览和应用都会留一条摘要，方便回看上次差了哪些代码</div>
          </div>
          <el-button size="small" @click="fetchBrokerHistory">刷新</el-button>
        </div>
      </template>
      <DataTable :rows="brokerHistory" row-key="id" empty-text="还没有对账记录" label="券商对账历史记录">
      <el-table :data="brokerHistory" stripe size="small" empty-text="还没有对账记录" style="width: 100%" aria-label="券商对账历史记录">
        <el-table-column label="时间" width="170" fixed="left">
          <template #default="s">{{ s.row.created_at || '—' }}</template>
        </el-table-column>
        <el-table-column label="类型" width="80">
          <template #default="s">
            <el-tag size="small" :type="s.row.kind === 'apply' ? 'warning' : 'info'">
              {{ s.row.kind === 'apply' ? '应用' : '预览' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="as_of_date" label="锚点日" width="110" />
        <el-table-column prop="filename" label="文件" min-width="120" show-overflow-tooltip />
        <el-table-column label="差异" width="80" align="right">
          <template #default="s">{{ s.row.diff_count ?? 0 }}</template>
        </el-table-column>
        <el-table-column label="写入" width="80" align="right">
          <template #default="s">{{ s.row.applied_count ?? 0 }}</template>
        </el-table-column>
        <el-table-column label="现金" width="90">
          <template #default="s">{{ s.row.cash_status || '—' }}</template>
        </el-table-column>
        <el-table-column prop="summary_text" label="摘要" min-width="220" show-overflow-tooltip />
        <el-table-column prop="codes" label="代码" min-width="140" show-overflow-tooltip />
      </el-table>
      <template #card="{ row }">
        <div class="m-card">
          <div class="m-card-row">
            <div class="m-card-title">
              <el-tag size="small" :type="row.kind === 'apply' ? 'warning' : 'info'">
                {{ row.kind === 'apply' ? '应用' : '预览' }}
              </el-tag>
              <span style="margin-left: 6px; font-size: 13px;">{{ row.created_at || '—' }}</span>
            </div>
            <div class="m-card-meta">
              <span v-if="row.as_of_date">锚点: {{ row.as_of_date }}</span>
            </div>
          </div>
          <div class="m-card-metrics" style="margin-top: 6px;">
            <div class="m-card-metric">
              <span class="m-card-metric-label">差异/写入</span>
              <span class="m-card-metric-val">{{ row.diff_count ?? 0 }} / {{ row.applied_count ?? 0 }}</span>
            </div>
            <div class="m-card-metric">
              <span class="m-card-metric-label">现金</span>
              <span class="m-card-metric-val">{{ row.cash_status || '—' }}</span>
            </div>
          </div>
          <div v-if="row.summary_text" class="m-card-sub" style="margin-top: 6px;">{{ row.summary_text }}</div>
          <div v-if="row.filename || row.codes" class="m-card-meta" style="margin-top: 4px;">
            <span v-if="row.filename">文件: {{ row.filename }}</span>
            <span v-if="row.codes">代码: {{ row.codes }}</span>
          </div>
        </div>
      </template>
      </DataTable>
    </el-card>
  </PageShell>
</template>

<script setup>
import { onMounted, ref } from 'vue';
import PageShell from '../components/PageShell.vue';
import DataTable from '../components/DataTable.vue';
import { useAppCtx } from '../composables/useAppCtx.js';

const {
  brokerResult,
  brokerLoading,
  brokerSelected,
  brokerAsOfDate,
  brokerCashInput,
  brokerHistory,
  statusLabel,
  statusType,
  onBrokerFileChange,
  onBrokerSelectionChange,
  selectAllSuggestions,
  clearBrokerSelection,
  applySelectedCorrections,
  fetchBrokerHistory,
} = useAppCtx();

// 写操作防连点：`brokerLoading` 要等确认框点完才置位（在 modules/brokerReconcile.js 的
// applySelectedCorrections 里），所以这里再补一个本地 in-flight ref：进入前判断、finally 复位。
const applying = ref(false);

async function onApplySelectedCorrections() {
  if (applying.value) return;
  applying.value = true;
  try {
    await applySelectedCorrections();
  } finally {
    applying.value = false;
  }
}

// 上传预览：模块里的 onBrokerFileChange 开头就置 brokerLoading，复用它做入口判断
function onBrokerUpload(file) {
  if (brokerLoading.value) return;
  return onBrokerFileChange(file);
}

onMounted(() => {
  fetchBrokerHistory?.();
});
</script>

<style scoped>
.ops-card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
  flex-wrap: wrap;
}
.ops-section-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--app-text);
}
.ops-hint {
  margin-top: 2px;
  font-size: 12px;
  color: var(--app-soft);
}
</style>
