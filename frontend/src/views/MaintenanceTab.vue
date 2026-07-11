<template>
                <el-card shadow="never">
                    <template #header>
                        <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;">
                            <div>
                                <div class="allocation-section-title">数据维护</div>
                                <div style="font-size:12px;color:#909399;margin-top:4px;">数据库备份、下载和恢复。恢复前会自动创建当前数据库备份。</div>
                            </div>
                            <el-space wrap>
                                <el-button @click="fetchMaintenance">刷新列表</el-button>
                                <el-button type="primary" :loading="maintenanceLoading" @click="createDbBackup">创建备份</el-button>
                                <el-upload
                                    :auto-upload="false"
                                    :show-file-list="false"
                                    accept=".db,.bak"
                                    :on-change="restoreUploadedBackup"
                                >
                                    <el-button type="danger" plain :loading="maintenanceLoading">上传备份并恢复</el-button>
                                </el-upload>
                            </el-space>
                        </div>
                    </template>
                    <el-descriptions :column="3" border style="margin-bottom:16px;">
                        <el-descriptions-item label="数据库状态">{{ maintenanceStatus.db_exists ? '正常' : '未找到' }}</el-descriptions-item>
                        <el-descriptions-item label="数据库大小">{{ ((maintenanceStatus.db_size || 0) / 1024 / 1024).toFixed(2) }} MB</el-descriptions-item>
                        <el-descriptions-item label="最近备份">{{ maintenanceStatus.latest_backup || '暂无' }}</el-descriptions-item>
                    </el-descriptions>
                    <el-alert
                        title="恢复数据库属于高风险操作：系统会先自动备份当前数据库，但仍建议先下载关键备份文件。"
                        type="warning"
                        show-icon
                        :closable="false"
                        style="margin-bottom: 16px;"
                    ></el-alert>
                    <el-table :data="backups" stripe style="width:100%;" empty-text="暂无备份文件">
                        <el-table-column prop="filename" label="备份文件" min-width="260" show-overflow-tooltip></el-table-column>
                        <el-table-column label="大小" width="110" align="right" header-align="right">
                            <template #default="scope">{{ (Number(scope.row.size || 0) / 1024 / 1024).toFixed(2) }} MB</template>
                        </el-table-column>
                        <el-table-column prop="created_at" label="创建时间" width="180"></el-table-column>
                        <el-table-column label="操作" width="230" align="center" header-align="center">
                            <template #default="scope">
                                <el-button type="primary" link @click="downloadBackup(scope.row)">下载</el-button>
                                <el-button type="warning" link @click="restoreBackup(scope.row)">恢复</el-button>
                                <el-button type="danger" link @click="deleteBackup(scope.row)">删除</el-button>
                            </template>
                        </el-table-column>
                    </el-table>
                </el-card>
</template>

<script setup>
import { useAppCtx } from '../composables/useAppCtx.js';
const { maintenanceStatus, backups, maintenanceLoading, fetchMaintenance, createDbBackup, downloadBackup, restoreBackup, deleteBackup, restoreUploadedBackup } = useAppCtx();
</script>
