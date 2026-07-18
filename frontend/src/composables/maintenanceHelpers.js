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
    const fetchMaintenance = async () => {
        try {
            const [statusRes, backupsRes] = await Promise.all([api.maintenanceStatus(), api.listBackups()]);
            maintenanceStatus.value = statusRes.data || {};
            backups.value = backupsRes.data || [];
        } catch (e) {
            console.error('获取维护状态失败', e);
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

    const downloadBackup = (row) => {
        if (!row?.filename) return;
        window.location.href = `${API}/maintenance/backups/${encodeURIComponent(row.filename)}/download`;
    };

    const restoreBackup = async (row) => {
        if (!row?.filename) return;
        try {
            await ElMessageBox.confirm(
                `确定恢复备份 ${row.filename}？\n\n1）会先自动备份当前数据库\n2）恢复后当前账本数据会被替换\n3）建议先点「下载」留一份到本地\n\n请再次确认操作人就是你本人。`,
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
    };
}
