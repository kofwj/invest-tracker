import { defineStore } from 'pinia';
import { ref } from 'vue';
import { ElMessage } from 'element-plus';
import api from '../api/index.js';
import { apiErrorDetail } from '../utils/index.js';

const emptyChannelDraft = () => ({
  feishu_webhook: '',
  feishu_app_id: '',
  feishu_app_secret: '',
  feishu_open_id: '',
  dingtalk_webhook: '',
  dingtalk_secret: '',
  wecom_webhook: '',
  telegram_bot_token: '',
  telegram_chat_id: '',
});

const emptyChannelClear = () => ({
  feishu_webhook: false,
  feishu_app_id: false,
  feishu_app_secret: false,
  feishu_open_id: false,
  dingtalk_webhook: false,
  dingtalk_secret: false,
  wecom_webhook: false,
  telegram_bot_token: false,
  telegram_chat_id: false,
});

export const useNotifyStore = defineStore('notify', () => {
  const notifyStatus = ref({
    enabled: true,
    template: 'medium',
    cooldown_minutes: 240,
    channels: {},
    event_channels: {},
    events: [],
    channel_keys: [],
    credential_flags: {},
    credential_fields: [],
  });
  const notifyLogs = ref([]);
  const notifyLoading = ref(false);
  const notifyEventDraft = ref({});
  const notifyChannelDraft = ref(emptyChannelDraft());
  const notifyChannelClear = ref(emptyChannelClear());
  const eveningBriefDialog = ref({ visible: false, text: '', loading: false });

  const fetchNotifyPanel = async () => {
    try {
      const [st, logs] = await Promise.all([
        api.getNotifyStatus(),
        api.listNotifyLogs(20),
      ]);
      notifyStatus.value = st.data || {};
      notifyEventDraft.value = { ...(st.data?.event_channels || {}) };
      // 不回填明文密钥；刷新后清空草稿
      notifyChannelDraft.value = emptyChannelDraft();
      notifyChannelClear.value = emptyChannelClear();
      notifyLogs.value = logs.data?.items || [];
    } catch (e) {
      console.error('获取通知配置失败', e);
    }
  };

  const buildChannelCredentialsPayload = () => {
    const payload = {};
    const draft = notifyChannelDraft.value || {};
    const clear = notifyChannelClear.value || {};
    const fields = [
      'feishu_webhook',
      'feishu_app_id',
      'feishu_app_secret',
      'feishu_open_id',
      'dingtalk_webhook',
      'dingtalk_secret',
      'wecom_webhook',
      'telegram_bot_token',
      'telegram_chat_id',
    ];
    fields.forEach((key) => {
      if (clear[key]) {
        payload[key] = '';
        return;
      }
      const val = String(draft[key] || '').trim();
      if (val) payload[key] = val;
    });
    return Object.keys(payload).length ? payload : null;
  };

  const saveNotifyPanel = async () => {
    notifyLoading.value = true;
    try {
      const channel_credentials = buildChannelCredentialsPayload();
      const body = {
        enabled: !!notifyStatus.value.enabled,
        cooldown_minutes: Number(notifyStatus.value.cooldown_minutes ?? 240),
        template: notifyStatus.value.template || 'medium',
        event_channels: notifyEventDraft.value,
      };
      if (channel_credentials) body.channel_credentials = channel_credentials;
      const res = await api.saveNotifySettings(body);
      notifyStatus.value = res.data || notifyStatus.value;
      notifyEventDraft.value = { ...(res.data?.event_channels || {}) };
      notifyChannelDraft.value = emptyChannelDraft();
      notifyChannelClear.value = emptyChannelClear();
      ElMessage.success('通知设置已保存');
      await fetchNotifyPanel();
    } catch (e) {
      ElMessage.error('保存通知设置失败：' + apiErrorDetail(e));
    } finally {
      notifyLoading.value = false;
    }
  };

  const testNotifyPush = async (channels) => {
    notifyLoading.value = true;
    try {
      const res = await api.testNotify({
        title: '测试推送',
        text: '这是 invest-tracker 设置页发出的试推消息。',
        event: 'test',
        force: true,
        channels: Array.isArray(channels) && channels.length ? channels : undefined,
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
    notifyStatus,
    notifyLogs,
    notifyLoading,
    notifyEventDraft,
    notifyChannelDraft,
    notifyChannelClear,
    eveningBriefDialog,
    openEveningBrief,
    fetchNotifyPanel,
    saveNotifyPanel,
    testNotifyPush,
    pushDepositDueNow,
    pushDisciplineNow,
  };
});
