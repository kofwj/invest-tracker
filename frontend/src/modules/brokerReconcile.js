import { ElMessage, ElMessageBox } from 'element-plus';
import api from '../api/index.js';

const createBrokerReconcileModule = ({
    brokerResult,
    brokerLoading,
    brokerSelected,
    brokerAsOfDate,
    brokerCashInput,
    fetchData,
    showSyncNotice,
}) => {
    const statusLabel = (status) => {
        if (status === 'only_broker') return '仅券商有';
        if (status === 'only_app') return '仅系统有';
        if (status === 'mismatch') return '不一致';
        return status || '—';
    };

    const statusType = (status) => {
        if (status === 'match') return 'success';
        if (status === 'mismatch') return 'warning';
        if (status === 'only_broker') return 'danger';
        if (status === 'only_app') return 'info';
        return 'info';
    };

    async function onBrokerFileChange(uploadFile) {
        const raw = uploadFile?.raw;
        if (!raw) return;
        brokerLoading.value = true;
        try {
            const fd = new FormData();
            fd.append('file', raw);
            if (brokerAsOfDate.value) fd.append('as_of_date', brokerAsOfDate.value);
            if (brokerCashInput.value !== '' && brokerCashInput.value != null) {
                fd.append('broker_cash', String(brokerCashInput.value));
            }
            const res = await api.brokerReconcilePreview(fd);
            brokerResult.value = res.data || {};
            brokerSelected.value = [];
            const n = Number(brokerResult.value.diff_count || 0);
            if (n === 0) ElMessage.success(brokerResult.value.summary_text || '全部一致');
            else ElMessage.warning(brokerResult.value.summary_text || `发现 ${n} 处差异`);
        } catch (e) {
            brokerResult.value = null;
            ElMessage.error(e?.response?.data?.detail || e?.message || '解析失败');
        } finally {
            brokerLoading.value = false;
        }
    }

    function onBrokerSelectionChange(rows) {
        brokerSelected.value = rows || [];
    }

    function selectAllSuggestions() {
        const list = brokerResult.value?.suggestions || [];
        brokerSelected.value = [...list];
    }

    function clearBrokerSelection() {
        brokerSelected.value = [];
    }

    async function applySelectedCorrections() {
        const items = brokerSelected.value || [];
        if (!items.length) {
            ElMessage.warning('请先勾选要校正的行');
            return;
        }
        try {
            await ElMessageBox.confirm(
                `将按券商数据写入 ${items.length} 条持仓校正（会先自动备份）。校正后自动重扫差异。确定？`,
                '应用券商校正',
                { type: 'warning', confirmButtonText: '写入校正', cancelButtonText: '取消' }
            );
        } catch {
            return;
        }
        brokerLoading.value = true;
        try {
            const cashVal = brokerCashInput.value;
            const payload = {
                items: items.map((s) => ({
                    date: s.date,
                    code: s.code,
                    name: s.name,
                    category: s.category,
                    actual_quantity: s.actual_quantity,
                    actual_avg_cost: s.actual_avg_cost,
                    actual_total_dividend: s.actual_total_dividend || 0,
                    remark: s.remark || '券商对账单导入校正',
                })),
                broker_rows: brokerResult.value?.broker_rows || null,
                as_of_date: brokerAsOfDate.value || brokerResult.value?.as_of_date || null,
                broker_cash: cashVal !== '' && cashVal != null ? Number(cashVal) : (brokerResult.value?.broker_cash_input ?? null),
            };
            const res = await api.brokerReconcileApply(payload);
            const n = res.data?.applied_count ?? items.length;
            showSyncNotice?.(`已写入 ${n} 条持仓校正` + (res.data?.backup ? `（已备份）` : ''), 'success');
            ElMessage.success(`已写入 ${n} 条校正`);
            await fetchData?.();
            brokerSelected.value = [];
            if (res.data?.recheck) {
                brokerResult.value = {
                    ...brokerResult.value,
                    ...res.data.recheck,
                    parse: brokerResult.value?.parse,
                    filename: brokerResult.value?.filename,
                    broker_cash_input: payload.broker_cash,
                };
                const left = Number(res.data.recheck.diff_count || 0);
                if (left === 0) ElMessage.success(res.data.recheck.summary_text || '重扫：已全部一致');
                else ElMessage.warning(res.data.recheck.summary_text || `重扫后仍有 ${left} 处差异`);
            }
        } catch (e) {
            if (e !== 'cancel') {
                ElMessage.error(e?.response?.data?.detail || e?.message || '写入失败');
            }
        } finally {
            brokerLoading.value = false;
        }
    }

    return {
        statusLabel,
        statusType,
        onBrokerFileChange,
        onBrokerSelectionChange,
        selectAllSuggestions,
        clearBrokerSelection,
        applySelectedCorrections,
    };
};

export { createBrokerReconcileModule };
export default createBrokerReconcileModule;
