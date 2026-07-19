import { ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import api from '../api/index.js';
import { apiErrorDetail } from '../utils/index.js';

export function createMaintenanceHelpers({
    maintenanceStatus,
    backups,
    maintenanceLoading,
    fetchData,
    fetchSnapshots,
    queryTransactions,
    API,
}) {
    const notifyStatus = ref({
        enabled: true,
        template: 'medium',
        cooldown_minutes: 240,
        channels: {},
        event_channels: {},
        events: [],
        channel_keys: [],
    });
    const notifyLogs = ref([]);
    const notifyLoading = ref(false);
    const notifyEventDraft = ref({});

    const fetchMaintenance = async () => {
        try {
            const [statusRes, backupsRes] = await Promise.all([api.maintenanceStatus(), api.listBackups()]);
            maintenanceStatus.value = statusRes.data || {};
            backups.value = backupsRes.data || [];
        } catch (e) {
            console.error('获取维护状态失败', e);
        }
    };

    const fetchNotifyPanel = async () => {
        try {
            const [st, logs] = await Promise.all([
                api.getNotifyStatus(),
                api.listNotifyLogs(20),
            ]);
            notifyStatus.value = st.data || {};
            notifyEventDraft.value = { ...(st.data?.event_channels || {}) };
            notifyLogs.value = logs.data?.items || [];
        } catch (e) {
            console.error('获取通知配置失败', e);
        }
    };

    const saveNotifyPanel = async () => {
        notifyLoading.value = true;
        try {
            const res = await api.saveNotifySettings({
                enabled: !!notifyStatus.value.enabled,
                cooldown_minutes: Number(notifyStatus.value.cooldown_minutes || 240),
                template: notifyStatus.value.template || 'medium',
                event_channels: notifyEventDraft.value,
            });
            notifyStatus.value = res.data || notifyStatus.value;
            notifyEventDraft.value = { ...(res.data?.event_channels || {}) };
            ElMessage.success('通知设置已保存');
            await fetchNotifyPanel();
        } catch (e) {
            ElMessage.error('保存通知设置失败：' + apiErrorDetail(e));
        } finally {
            notifyLoading.value = false;
        }
    };

    const testNotifyPush = async () => {
        notifyLoading.value = true;
        try {
            const res = await api.testNotify({
                title: '测试推送',
                text: '这是 invest-tracker 维护页发出的试推消息。',
                event: 'test',
                force: true,
            });
            const data = res.data || {};
            if (data.sent) ElMessage.success('试推已发出（至少一个通道成功）');
            else ElMessage.warning('试推未成功：' + (data.reason || '请检查通道配置'));
            await fetchNotifyPanel();
        } catch (e) {
            ElMessage.error('试推失败：' + apiErrorDetail(e));
        } finally {
            notifyLoading.value = false;
        }
    };

    const pushDepositDueNow = async () => {
        notifyLoading.value = true;
        try {
            const res = await api.pushNotifyDepositDue(true);
            const data = res.data || {};
            if (data.sent) ElMessage.success('存款到期提醒已推送');
            else ElMessage.info(data.reason === 'nothing_due' ? '近 30 天无到期项（已强制检查）' : ('未推送：' + (data.reason || '')));
            await fetchNotifyPanel();
        } catch (e) {
            ElMessage.error('存款到期推送失败：' + apiErrorDetail(e));
        } finally {
            notifyLoading.value = false;
        }
    };

    const pushDisciplineNow = async () => {
        notifyLoading.value = true;
        try {
            const res = await api.pushNotifyDiscipline(true);
            const data = res.data || {};
            if (data.sent) ElMessage.success('纪律摘要已推送');
            else ElMessage.info('未推送：' + (data.reason || '无破线或通道未配置'));
            await fetchNotifyPanel();
        } catch (e) {
            ElMessage.error('纪律推送失败：' + apiErrorDetail(e));
        } finally {
            notifyLoading.value = false;
        }
    };

    const createDbBackup = async () => {
        maintenanceLoading.value = true;
        try {
            const res = await api.createBackup();
            ElMessage.success(`备份已创建：${res.data?.filename || ''}`);
            await fetchMaintenance();
        } catch (e) {
            ElMessage.error('创建备份失败：' + apiErrorDetail(e));
        } finally {
            maintenanceLoading.value = false;
        }
    };

    const downloadBackup = async (row) => {
        if (!row?.filename) return;
        try {
            const res = await api.download(
                `/maintenance/backups/${encodeURIComponent(row.filename)}/download`,
            );
            const blobUrl = window.URL.createObjectURL(new Blob([res.data], { type: 'application/octet-stream' }));
            const link = document.createElement('a');
            link.href = blobUrl;
            link.download = row.filename;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            window.URL.revokeObjectURL(blobUrl);
        } catch (e) {
            ElMessage.error('下载备份失败：' + apiErrorDetail(e));
        }
    };

    const restoreBackup = async (row) => {
        if (!row?.filename) return;
        try {
            await ElMessageBox.confirm(
                `确定恢复备份 ${row.filename}？\\n\\n1）会先自动备份当前数据库\\n2）恢复后当前账本数据会被替换\\n3）建议先点「下载」留一份到本地\\n\\n请再次确认操作人就是你本人。`,
                '恢复数据库（高风险）',
                { type: 'warning', confirmButtonText: '仍要恢复', cancelButtonText: '取消' },
            );
            maintenanceLoading.value = true;
            const res = await api.restoreBackup(row.filename);
            ElMessage.success(`恢复完成，恢复前备份：${res.data?.pre_restore_backup || ''}`);
            await Promise.all([fetchData(), fetchSnapshots(), queryTransactions(), fetchMaintenance()]);
        } catch (e) {
            if (e === 'cancel') return;
            ElMessage.error('恢复备份失败：' + apiErrorDetail(e));
        } finally {
            maintenanceLoading.value = false;
        }
    };

    const deleteBackup = async (row) => {
        if (!row?.filename) return;
        try {
            await ElMessageBox.confirm(`确定删除备份 ${row.filename}？删除后无法从系统内恢复。`, '删除备份', { type: 'warning' });
            maintenanceLoading.value = true;
            await api.deleteBackup(row.filename);
            ElMessage.success(`备份已删除：${row.filename}`);
            await fetchMaintenance();
        } catch (e) {
            if (e === 'cancel') return;
            ElMessage.error('删除备份失败：' + apiErrorDetail(e));
        } finally {
            maintenanceLoading.value = false;
        }
    };

    const restoreUploadedBackup = async (file) => {
        const raw = file?.raw || file;
        if (!raw) return;
        try {
            await ElMessageBox.confirm(`确定上传并恢复备份 ${raw.name}？系统会先自动备份当前数据库。`, '上传备份并恢复', { type: 'warning' });
            maintenanceLoading.value = true;
            const fd = new FormData();
            fd.append('file', raw);
            const res = await api.restoreUploadedBackup(fd);
            ElMessage.success(`恢复完成，恢复前备份：${res.data?.pre_restore_backup || ''}`);
            await Promise.all([fetchData(), fetchSnapshots(), queryTransactions(), fetchMaintenance()]);
        } catch (e) {
            if (e === 'cancel') return;
            ElMessage.error('上传恢复失败：' + apiErrorDetail(e));
        } finally {
            maintenanceLoading.value = false;
        }
    };

    return {
        fetchMaintenance,
        createDbBackup,
        downloadBackup,
        restoreBackup,
        deleteBackup,
        restoreUploadedBackup,
        notifyStatus,
        notifyLogs,
        notifyLoading,
        notifyEventDraft,
        fetchNotifyPanel,
        saveNotifyPanel,
        testNotifyPush,
        pushDepositDueNow,
        pushDisciplineNow,
    };
}
