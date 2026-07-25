<template>
  <PageShell
    title="数据备份"
    subtitle="数据库备份、下载和恢复。恢复前会自动再备份当前库。"
  >
    <template #actions>
      <el-space wrap>
        <el-button size="small" @click="fetchMaintenance" :loading="maintenanceLoading">刷新列表</el-button>
        <el-button size="small" type="primary" :loading="maintenanceLoading" @click="createDbBackup">创建备份</el-button>
        <el-upload
          :auto-upload="false"
          :show-file-list="false"
          accept=".db,.bak"
          :on-change="restoreUploadedBackup"
        >
          <el-button size="small" type="danger" plain :loading="maintenanceLoading">上传并恢复</el-button>
        </el-upload>
      </el-space>
    </template>

    <div class="ledger-metrics cols-4">
      <MetricCard
        label="数据库"
        :value="maintenanceStatus.db_exists ? '正常' : '未找到'"
        :sub="dbSizeText"
        :tone="maintenanceStatus.db_exists ? 'ok' : 'warn'"
        main
        :title="dbSizeText"
      />
      <MetricCard
        label="备份数量"
        :value="String(backupCount)"
        sub="服务器本地文件"
        :tone="backupCount ? 'ok' : 'warn'"
      />
      <MetricCard
        label="最近备份"
        :value="latestBackupShort"
        :sub="latestBackupText"
        :title="String(maintenanceStatus.latest_backup || latestBackupText || '')"
      />
      <MetricCard
        label="建议"
        value="先下本地"
        sub="操作前创建并下载一份"
      />
    </div>

    <el-alert
      title="恢复属于高风险操作：系统会先自动备份当前库，但仍建议先下载最新备份到电脑。恢复后会刷新首页/持仓/交易。"
      type="warning"
      show-icon
      :closable="false"
      style="margin-bottom: 14px;"
    />

    <el-card shadow="never" class="ops-card">
      <template #header>
        <div class="ops-card-head">
          <div>
            <div class="ops-section-title">备份文件</div>
            <div class="ops-hint">下载到本地最稳；恢复会覆盖当前库</div>
          </div>
          <el-tag size="small" type="info">{{ backupCount }} 份</el-tag>
        </div>
      </template>
      <el-table :data="backups" stripe size="small" style="width:100%;" empty-text="暂无备份文件" v-loading="maintenanceLoading">
        <el-table-column prop="filename" label="备份文件" min-width="260" show-overflow-tooltip />
        <el-table-column label="大小" width="110" align="right" header-align="right">
          <template #default="scope">
            <span class="num-cell">{{ (Number(scope.row.size || 0) / 1024 / 1024).toFixed(2) }} MB</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180" />
        <el-table-column label="操作" width="220" align="center" header-align="center">
          <template #default="scope">
            <el-button type="primary" link size="small" @click="downloadBackup(scope.row)">下载</el-button>
            <el-button type="warning" link size="small" @click="restoreBackup(scope.row)">恢复</el-button>
            <el-button type="danger" link size="small" @click="deleteBackup(scope.row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </PageShell>
</template>

<script setup>
import PageShell from '../components/PageShell.vue';
import MetricCard from '../components/MetricCard.vue';
import { computed } from 'vue';
import { useAppCtx } from '../composables/useAppCtx.js';

const {
  maintenanceStatus, backups, maintenanceLoading, latestBackupText,
  fetchMaintenance, createDbBackup, downloadBackup, restoreBackup, deleteBackup, restoreUploadedBackup,
} = useAppCtx();

const backupCount = computed(() => {
  const n = Number(maintenanceStatus.value?.backup_count || 0);
  if (n) return n;
  const list = backups?.value ?? backups ?? [];
  return Array.isArray(list) ? list.length : 0;
});

const dbSizeText = computed(() => {
  const bytes = Number(maintenanceStatus.value?.db_size || 0);
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
});

const latestBackupShort = computed(() => {
  const name = String(maintenanceStatus.value?.latest_backup || '').trim();
  if (!name) return '暂无';
  if (name.length <= 18) return name;
  return `${name.slice(0, 8)}…${name.slice(-6)}`;
});
</script>

<style scoped>
.ops-card { margin-bottom: 14px; }
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
