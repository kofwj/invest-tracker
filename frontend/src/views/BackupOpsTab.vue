<template>
  <PageShell>
    <template #actions>
      <el-space wrap>
        <el-button size="small" @click="fetchMaintenance" :loading="maintenanceLoading">刷新列表</el-button>
        <el-button size="small" type="primary" :loading="maintenanceLoading || backupBusy === 'create'" :disabled="!!backupBusy && backupBusy !== 'create'" @click="onCreateBackup">创建备份</el-button>
        <el-upload
          :auto-upload="false"
          :show-file-list="false"
          accept=".db,.bak"
          :on-change="onRestoreUploadedBackup"
        >
          <el-button size="small" type="danger" plain :loading="maintenanceLoading || backupBusy === 'upload'" :disabled="!!backupBusy && backupBusy !== 'upload'">上传并恢复</el-button>
        </el-upload>
      </el-space>
    </template>

    <!-- 四个状态数：一行、发丝线分格（新版排版） -->
    <div class="app-stat-row cols-4">
      <div class="app-stat-cell">
        <div class="k">数据库</div>
        <div class="v" :class="maintenanceStatus.db_exists ? 'ok' : 'warn'" :title="dbSizeText">{{ maintenanceStatus.db_exists ? '正常' : '未找到' }}</div>
      </div>
      <div class="app-stat-cell">
        <div class="k">备份数量</div>
        <div class="v" :class="backupCount ? 'ok' : 'warn'">{{ String(backupCount) }}</div>
      </div>
      <div class="app-stat-cell">
        <div class="k">最近备份</div>
        <div class="v" :title="String(maintenanceStatus.latest_backup || latestBackupText || '')">{{ latestBackupShort }}</div>
      </div>
      <div class="app-stat-cell">
        <div class="k">建议</div>
        <div class="v">先下本地</div>
      </div>
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
      <el-table :data="backups" stripe size="small" style="width:100%;" empty-text="暂无备份文件" v-loading="maintenanceLoading" aria-label="备份文件列表">
        <el-table-column prop="filename" label="备份文件" min-width="260" show-overflow-tooltip />
        <el-table-column label="大小" width="110" align="right" header-align="right">
          <template #default="scope">
            <span class="num-cell">{{ (Number(scope.row.size || 0) / 1024 / 1024).toFixed(2) }} MB</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180" />
        <el-table-column label="操作" width="220" align="center" header-align="center">
          <template #default="scope">
            <el-button type="primary" link size="small" :loading="backupBusy === 'download:' + scope.row.filename" :disabled="!!backupBusy" @click="onDownloadBackup(scope.row)">下载</el-button>
            <el-button type="warning" link size="small" :loading="backupBusy === 'restore:' + scope.row.filename" :disabled="!!backupBusy" @click="onRestoreBackup(scope.row)">恢复</el-button>
            <el-button type="danger" link size="small" :loading="backupBusy === 'delete:' + scope.row.filename" :disabled="!!backupBusy" @click="onDeleteBackup(scope.row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </PageShell>
</template>

<script setup>
import PageShell from '../components/PageShell.vue';
import { computed, ref } from 'vue';
import { useAppCtx } from '../composables/useAppCtx.js';

const {
  maintenanceStatus, backups, maintenanceLoading, latestBackupText,
  fetchMaintenance, createDbBackup, downloadBackup, restoreBackup, deleteBackup, restoreUploadedBackup,
} = useAppCtx();

// 表格行上的 下载/恢复/删除 以前只靠 v-loading 遮罩，按钮本身可连点。
// 这里用一个 in-flight 标志（`动作:文件名`）挡住，进行中整行三个按钮都禁用。
const backupBusy = ref('');

async function runBackupAction(key, fn) {
  if (backupBusy.value) return;
  backupBusy.value = key;
  try {
    await fn();
  } finally {
    if (backupBusy.value === key) backupBusy.value = '';
  }
}

const onDownloadBackup = (row) => runBackupAction(`download:${row?.filename || ''}`, () => downloadBackup(row));
const onRestoreBackup = (row) => runBackupAction(`restore:${row?.filename || ''}`, () => restoreBackup(row));
const onDeleteBackup = (row) => runBackupAction(`delete:${row?.filename || ''}`, () => deleteBackup(row));

// 工具栏的「创建备份 / 上传并恢复」以前只有表格 v-loading 遮罩，按钮本身没有入口判断，
// 连点会发两次 POST。这里复用同一个 in-flight 标志（'create' / 'upload'）。
const onCreateBackup = () => runBackupAction('create', createDbBackup);
const onRestoreUploadedBackup = (file) => runBackupAction('upload', () => restoreUploadedBackup(file));

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
