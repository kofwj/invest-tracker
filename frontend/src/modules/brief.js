import { ref } from 'vue';
import { ElMessage } from 'element-plus';
import api from '../api/index.js';

/**
 * Evening brief dialog helpers.
 * Extracted small dialog open function + state.
 */
export function createBriefHelpers() {
    const eveningBriefDialog = {
        visible: false,
        text: '',
        loading: false,
    };

    const openEveningBrief = async (notify = false) => {
        eveningBriefDialog.value.loading = true;
        try {
            const res = await api.eveningBrief(!!notify);
            eveningBriefDialog.value.text = res.data?.text || '';
            eveningBriefDialog.value.visible = true;
            if (notify && res.data?.notify?.sent) {
                ElMessage.success('已推送飞书');
            } else if (notify && res.data?.notify?.reason === 'no_webhook') {
                ElMessage.warning('未配置 FEISHU_ALERT_WEBHOOK，仅本地预览');
            }
        } catch (e) {
            ElMessage.error(e?.response?.data?.detail || e?.message || '简报失败');
        } finally {
            eveningBriefDialog.value.loading = false;
        }
    };

    return {
        eveningBriefDialog,
        openEveningBrief,
    };
}

export default createBriefHelpers;
