<template>
  <PageShell>
    <template #actions>
      <el-space wrap>
        <el-button size="small" @click="loadStatus" :loading="loading">刷新</el-button>
        <el-button size="small" type="success" plain :loading="testing" @click="onTest">测试连接</el-button>
        <el-button size="small" type="primary" :loading="saving" @click="onSave">保存设置</el-button>
      </el-space>
    </template>

    <div class="app-stat-row cols-4">
      <div class="app-stat-cell">
        <div class="k">总开关</div>
        <div class="v" :class="form.enabled ? 'ok' : 'warn'">{{ form.enabled ? '已开启' : '已关闭' }}</div>
      </div>
      <div class="app-stat-cell">
        <div class="k">影子模式</div>
        <div class="v" :class="form.shadow_mode ? 'warn' : 'ok'">{{ form.shadow_mode ? '只记日志' : '正式拦截' }}</div>
      </div>
      <div class="app-stat-cell">
        <div class="k">今日调用</div>
        <div class="v">{{ usageText }}</div>
      </div>
      <div class="app-stat-cell">
        <div class="k">密钥</div>
        <div class="v" :class="status.api_key_configured ? 'ok' : 'warn'">{{ status.api_key_configured ? '已配置' : '未配置' }}</div>
      </div>
    </div>

    <el-alert
      v-if="status.last_error"
      :title="'最近失败：' + status.last_error"
      type="warning"
      show-icon
      :closable="false"
      style="margin-bottom: 14px;"
    />

    <el-card shadow="never" class="ops-card">
      <template #header>
        <div class="ops-card-head">
          <div>
            <div class="ops-section-title">连接</div>
            <div class="ops-hint">OpenAI 兼容 POST /v1/chat/completions；没写 /v1 会自动补。密钥留空表示不改，勾选「清除」才删掉已存密钥。</div>
          </div>
        </div>
      </template>
      <el-form label-position="top">
        <el-row :gutter="16">
          <el-col :xs="24" :sm="8">
            <el-form-item label="总开关">
              <el-switch v-model="form.enabled" active-text="开" inactive-text="关" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="8">
            <el-form-item label="影子模式">
              <el-switch v-model="form.shadow_mode" active-text="开" inactive-text="关" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="8">
            <el-form-item label="每日上限">
              <el-input-number v-model="form.daily_call_cap" :min="0" :max="10000" :step="1" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :md="12">
            <el-form-item label="Base URL">
              <el-input v-model="form.base_url" clearable placeholder="https://api.deepseek.com 或 …/v1" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :md="12">
            <el-form-item label="模型">
              <el-space wrap>
                <el-select
                  v-model="form.model"
                  filterable
                  allow-create
                  default-first-option
                  clearable
                  placeholder="deepseek-chat"
                  style="min-width: 200px;"
                >
                  <el-option v-for="m in modelOptions" :key="m" :label="m" :value="m" />
                </el-select>
                <el-button size="small" :loading="modelsLoading" @click="fetchModels">拉取模型</el-button>
              </el-space>
              <div class="ops-hint">模型名要和供应方 /models 里的 id 完全一致（区分大小写、不能带空格）；先保存 base_url + 密钥再拉取</div>
              <div v-if="modelsHint" class="ops-hint" :class="{ 'ops-warn': !!modelsError || modelUnknown }">{{ modelsHint }}</div>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :md="12">
            <el-form-item label="API Key">
              <el-input v-model="form.api_key" type="password" show-password clearable :placeholder="status.api_key_masked || '留空不改'" :disabled="clearApiKey" />
              <el-checkbox v-model="clearApiKey" style="margin-top:6px;">清除已存密钥</el-checkbox>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :md="12">
            <el-form-item label="超时（秒）">
              <el-input-number v-model="form.timeout_seconds" :min="1" :max="120" :step="1" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </el-card>

    <el-card shadow="never" class="ops-card">
      <template #header>
        <div class="ops-card-head">
          <div>
            <div class="ops-section-title">用例开关</div>
            <div class="ops-hint">先配底座；真正接晚报/预警/自然语言规则是后面的包</div>
          </div>
        </div>
      </template>
      <el-space wrap>
        <el-switch v-model="form.features.brief" active-text="晚报 brief" />
        <el-switch v-model="form.features.alert_note" active-text="预警附言" />
        <el-switch v-model="form.features.nl_rule" active-text="自然语言规则" />
      </el-space>
    </el-card>

    <el-card v-if="lastTest" shadow="never" class="ops-card">
      <template #header>
        <div class="ops-card-head">
          <div>
            <div class="ops-section-title">最近一次连接测试</div>
            <div class="ops-hint">看真实请求 URL，base_url 拼错一眼能看出来</div>
          </div>
        </div>
      </template>
      <div class="ops-hint">{{ lastTest.ok ? '成功' : ('失败 ' + (lastTest.reason || '')) }} · {{ lastTest.duration_ms || 0 }} ms · HTTP {{ lastTest.status == null ? '—' : lastTest.status }}</div>
      <div v-if="lastTest.provider_error" class="ops-hint ops-warn">供应方原文：{{ lastTest.provider_error }}</div>
      <div class="ops-url">{{ lastTest.request_url || '（未配置 base_url）' }}</div>
    </el-card>

    <el-card shadow="never" class="ops-card">
      <template #header>
        <div class="ops-card-head">
          <div>
            <div class="ops-section-title">最近调用</div>
            <div class="ops-hint">最多 10 条，不含密钥</div>
          </div>
        </div>
      </template>
      <el-table :data="status.recent || []" size="small" style="width:100%;" empty-text="暂无调用" max-height="360" aria-label="AI 调用审计">
        <el-table-column prop="created_at" label="时间" width="170" />
        <el-table-column prop="feature" label="用例" width="110" />
        <el-table-column prop="model" label="模型" min-width="120" show-overflow-tooltip />
        <el-table-column label="结果" width="80" align="center">
          <template #default="s">
            <el-tag :type="s.row.ok ? 'success' : 'danger'" size="small">{{ s.row.ok ? '成功' : '失败' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="reason" label="原因" min-width="140" show-overflow-tooltip />
        <el-table-column prop="duration_ms" label="耗时" width="80" />
      </el-table>
    </el-card>
  </PageShell>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue';
import { ElMessage } from 'element-plus';
import PageShell from '../components/PageShell.vue';
import api from '../api/index.js';

const loading = ref(false);
const saving = ref(false);
const testing = ref(false);
const status = ref({});
const lastTest = ref(null);
const clearApiKey = ref(false);
const form = reactive({
  enabled: false,
  shadow_mode: true,
  base_url: '',
  model: '',
  api_key: '',
  timeout_seconds: 8,
  daily_call_cap: 30,
  features: { brief: false, alert_note: false, nl_rule: false },
});
const usageText = computed(() => {
  const used = Number(status.value.today_used ?? status.value.today_calls ?? 0);
  const cap = Number(form.daily_call_cap || 0);
  if (cap <= 0) return `${used} / 不限`;
  return `${used} / ${cap}`;
});
function applyStatus(data, { writeForm = true } = {}) {
  status.value = data || {};
  if (!writeForm) return;
  form.enabled = !!data.enabled;
  form.shadow_mode = data.shadow_mode !== false;
  form.base_url = data.base_url || '';
  form.model = data.model || '';
  form.api_key = '';
  form.timeout_seconds = Number(data.timeout_seconds || 8);
  form.daily_call_cap = Number(data.daily_call_cap || 0);
  form.features = {
    brief: !!(data.features && data.features.brief),
    alert_note: !!(data.features && data.features.alert_note),
    nl_rule: !!(data.features && data.features.nl_rule),
  };
  clearApiKey.value = false;
}

async function loadStatus({ writeForm = true } = {}) {
  if (loading.value) return;
  loading.value = true;
  try {
    const { data } = await api.getAiStatus();
    applyStatus(data, { writeForm });
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '读取 AI 配置失败');
  } finally {
    loading.value = false;
  }
}

const modelsLoading = ref(false);
const modelOptions = ref([]);
const modelsError = ref('');

const modelUnknown = computed(
  () => !!form.model && modelOptions.value.length > 0 && !modelOptions.value.includes(form.model),
);
const modelsHint = computed(() => {
  if (modelsError.value) return `拉取模型失败：${modelsError.value}`;
  if (!modelOptions.value.length) return '';
  if (modelUnknown.value) {
    return `已拉取 ${modelOptions.value.length} 个模型，但当前填的「${form.model}」不在列表里 —— 供应方会按 model_not_found 处理`;
  }
  return `已拉取 ${modelOptions.value.length} 个模型`;
});

async function fetchModels() {
  if (modelsLoading.value) return;
  modelsLoading.value = true;
  modelsError.value = '';
  try {
    const { data } = await api.getAiModels();
    modelOptions.value = Array.isArray(data?.ids) ? data.ids : [];
    if (!data?.ok) {
      modelsError.value = data?.error || `HTTP ${data?.status}`;
      ElMessage.error('拉取模型失败：' + modelsError.value);
    } else {
      ElMessage.success(`已拉取 ${modelOptions.value.length} 个模型`);
    }
  } catch (e) {
    modelsError.value = e?.response?.data?.detail || e?.message || '拉取失败';
    ElMessage.error('拉取模型失败：' + modelsError.value);
  } finally {
    modelsLoading.value = false;
  }
}

async function onSave() {
  if (saving.value) return;
  saving.value = true;
  try {
    const payload = {
      enabled: form.enabled,
      shadow_mode: form.shadow_mode,
      base_url: form.base_url,
      model: form.model,
      timeout_seconds: form.timeout_seconds,
      daily_call_cap: form.daily_call_cap,
      features: { ...form.features },
      clear_api_key: !!clearApiKey.value,
    };
    if (!clearApiKey.value && form.api_key) payload.api_key = form.api_key;
    const { data } = await api.saveAiConfig(payload);
    applyStatus(data);
    ElMessage.success('已保存');
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '保存失败');
  } finally {
    saving.value = false;
  }
}

async function onTest() {
  if (testing.value) return;
  testing.value = true;
  try {
    const { data } = await api.testAi();
    lastTest.value = data || {};
    if (data?.ok) ElMessage.success('连接成功');
    else ElMessage.warning(data?.reason || '连接失败');
    await loadStatus({ writeForm: false });
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '测试失败');
  } finally {
    testing.value = false;
  }
}

function onHeaderRefresh() {
  loadStatus();
}

onMounted(() => {
  loadStatus();
  window.addEventListener('invest-tab-refresh', onHeaderRefresh);
});
onUnmounted(() => {
  window.removeEventListener('invest-tab-refresh', onHeaderRefresh);
});
</script>

<style scoped>
.ops-card { margin-bottom: 14px; }
.ops-card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
  flex-wrap: wrap;
}
.ops-section-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--app-text);
}
.ops-hint {
  margin-top: 2px;
  font-size: 12px;
  color: var(--app-soft);
}
.ops-warn {
  color: var(--el-color-danger);
}
.ops-url {
  margin-top: 8px;
  font-size: 13px;
  word-break: break-all;
  color: var(--app-text);
}
</style>
