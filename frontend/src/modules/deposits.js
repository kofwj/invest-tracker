import api from '../api/index.js';
import { ElMessage, ElMessageBox } from 'element-plus';
import { formatMoney } from '../utils/index.js';

const createDepositsModule = ({ depositDialog, fetchData }) => {
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

    return { openDepositDialog, saveDeposit, deleteDeposit };
};

export { createDepositsModule };
export default createDepositsModule;
