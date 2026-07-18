import api from '../api/index.js';
import { ElMessage, ElMessageBox } from 'element-plus';
import { formatMoney, daysUntil } from '../utils/index.js';

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
        return [...deposits.value]
            .map(d => {
                const amount = Number(d.amount || 0);
                const rate = Number(d.interest_rate || 0);
                return {
                    ...d,
                    amount,
                    interest_rate: rate,
                    annual_interest: amount * rate / 100,
                    percentage: total > 0 ? amount / total * 100 : 0,
                    daysLeft: daysUntil(d.due_date)
                };
            })
            .sort((a, b) => {
                if (a.daysLeft === null && b.daysLeft === null) return 0;
                if (a.daysLeft === null) return 1;
                if (b.daysLeft === null) return -1;
                return a.daysLeft - b.daysLeft;
            });
    });

    const depositSummary = computed(() => {
        const rows = depositRows.value;
        const total = rows.reduce((sum, d) => sum + d.amount, 0);
        const annualInterest = rows.reduce((sum, d) => sum + d.annual_interest, 0);
        const weightedRate = total > 0 ? annualInterest / total * 100 : 0;
        const nextDue = rows.find(d => d.daysLeft !== null && d.daysLeft >= 0) || null;
        return { total, annualInterest, weightedRate, count: rows.length, nextDue };
    });

    const depositBankBreakdown = computed(() => {
        const map = {};
        depositRows.value.forEach(d => {
            const key = d.bank_name || '未命名';
            map[key] = (map[key] || 0) + d.amount;
        });
        const total = depositSummary.value.total;
        return Object.keys(map)
            .map(bank_name => ({ bank_name, amount: map[bank_name], percentage: total > 0 ? map[bank_name] / total * 100 : 0 }))
            .sort((a, b) => b.amount - a.amount);
    });

    const depositMaturityBuckets = computed(() => {
        const buckets = [
            { bucket: '30天内', amount: 0 },
            { bucket: '31-90天', amount: 0 },
            { bucket: '91-180天', amount: 0 },
            { bucket: '180天以上', amount: 0 },
            { bucket: '未设置到期', amount: 0 }
        ];
        depositRows.value.forEach(d => {
            const days = d.daysLeft;
            if (days === null) buckets[4].amount += d.amount;
            else if (days <= 30) buckets[0].amount += d.amount;
            else if (days <= 90) buckets[1].amount += d.amount;
            else if (days <= 180) buckets[2].amount += d.amount;
            else buckets[3].amount += d.amount;
        });
        const total = depositSummary.value.total;
        return buckets.map(b => ({ ...b, percentage: total > 0 ? b.amount / total * 100 : 0 }));
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
