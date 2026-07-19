import { ref } from 'vue';
import { ElMessage } from 'element-plus';
import api from '../api/index.js';
import { apiErrorDetail } from '../utils/index.js';

/**
 * Evening brief dialog helpers.
 * GET 只读预览；推送走 POST /evening-brief/notify（避免 GET 副作用）。
 */
export function createBriefHelpers() {
    const eveningBriefDialog = ref({ visible: false, text: '', loading: false });

    const openEveningBrief = async (notify = false) => {
        eveningBriefDialog.value.loading = true;
        try {
            const res = notify
                ? await api.eveningBriefNotify()
                : await api.eveningBrief();
            eveningBriefDialog.value.text = res.data?.text || '';
            eveningBriefDialog.value.visible = true;
            if (notify) {
                const n = res.data?.notify || {};
                if (n.sent) {
                    ElMessage.success('已推送（多通道）');
                } else if (n.reason === 'no_webhook' || n.reason === 'skipped') {
                    ElMessage.warning('未配置通知通道，仅本地预览');
                } else if (n.reason) {
                    ElMessage.warning('推送未成功：' + n.reason);
                }
            }
        } catch (e) {
            ElMessage.error(apiErrorDetail(e) || '简报失败');
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
