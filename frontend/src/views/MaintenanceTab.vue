<template>
                <el-card shadow="never" style="margin-bottom:16px;">
                    <template #header>
                        <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;">
                            <div>
                                <div class="allocation-section-title">消息推送（VPS 自有，独立于 Hermes）</div>
                                <div style="font-size:12px;color:#909399;margin-top:4px;">
                                    通道密钥写在服务器 .env；这里管开关、事件订阅、试推和最近日志。
                                </div>
                            </div>
                            <el-space wrap>
                                <el-button @click="fetchNotifyPanel" :loading="notifyLoading">刷新</el-button>
                                <el-button type="primary" :loading="notifyLoading" @click="saveNotifyPanel">保存设置</el-button>
                                <el-button type="success" plain :loading="notifyLoading" @click="testNotifyPush">试推一条</el-button>
                            </el-space>
                        </div>
                    </template>

                    <el-row :gutter="16" style="margin-bottom:12px;">
                        <el-col :xs="24" :sm="8">
                            <div style="margin-bottom:8px;font-size:13px;color:#606266;">总开关</div>
                            <el-switch v-model="notifyStatus.enabled" active-text="开" inactive-text="关"></el-switch>
                        </el-col>
                        <el-col :xs="24" :sm="8">
                            <div style="margin-bottom:8px;font-size:13px;color:#606266;">正文模板</div>
                            <el-radio-group v-model="notifyStatus.template" size="small">
                                <el-radio-button label="short">短</el-radio-button>
                                <el-radio-button label="medium">中</el-radio-button>
                            </el-radio-group>
                        </el-col>
                        <el-col :xs="24" :sm="8">
                            <div style="margin-bottom:8px;font-size:13px;color:#606266;">同事件冷却（分钟）</div>
                            <el-input-number v-model="notifyStatus.cooldown_minutes" :min="0" :max="10080" :step="30" size="small"></el-input-number>
                        </el-col>
                    </el-row>

                    <div style="margin:12px 0 8px;font-weight:600;">通道就绪状态（密钥在 .env）</div>
                    <el-table :data="channelRows" size="small" style="width:100%;margin-bottom:16px;" empty-text="暂无">
                        <el-table-column prop="name" label="通道" width="110"></el-table-column>
                        <el-table-column label="状态" width="100">
                            <template #default="s">
                                <el-tag :type="s.row.configured ? 'success' : 'info'" size="small">
                                    {{ s.row.configured ? '已配置' : '未配置' }}
                                </el-tag>
                            </template>
                        </el-table-column>
                        <el-table-column prop="hint" label="提示" min-width="180" show-overflow-tooltip></el-table-column>
                    </el-table>

                    <div style="margin:8px 0;font-weight:600;">事件 → 通道（逗号分隔：feishu,dingtalk,wecom,telegram）</div>
                    <el-table :data="eventRows" size="small" style="width:100%;margin-bottom:12px;">
                        <el-table-column prop="event" label="事件" width="140"></el-table-column>
                        <el-table-column prop="label" label="说明" min-width="140"></el-table-column>
                        <el-table-column label="通道" min-width="220">
                            <template #default="s">
                                <el-input v-model="notifyEventDraft[s.row.event]" size="small" placeholder="例如 feishu,telegram"></el-input>
                            </template>
                        </el-table-column>
                    </el-table>

                    <el-space wrap style="margin-bottom:16px;">
                        <el-button size="small" type="primary" plain :loading="eveningBriefDialog?.loading" @click="() => openEveningBrief(false)">生成晚间简报</el-button>
                        <el-button size="small" type="success" plain :loading="eveningBriefDialog?.loading" @click="() => openEveningBrief(true)">生成并推送晚报</el-button>
                        <el-button size="small" :loading="notifyLoading" @click="pushDepositDueNow">立即推送·存款到期</el-button>
                        <el-button size="small" :loading="notifyLoading" @click="pushDisciplineNow">立即推送·纪律摘要</el-button>
                    </el-space>

                    <div style="margin:8px 0;font-weight:600;">最近 20 条发送日志</div>
                    <el-table :data="notifyLogs" size="small" style="width:100%;" empty-text="暂无发送记录" max-height="320">
                        <el-table-column prop="created_at" label="时间" width="160"></el-table-column>
                        <el-table-column prop="event" label="事件" width="110"></el-table-column>
                        <el-table-column prop="channel" label="通道" width="90"></el-table-column>
                        <el-table-column prop="title" label="标题" width="120" show-overflow-tooltip></el-table-column>
                        <el-table-column label="结果" width="80">
                            <template #default="s">
                                <el-tag :type="s.row.ok ? 'success' : 'danger'" size="small">{{ s.row.ok ? '成功' : '失败' }}</el-tag>
                            </template>
                        </el-table-column>
                        <el-table-column prop="reason" label="原因" min-width="140" show-overflow-tooltip></el-table-column>
                    </el-table>
                </el-card>

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
                        <el-descriptions-item label="最近备份时间">{{ latestBackupText }}</el-descriptions-item>
                        <el-descriptions-item label="备份数量">{{ maintenanceStatus.backup_count || backups.length || 0 }}</el-descriptions-item>
                        <el-descriptions-item label="建议">操作前先「创建备份」并下载一份到本地</el-descriptions-item>
                    </el-descriptions>
                    <el-alert
                        title="恢复数据库属于高风险操作：系统会先自动备份当前库，但仍建议先下载最新备份到电脑。恢复后会刷新首页/持仓/交易数据。"
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
import { computed } from 'vue';
import { useAppCtx } from '../composables/useAppCtx.js';

const {
    maintenanceStatus, backups, maintenanceLoading, latestBackupText,
    fetchMaintenance, createDbBackup, downloadBackup, restoreBackup, deleteBackup, restoreUploadedBackup,
    notifyStatus, notifyLogs, notifyLoading, notifyEventDraft,
    fetchNotifyPanel, saveNotifyPanel, testNotifyPush, pushDepositDueNow, pushDisciplineNow,
    eveningBriefDialog, openEveningBrief,
} = useAppCtx();

const CHANNEL_LABEL = {
    feishu: '飞书',
    dingtalk: '钉钉',
    wecom: '企业微信',
    telegram: 'Telegram',
};

const EVENT_LABEL = {
    price_alert: '价格预警',
    evening_brief: '晚间简报',
    deposit_due: '存款到期',
    discipline: '纪律破线',
    ops: '运维',
    test: '试推',
};

const channelRows = computed(() => {
    const ch = notifyStatus.value?.channels || {};
    return Object.keys(CHANNEL_LABEL).map((k) => ({
        key: k,
        name: CHANNEL_LABEL[k],
        configured: !!(ch[k] && ch[k].configured),
        hint: (ch[k] && ch[k].hint) || '—',
    }));
});

const eventRows = computed(() => {
    const keys = notifyStatus.value?.events?.length
        ? notifyStatus.value.events
        : Object.keys(EVENT_LABEL);
    return keys.map((event) => ({
        event,
        label: EVENT_LABEL[event] || event,
    }));
});
</script>
