import { ElMessage, ElMessageBox } from 'element-plus';
import api from '../api/index.js';

/**
 * Holding correction + expected return helpers.
 * Extracted from main.js to keep the root setup slimmer.
 */
export function createHoldingCorrectionHelpers({
    expectedReturnDialog,
    holdingCorrectionDialog,
    holdingCorrectionHistoryDialog,
    fetchData,
    todayLocalIso,
}) {
    const openExpectedReturnDialog = (row) => {
        expectedReturnDialog.value = {
            visible: true,
            form: {
                code: row.code,
                name: row.name,
                expected_return: row.expected_return ?? 0,
            },
        };
    };

    const saveExpectedReturn = async () => {
        try {
            const code = expectedReturnDialog.value.form.code;
            const expected_return = expectedReturnDialog.value.form.expected_return;
            await api.updateExpectedReturn(code, expected_return);
            ElMessage.success('更新成功');
            expectedReturnDialog.value.visible = false;
            if (typeof fetchData === 'function') {
                await fetchData();
            }
        } catch (e) {
            ElMessage.error('更新失败');
        }
    };

    const openHoldingCorrectionDialog = (row) => {
        holdingCorrectionDialog.value = {
            visible: true,
            current: { ...row },
            form: {
                date: typeof todayLocalIso === 'function' ? todayLocalIso() : todayLocalIso,
                code: row.code,
                name: row.name,
                category: row.category || '',
                actual_quantity: Number(row.quantity || 0),
                actual_avg_cost: Number(row.avg_cost || 0),
                actual_total_dividend: Number(row.total_dividend || 0),
                remark: '按券商持仓页面强制校正',
            },
        };
    };

    const saveHoldingCorrection = async () => {
        try {
            const f = holdingCorrectionDialog.value.form;
            if (!f.date || !f.code) {
                return ElMessage.warning('校正日期和代码不能为空');
            }
            await api.addHoldingCorrection(f);
            ElMessage.success('持仓校正已保存，并已重新计算持仓');
            holdingCorrectionDialog.value.visible = false;
            if (typeof fetchData === 'function') {
                await fetchData();
            }
        } catch (e) {
            ElMessage.error(e?.response?.data?.detail || '保存持仓校正失败');
        }
    };

    const openHoldingCorrectionHistory = async (row) => {
        try {
            const res = await api.listHoldingCorrections(row.code);
            holdingCorrectionHistoryDialog.value = {
                visible: true,
                title: `${row.name} (${row.code}) 持仓校正记录`,
                records: res.data || [],
            };
        } catch (e) {
            ElMessage.error('获取校正记录失败');
        }
    };

    const deleteHoldingCorrection = async (row) => {
        try {
            await ElMessageBox.confirm(
                `确定删除 ${row.date} ${row.code} 的持仓校正？删除后会按交易记录重新计算。`,
                '确认删除',
                { type: 'warning' }
            );
            await api.deleteHoldingCorrection(row.id);
            ElMessage.success('校正记录已删除，并已重新计算持仓');
            if (holdingCorrectionHistoryDialog.value.records) {
                holdingCorrectionHistoryDialog.value.records = holdingCorrectionHistoryDialog.value.records.filter(
                    (x) => x.id !== row.id
                );
            }
            if (typeof fetchData === 'function') {
                await fetchData();
            }
        } catch (e) {
            // user cancelled or error already handled by confirm
        }
    };

    return {
        openExpectedReturnDialog,
        saveExpectedReturn,
        openHoldingCorrectionDialog,
        saveHoldingCorrection,
        openHoldingCorrectionHistory,
        deleteHoldingCorrection,
    };
}
