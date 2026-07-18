import api from '../api/index.js';
import { ElMessage, ElMessageBox } from 'element-plus';
import { formatMoney } from '../utils/index.js';

const createDepositsModule = ({ depositDialog, deposits, fetchData, computed }) => {
    const openDepositDialog = (row) => {
        if (row) {
            depositDialog.value = {
                visible: true, isEdit: true, editId: row.id,
                form: { bank_name: row.bank_name, amount: row.amount, interest_rate: row.interest_rate || 0, due_date: row.due_date || '', remark: row.remark || '' },
            };
        } else {
            depositDialog.value = {
                visible: true, isEdit: false, editId: null,
                form: { bank_name: '', amount: 0, interest_rate: 0, due_date: '', remark: '' },
            };
        }
    };

    const saveDeposit = async () => {
        const f = depositDialog.value.form;
        try {
            if (depositDialog.value.isEdit) {
                await api.updateDeposit(depositDialog.value.editId, f);
                ElMessage.success('更新成功');
            } else {
                await api.addDeposit(f);
                ElMessage.success('新增成功');
            }
            depositDialog.value.visible = false;
            await fetchData();
        } catch (e) { ElMessage.error('操作失败'); }
    };

    const deleteDeposit = async (row) => {
        try {
            await ElMessageBox.confirm('确定删除 ' + row.bank_name + ' 的 ' + formatMoney(row.amount) + '？', '确认删除', { type: 'warning' });
            await api.deleteDeposit(row.id);
            ElMessage.success('已删除');
            await fetchData();
        } catch (e) { /* 用户取消 */ }
    };

    const depositRows = computed(() => {
        const total = deposits.value.reduce((sum, d) => sum + Number(d.amount || 0), 0);
        return deposits.value.map(d => ({
            ...d,
            amount: Number(d.amount || 0),
            interest_rate: Number(d.interest_rate || 0),
        })).sort((a, b) => String(b.due_date || '').localeCompare(String(a.due_date || '')));
    });

    const depositSummary = computed(() => {
        const rows = depositRows.value;
        const total = rows.reduce((s, r) => s + r.amount, 0);
        return { total, count: rows.length };
    });

    const depositBankBreakdown = computed(() => {
        const map = {};
        for (const d of deposits.value) {
            const bank = d.bank_name || '未知银行';
            if (!map[bank]) map[bank] = { bank, amount: 0, count: 0 };
            map[bank].amount += Number(d.amount || 0);
            map[bank].count += 1;
        }
        return Object.values(map).sort((a, b) => b.amount - a.amount);
    });

    const depositMaturityBuckets = computed(() => {
        const buckets = [
            { label: '7天内', days: 7, amount: 0 },
            { label: '30天内', days: 30, amount: 0 },
            { label: '90天内', days: 90, amount: 0 },
            { label: '其他', days: 9999, amount: 0 },
        ];
        const now = new Date();
        for (const d of deposits.value) {
            if (!d.due_date) {
                buckets[3].amount += Number(d.amount || 0);
                continue;
            }
            const due = new Date(d.due_date);
            const diffDays = Math.ceil((due - now) / (1000 * 3600 * 24));
            if (diffDays <= 7) buckets[0].amount += Number(d.amount || 0);
            else if (diffDays <= 30) buckets[1].amount += Number(d.amount || 0);
            else if (diffDays <= 90) buckets[2].amount += Number(d.amount || 0);
            else buckets[3].amount += Number(d.amount || 0);
        }
        return buckets;
    });

    return {
        openDepositDialog,
        saveDeposit,
        deleteDeposit,
        depositRows,
        depositSummary,
        depositBankBreakdown,
        depositMaturityBuckets,
    };
};

export { createDepositsModule };
export default createDepositsModule;
