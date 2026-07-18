import { ElMessage, ElMessageBox } from 'element-plus';
import api from '../api/index.js';
import { apiErrorDetail } from '../utils/index.js';

export function createImportExportHelpers({ todayLocalIso, queryTransactions, fetchData, transQuery }) {
    const downloadFile = async (url, filename) => {
        try {
            const res = await api.download(url);
            const blobUrl = window.URL.createObjectURL(new Blob([res.data], { type: 'text/csv;charset=utf-8;' }));
            const link = document.createElement('a');
            link.href = blobUrl;
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            window.URL.revokeObjectURL(blobUrl);
        } catch (e) {
            ElMessage.error('下载失败：' + apiErrorDetail(e));
        }
    };

    const downloadTransactionsTemplate = () => downloadFile('/transactions/template', 'transactions_template.csv');
    const downloadDividendTemplate = () => downloadFile('/dividends/template', 'dividends_template.csv');
    const buildTransactionExportParams = () => {
        const q = transQuery.value || {};
        const params = { code: q.code || '', name: q.name || '', direction: q.direction || '' };
        if (q.dateRange && q.dateRange.length === 2) {
            params.start_date = q.dateRange[0];
            params.end_date = q.dateRange[1];
        }
        return params;
    };

    const exportTransactions = async () => {
        try {
            const res = await api.exportTransactions(buildTransactionExportParams());
            const blobUrl = window.URL.createObjectURL(new Blob([res.data], { type: 'text/csv;charset=utf-8;' }));
            const link = document.createElement('a');
            link.href = blobUrl;
            link.download = `transactions_${todayLocalIso()}.csv`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            window.URL.revokeObjectURL(blobUrl);
        } catch (e) {
            ElMessage.error('导出交易失败：' + apiErrorDetail(e));
        }
    };

    const downloadDepositsTemplate = () => downloadFile('/deposits/template', 'deposits_template.csv');
    const exportDeposits = () => downloadFile('/deposits/export', `deposits_${todayLocalIso()}.csv`);

    const uploadCsv = async (url, file, label, afterSuccess) => {
        const raw = file?.raw || file;
        if (!raw) return;
        if (!String(raw.name || '').toLowerCase().endsWith('.csv')) {
            return ElMessage.warning('请上传 CSV 文件');
        }
        try {
            await ElMessageBox.confirm(`确认导入 ${raw.name}？导入前系统会自动备份数据库，成功行会写入真实数据。`, `导入${label}`, { type: 'warning' });
            const fd = new FormData();
            fd.append('file', raw);
            const res = await api.uploadCsv(url, fd);
            const data = res.data || {};
            const errorText = data.failed
                ? `，失败 ${data.failed} 行：${(data.errors || []).slice(0, 3).map(e => `第${e.row}行 ${e.error}`).join('；')}`
                : '';
            ElMessage.success(`${label}导入完成：成功 ${data.imported || 0} 行${errorText}`);
            if (afterSuccess) await afterSuccess();
        } catch (e) {
            if (e === 'cancel') return;
            ElMessage.error(`${label}导入失败：` + apiErrorDetail(e));
        }
    };

    const importTransactions = (file) => uploadCsv('/transactions/import', file, '交易记录', async () => {
        await queryTransactions();
        await fetchData();
    });
    const importDeposits = (file) => uploadCsv('/deposits/import', file, '银行存款', async () => {
        await fetchData();
    });

    const importDividends = (file) => uploadCsv('/dividends/import', file, '分红记录', async () => {
        await fetchData();
        await queryTransactions();
    });

    return {
        downloadTransactionsTemplate,
        exportTransactions,
        importTransactions,
        downloadDepositsTemplate,
        exportDeposits,
        importDeposits,
        downloadDividendTemplate,
        importDividends,
    };
}
