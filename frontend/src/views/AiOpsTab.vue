<template>
  <PageShell>
    <template #actions>
      <el-space wrap>
        <el-button size="small" @click="loadStatus" :loading="loading">刷新</el-button>
        <el-button size="small" type="success" plain :loading="testing" @click="onTest">测试连接</el-button>
        <el-button size="small" type="primary" :loading="saving" @click="onSave">保存设置</el-button>
      </el-space>
    </template>

    <div class="app-stat-row cols-4" aria-label="AI 设置状态速览">
      <div class="app-stat-cell">
        <div class="k">总开关</div>
        <div class="v" :class="form.enabled ? 'ok' : 'warn'">{{ form.enabled ? '已开启' : '已关闭' }}</div>
        <div class="s">关掉后晚报 / 预警 / 规则都不调用，配置保留</div>
      </div>
      <div class="app-stat-cell">
        <div class="k">影子模式</div>
        <div class="v" :class="form.shadow_mode ? 'warn' : 'ok'">{{ form.shadow_mode ? '只记日志' : '正式拦截' }}</div>
        <div class="s">{{ form.shadow_mode ? '不拦截；关掉才是「正式拦截」' : '已按正式规则拦截' }}</div>
      </div>
      <div class="app-stat-cell">
        <div class="k">今日调用</div>
        <div class="v">{{ usageText }}</div>
        <div class="s">上限填 0＝不限；只数成功的正式调用</div>
      </div>
      <div class="app-stat-cell">
        <div class="k">密钥</div>
        <div class="v" :class="status.api_key_configured ? 'ok' : 'warn'">{{ status.api_key_configured ? '已配置' : '未配置' }}</div>
        <div class="s">{{ status.api_key_masked || '界面只回显打码值' }}</div>
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

    <!-- Q1 连到哪个模型 -->
    <el-card shadow="never" class="ops-card">
      <template #header>
        <div class="ops-card-head">
          <div>
            <div class="ops-section-title"><span class="ops-q">Q1</span>连到哪个模型</div>
            <div class="ops-hint">OpenAI 兼容 POST /v1/chat/completions；没写 /v1 会自动补。密钥留空表示不改，勾选「清除」才删掉已存密钥。</div>
          </div>
          <el-tag size="small" :type="status.api_key_configured ? 'success' : 'info'" effect="light">
            {{ status.api_key_configured ? '密钥已配置' : '未配置' }}
          </el-tag>
        </div>
      </template>
      <el-form label-position="top">
        <div class="field-grid">
          <div class="field">
            <div class="field-label">总开关</div>
            <div class="field-row">
              <el-switch v-model="form.enabled" active-text="开" inactive-text="关" />
            </div>
            <div class="ops-hint">关掉后晚报 / 预警 / 规则都不调用，配置保留。</div>
          </div>
          <div class="field">
            <div class="field-label">影子模式</div>
            <div class="field-row">
              <el-switch v-model="form.shadow_mode" active-text="开" inactive-text="关" />
            </div>
            <div class="ops-hint">
              {{ form.shadow_mode ? '只写审计日志、不拦截推送；确认效果后再关掉。' : '已按正式规则拦截；开启影子模式可先只记日志。' }}
            </div>
          </div>
          <div class="field">
            <div class="field-label">每日上限</div>
            <div class="field-row">
              <el-input-number v-model="form.daily_call_cap" :min="0" :max="10000" :step="1" />
            </div>
            <div class="ops-hint">0＝不限。只数当天成功且不是试推的调用（今天 {{ Number(status.today_used ?? status.today_calls ?? 0) }} 次）。</div>
          </div>
          <div class="field">
            <div class="field-label">超时（秒）</div>
            <div class="field-row">
              <el-input-number v-model="form.timeout_seconds" :min="1" :max="120" :step="1" />
            </div>
            <div class="ops-hint">1–120 秒；超时算失败并进审计日志。</div>
          </div>
          <div class="field">
            <div class="field-label">
              API Key
              <span v-if="status.api_key_configured" class="cred-flag">库里已有</span>
            </div>
            <el-input v-model="form.api_key" type="password" show-password clearable :placeholder="status.api_key_masked || '留空不改'" :disabled="clearApiKey" />
            <div class="ops-hint">只存库、不回明文；想删掉看下面的「危险操作」。</div>
          </div>
          <div class="field">
            <div class="field-label">模型</div>
            <div class="field-row">
              <el-select
                v-model="form.model"
                filterable
                default-first-option
                clearable
                placeholder="先拉取模型再选"
                style="min-width: 200px;"
              >
                <el-option v-for="m in modelOptions" :key="m" :label="m" :value="m" />
              </el-select>
              <el-button size="small" :loading="modelsLoading" @click="fetchModels()">拉取模型</el-button>
            </div>
            <div class="ops-hint">模型名要和供应方 /models 里的 id 完全一致（区分大小写、不能带空格）；先保存 base_url + 密钥再拉取</div>
            <div v-if="modelsHint" class="ops-hint" :class="{ 'ops-warn': !!modelsError || modelUnknown }">{{ modelsHint }}</div>
          </div>
          <div class="field span-2">
            <div class="field-label">Base URL</div>
            <div class="field-row">
              <el-input v-model="form.base_url" clearable placeholder="https://api.deepseek.com 或 …/v1" />
            </div>
            <div class="ops-hint">可写 …/v1 也可只写域名，没写 /v1 会自动补。</div>
          </div>
        </div>
      </el-form>

      <!-- 危险操作单独成组：清除已存密钥 -->
      <div class="hazard">
        <div class="hazard-head">
          <el-tag size="small" type="danger" effect="light">危险操作</el-tag>
          <strong>清除已存密钥</strong>
          <div class="hazard-hint">勾选后点右上角「保存设置」会先弹一次确认，确认后删掉库里的 AI 密钥；服务器 .env 里的 AI_API_KEY 还能兜底，但页面里配的地址 + 模型会立刻用不了。</div>
        </div>
        <div class="hazard-body">
          <el-checkbox v-model="clearApiKey">清除已存密钥</el-checkbox>
        </div>
        <p v-if="clearApiKey" class="hazard-note">
          已勾选：保存时会先确认「确定清除库里已有的 AI 密钥？」，上面的 API Key 输入框同时锁定。
        </p>
      </div>
    </el-card>

    <!-- Q2 哪些用例允许调用 -->
    <el-card shadow="never" class="ops-card">
      <template #header>
        <div class="ops-card-head">
          <div>
            <div class="ops-section-title"><span class="ops-q">Q2</span>哪些用例允许调用</div>
            <div class="ops-hint">先配底座；真正接晚报 / 预警 / 自然语言规则是后面的包。用例关闭时后端返回 feature_disabled，不发请求。</div>
          </div>
          <el-tag size="small" type="info" effect="light">已开 {{ enabledFeatureCount }} / 3</el-tag>
        </div>
      </template>
      <div class="use-grid">
        <div class="use-card">
          <el-switch v-model="form.features.brief" aria-label="晚报 brief 开关" />
          <span class="use-card-txt">
            <span class="use-card-title">晚报 brief</span>
            <span class="use-card-hint">晚间简报正文用 AI 生成。{{ form.features.brief ? '已开启' : '未开启' }}。</span>
          </span>
        </div>
        <div class="use-card">
          <el-switch v-model="form.features.alert_note" aria-label="预警附言开关" />
          <span class="use-card-txt">
            <span class="use-card-title">预警附言</span>
            <span class="use-card-hint">价格预警后面附一句解读。{{ form.features.alert_note ? '已开启' : '未开启' }}。</span>
          </span>
        </div>
        <div class="use-card">
          <el-switch v-model="form.features.nl_rule" aria-label="自然语言规则开关" />
          <span class="use-card-txt">
            <span class="use-card-title">自然语言规则</span>
            <span class="use-card-hint">把自然语言描述翻成纪律规则。{{ form.features.nl_rule ? '已开启' : '未开启' }}。</span>
          </span>
        </div>
      </div>
    </el-card>

    <!-- Q3 最近一次连接测试 -->
    <el-card v-if="lastTest" shadow="never" class="ops-card">
      <template #header>
        <div class="ops-card-head">
          <div>
            <div class="ops-section-title"><span class="ops-q">Q3</span>最近一次连接测试</div>
            <div class="ops-hint">看真实请求 URL，base_url 拼错一眼能看出来。</div>
          </div>
          <el-tag size="small" :type="lastTest.ok ? 'success' : 'danger'" effect="light">{{ lastTest.ok ? '成功' : '失败' }}</el-tag>
        </div>
      </template>
      <div class="app-brief cols-3">
        <div class="app-brief-cell">
          <div class="k">结果</div>
          <div class="v" :class="lastTest.ok ? 'ok' : 'warn'">{{ lastTest.ok ? '成功' : ('失败 ' + (lastTest.reason || '')) }}</div>
        </div>
        <div class="app-brief-cell">
          <div class="k">耗时</div>
          <div class="v">{{ lastTest.duration_ms || 0 }} ms</div>
        </div>
        <div class="app-brief-cell">
          <div class="k">HTTP</div>
          <div class="v">{{ lastTest.status == null ? '—' : lastTest.status }}</div>
        </div>
      </div>
      <div v-if="lastTest.provider_error" class="ops-hint ops-warn">供应方原文：{{ lastTest.provider_error }}</div>
      <div class="ops-hint">真实请求 URL</div>
      <div class="ops-url">{{ lastTest.request_url || '（未配置 base_url）' }}</div>
    </el-card>

    <!-- Q4 最近调用（审计） -->
    <el-card shadow="never" class="ops-card">
      <template #header>
        <div class="ops-card-head">
          <div>
            <div class="ops-section-title"><span class="ops-q">Q4</span>最近调用（审计）</div>
            <div class="ops-hint">最多 10 条，不含密钥；失败的写清原因，方便对账「今天到底烧了几次」。</div>
          </div>
          <el-tag size="small" type="info" effect="light">{{ (status.recent || []).length }} 条</el-tag>
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
import { ElMessage, ElMessageBox } from 'element-plus';
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
// 状态带 / Q2 卡头「已开 n / 3」（只做展示计数，不改三个开关本身）
const enabledFeatureCount = computed(
  () => [form.features.brief, form.features.alert_note, form.features.nl_rule].filter(Boolean).length,
);
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
// 拉取结果（原始列表）与「当前值」分开：已保存的模型名永远能在下拉里选到，
// 即使拉取失败或它已从供应方下线（见下面 modelOptions）。
const fetchedModels = ref([]);
const modelsError = ref('');

const modelOptions = computed(() => [...new Set([...fetchedModels.value, form.model].filter(Boolean))]);

// 「当前值不在供应方列表里」只跟拉取结果比，不能拿 modelOptions 比（那个一定包含当前值）
const modelUnknown = computed(
  () => !!form.model && fetchedModels.value.length > 0 && !fetchedModels.value.includes(form.model),
);
const modelsHint = computed(() => {
  if (modelsError.value) return `拉取模型失败：${modelsError.value}`;
  if (!fetchedModels.value.length) return '';
  if (modelUnknown.value) {
    return `已拉取 ${fetchedModels.value.length} 个模型，但当前填的「${form.model}」不在列表里 —— 供应方会按 model_not_found 处理`;
  }
  return `已拉取 ${fetchedModels.value.length} 个模型`;
});

// silent=true：进页面自动拉取时不弹「已拉取 N 个模型」的成功提示；失败仍然提示。
async function fetchModels({ silent = false } = {}) {
  if (modelsLoading.value) return;
  modelsLoading.value = true;
  modelsError.value = '';
  try {
    const { data } = await api.getAiModels();
    fetchedModels.value = Array.isArray(data?.ids) ? data.ids : [];
    if (!data?.ok) {
      modelsError.value = data?.error || `HTTP ${data?.status}`;
      ElMessage.error('拉取模型失败：' + modelsError.value);
    } else if (!silent) {
      ElMessage.success(`已拉取 ${fetchedModels.value.length} 个模型`);
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
    // 破坏性操作（清除已存密钥）补一次二次确认：勾了才问，取消就不发保存请求。
    if (clearApiKey.value) {
      try {
        await ElMessageBox.confirm(
          '确定清除库里已有的 AI 密钥？\n1）清除后三个用例都无法调用，直到重新填入密钥\n2）审计日志与用量统计不受影响\n3）服务器 .env 里有 AI_API_KEY 时仍会兜底',
          '清除已存 AI 密钥',
          { type: 'warning' },
        );
      } catch {
        return;
      }
    }
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
  // 进页面静默拉一次模型列表：不弹成功提示，失败仍提示（hint 里也留供应方 error）
  fetchModels({ silent: true });
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
  font-family: "SF Mono", Menlo, Consolas, ui-monospace, monospace;
  font-variant-numeric: tabular-nums;
}
.cred-flag {
  color: var(--app-ok, #3d9a5f);
  font-weight: 600;
}
/* —— 参考图 idiom：卡片更轻、输入框更高（与消息推送页同一套，.chan-* 是推送页专属不在此列） —— */
.ops-card {
  border: 1px solid var(--app-hairline);
  border-radius: 12px;
  box-shadow: none;
}
.ops-card + .ops-card { margin-top: 16px; }
.ops-card :deep(.el-card__body) { padding: 18px 20px; }
.ops-card :deep(.el-input__wrapper) { min-height: 40px; }
</style>
