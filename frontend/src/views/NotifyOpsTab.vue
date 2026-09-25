<template>
  <PageShell>
    <template #actions>
      <el-space wrap>
        <el-button size="small" @click="fetchNotifyPanel" :loading="notifyLoading">刷新</el-button>
        <el-button size="small" type="primary" :loading="notifyLoading" @click="onSaveNotifyPanel">保存设置</el-button>
      </el-space>
    </template>

    <!-- 状态带：这页只回答「会不会推 / 推到哪 / 上次成不成」 -->
    <div class="app-stat-row cols-4" aria-label="消息推送状态速览">
      <div class="app-stat-cell">
        <div class="k">总开关</div>
        <div class="v" :class="notifyOn ? 'ok' : 'warn'">{{ notifyOn ? '已开启' : '已关闭' }}</div>
        <div class="s">改完点右上角「保存设置」才生效</div>
      </div>
      <div class="app-stat-cell">
        <div class="k">已配置通道</div>
        <div class="v" :class="configuredCount ? 'ok' : 'warn'">{{ `${configuredCount} / ${channelRows.length}` }}</div>
        <div class="s">{{ configuredNames || '还没有可用通道，先在下面填凭据' }}</div>
      </div>
      <div class="app-stat-cell">
        <div class="k">上次发送</div>
        <div class="v" :class="lastLog ? (lastLog.ok ? 'ok' : 'warn') : 'muted'">
          {{ lastLog ? (lastLog.ok ? '成功' : '失败') : '暂无记录' }}
        </div>
        <div class="s">{{ lastSendText || '还没有发送记录' }}</div>
      </div>
      <div class="app-stat-cell">
        <div class="k">同事件冷却</div>
        <div class="v">{{ `${Number(notifyStatus.cooldown_minutes || 0)} 分` }}</div>
        <div class="s">正文模板：{{ templateLabel }} · 事件映射 {{ eventRows.length }} 条</div>
      </div>
    </div>

    <!-- Q1 要不要推、推得吵不吵 -->
    <el-card shadow="never" class="ops-card">
      <template #header>
        <div class="ops-card-head">
          <div>
            <div class="ops-section-title"><span class="ops-q">Q1</span>通知与开关</div>
            <div class="ops-hint">总开关、正文模板、飞书模式、同事件冷却。改完点右上角「保存设置」才生效。</div>
          </div>
        </div>
      </template>
      <el-form label-position="top">
        <div class="field-grid">
          <div class="field">
            <div class="field-label">总开关</div>
            <div class="field-row">
              <el-switch v-model="notifyStatus.enabled" active-text="开" inactive-text="关" />
            </div>
            <div class="ops-hint">关掉后所有通道都停（事件映射与凭据保留）。</div>
          </div>
          <div class="field">
            <div class="field-label">正文模板</div>
            <div class="field-row">
              <el-radio-group v-model="notifyStatus.template" size="small">
                <el-radio-button label="short">短</el-radio-button>
                <el-radio-button label="medium">中</el-radio-button>
              </el-radio-group>
            </div>
            <div class="ops-hint">短＝一行结论；中＝带数值明细。当前值：{{ notifyStatus.template || 'medium' }}</div>
          </div>
          <div class="field">
            <div class="field-label">同事件冷却（分钟）</div>
            <div class="field-row">
              <el-input-number
                v-model="notifyStatus.cooldown_minutes"
                :min="0"
                :max="10080"
                :step="30"
                size="small"
              />
            </div>
            <div class="ops-hint">同一事件在这段时间内只推一条；0＝不冷却。</div>
          </div>
          <div class="field">
            <div class="field-label">飞书模式</div>
            <div class="field-row">
              <el-radio-group v-model="feishuMode" size="small">
                <el-radio-button label="webhook">Webhook</el-radio-button>
                <el-radio-button label="app">自建应用</el-radio-button>
              </el-radio-group>
            </div>
            <div class="ops-hint">选了自建应用就忽略 Webhook（下面「飞书」组的字段跟着切）。</div>
          </div>
        </div>
      </el-form>
    </el-card>

    <!-- Q2 推到哪些通道（4 组凭据） -->
    <el-card shadow="never" class="ops-card">
      <template #header>
        <div class="ops-card-head">
          <div>
            <div class="ops-section-title">通知渠道</div>
            <div class="ops-hint">
              配了哪个通道就发哪个，也可以同时用；点渠道行展开填凭据。本页填写优先，留空不改；
              勾「清除已存凭据」会删掉库里的值（保存前再确认一次，仍可用 .env 兜底）。
            </div>
          </div>
          <span class="ops-card-actions">
            <el-button size="small" :loading="notifyLoading" @click="onTestNotifyPush">发送测试</el-button>
            <el-tag size="small" :type="configuredCount ? 'success' : 'info'" effect="light">
              已配置 {{ configuredCount }} / {{ channelRows.length }}
            </el-tag>
          </span>
        </div>
      </template>
      <el-form label-position="top" class="cred-form">
        <div
          v-for="row in channelRows"
          :key="row.key"
          class="chan"
          :class="row.configured ? '' : 'is-off'"
        >
          <div
            class="chan-head"
            role="button"
            tabindex="0"
            :aria-expanded="chanOpen(row.key) ? 'true' : 'false'"
            @click="toggleChan(row.key)"
            @keydown.enter.prevent="toggleChan(row.key)"
            @keydown.space.prevent="toggleChan(row.key)"
          >
            <span class="chan-chev" :class="{ 'is-open': chanOpen(row.key) }" aria-hidden="true">›</span>
            <span class="chan-name">{{ row.name }}</span>
            <span v-if="row.key === 'feishu'" class="chan-mode">{{ feishuMode === 'app' ? '自建应用' : 'Webhook' }}</span>
            <span class="chan-hint">{{ row.hint || '—' }}</span>
            <span class="chan-tools" @click.stop>
              <el-button size="small" :loading="notifyLoading" @click="onTestChannel(row.key)">测试</el-button>
              <el-tag :type="row.configured ? 'success' : 'info'" size="small" effect="light">
                {{ row.configured ? (row.sourceLabel || '已配置') : '未配置' }}
              </el-tag>
            </span>
          </div>

          <!-- 飞书：Webhook 模式 / 自建应用模式字段二选一 -->
          <div v-if="chanOpen(row.key) && row.key === 'feishu'" class="field-grid">
            <div v-if="feishuMode === 'webhook'" class="field">
              <div class="field-label">
                {{ fieldLabel('feishu_webhook') }}
                <span v-if="flagOf('feishu_webhook')" class="cred-flag">库里已有</span>
              </div>
              <el-input
                v-model="notifyChannelDraft.feishu_webhook"
                type="password"
                show-password
                clearable
                placeholder="飞书机器人 Webhook"
                :disabled="notifyChannelClear.feishu_webhook"
              />
              <div class="ops-hint">https://open.feishu.cn/open-apis/bot/v2/hook/…</div>
            </div>
            <template v-else>
              <div class="field">
                <div class="field-label">
                  {{ fieldLabel('feishu_app_id') }}
                  <span v-if="flagOf('feishu_app_id')" class="cred-flag">库里已有</span>
                </div>
                <el-input
                  v-model="notifyChannelDraft.feishu_app_id"
                  type="password"
                  show-password
                  clearable
                  placeholder="例如 cli_xxx"
                  :disabled="notifyChannelClear.feishu_app_id"
                />
                <div class="ops-hint">开放平台「凭证与基础信息」里的 App ID。</div>
              </div>
              <div class="field">
                <div class="field-label">
                  {{ fieldLabel('feishu_app_secret') }}
                  <span v-if="flagOf('feishu_app_secret')" class="cred-flag">库里已有</span>
                </div>
                <el-input
                  v-model="notifyChannelDraft.feishu_app_secret"
                  type="password"
                  show-password
                  clearable
                  placeholder="应用密钥"
                  :disabled="notifyChannelClear.feishu_app_secret"
                />
                <div class="ops-hint">只在服务端使用，界面只回显打码值。</div>
              </div>
              <div class="field">
                <div class="field-label">
                  {{ fieldLabel('feishu_open_id') }}
                  <span v-if="flagOf('feishu_open_id')" class="cred-flag">库里已有</span>
                </div>
                <el-input
                  v-model="notifyChannelDraft.feishu_open_id"
                  clearable
                  placeholder="自己/群的 Open ID（开放平台获取）"
                  :disabled="notifyChannelClear.feishu_open_id"
                />
                <div class="ops-hint">开放平台给的 ou_xxx / oc_xxx；自建应用必须填收件人。</div>
              </div>
            </template>
          </div>

          <!-- 钉钉：Webhook + 加签密钥 -->
          <div v-else-if="chanOpen(row.key) && row.key === 'dingtalk'" class="field-grid">
            <div class="field">
              <div class="field-label">
                {{ fieldLabel('dingtalk_webhook') }}
                <span v-if="flagOf('dingtalk_webhook')" class="cred-flag">库里已有</span>
              </div>
              <el-input
                v-model="notifyChannelDraft.dingtalk_webhook"
                type="password"
                show-password
                clearable
                placeholder="钉钉机器人 Webhook"
                :disabled="notifyChannelClear.dingtalk_webhook"
              />
              <div class="ops-hint">https://oapi.dingtalk.com/robot/send?access_token=…</div>
            </div>
            <div class="field">
              <div class="field-label">
                {{ fieldLabel('dingtalk_secret') }}
                <span v-if="flagOf('dingtalk_secret')" class="cred-flag">库里已有</span>
              </div>
              <el-input
                v-model="notifyChannelDraft.dingtalk_secret"
                type="password"
                show-password
                clearable
                placeholder="钉钉加签密钥（可选）"
                :disabled="notifyChannelClear.dingtalk_secret"
              />
              <div class="ops-hint">安全设置选了「加签」才需要填。</div>
            </div>
          </div>

          <!-- 企业微信：Webhook -->
          <div v-else-if="chanOpen(row.key) && row.key === 'wecom'" class="field-grid">
            <div class="field">
              <div class="field-label">
                {{ fieldLabel('wecom_webhook') }}
                <span v-if="flagOf('wecom_webhook')" class="cred-flag">库里已有</span>
              </div>
              <el-input
                v-model="notifyChannelDraft.wecom_webhook"
                type="password"
                show-password
                clearable
                placeholder="企业微信群机器人 Webhook"
                :disabled="notifyChannelClear.wecom_webhook"
              />
              <div class="ops-hint">https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=…</div>
            </div>
          </div>

          <!-- Telegram：Token + Chat ID -->
          <div v-else-if="chanOpen(row.key)" class="field-grid">
            <div class="field">
              <div class="field-label">
                {{ fieldLabel('telegram_bot_token') }}
                <span v-if="flagOf('telegram_bot_token')" class="cred-flag">库里已有</span>
              </div>
              <el-input
                v-model="notifyChannelDraft.telegram_bot_token"
                type="password"
                show-password
                clearable
                placeholder="Telegram Bot Token"
                :disabled="notifyChannelClear.telegram_bot_token"
              />
              <div class="ops-hint">@BotFather 建机器人时给的那串 token。</div>
            </div>
            <div class="field">
              <div class="field-label">
                {{ fieldLabel('telegram_chat_id') }}
                <span v-if="flagOf('telegram_chat_id')" class="cred-flag">库里已有</span>
              </div>
              <el-input
                v-model="notifyChannelDraft.telegram_chat_id"
                clearable
                placeholder="Telegram Chat ID"
                :disabled="notifyChannelClear.telegram_chat_id"
              />
              <div class="ops-hint">私聊是正数，群组是 -100… 开头的负数。</div>
            </div>
          </div>
        </div>
      </el-form>

      <!-- 危险操作单独成组：9 项「清除已存」集中在这里，勾选后对应输入框锁定 -->
      <div class="hazard">
        <div class="hazard-head">
          <el-tag size="small" type="danger" effect="light">危险操作</el-tag>
          <strong>清除已存凭据</strong>
          <div class="hazard-hint">勾选后点右上角「保存设置」会删掉库里的值（保存前会再确认一次），不可撤销；.env 里还有的话仍会兜底。</div>
        </div>
        <div class="hazard-grid">
          <el-checkbox v-model="notifyChannelClear.feishu_webhook">清除 飞书 Webhook</el-checkbox>
          <el-checkbox v-model="notifyChannelClear.feishu_app_id">清除 飞书 App ID</el-checkbox>
          <el-checkbox v-model="notifyChannelClear.feishu_app_secret">清除 飞书 App Secret</el-checkbox>
          <el-checkbox v-model="notifyChannelClear.feishu_open_id">清除 飞书 Open ID</el-checkbox>
          <el-checkbox v-model="notifyChannelClear.dingtalk_webhook">清除 钉钉 Webhook</el-checkbox>
          <el-checkbox v-model="notifyChannelClear.dingtalk_secret">清除 钉钉加签 Secret</el-checkbox>
          <el-checkbox v-model="notifyChannelClear.wecom_webhook">清除 企业微信 Webhook</el-checkbox>
          <el-checkbox v-model="notifyChannelClear.telegram_bot_token">清除 Telegram Token</el-checkbox>
          <el-checkbox v-model="notifyChannelClear.telegram_chat_id">清除 Telegram Chat ID</el-checkbox>
        </div>
        <p v-if="clearedCount" class="hazard-note">
          已勾选 {{ clearedCount }} 项：保存前会再确认一次「将从库里删除这几个凭据」，对应输入框同时锁定。
        </p>
      </div>
    </el-card>

    <!-- Q3 哪类事件推给哪些通道 -->
    <el-card shadow="never" class="ops-card">
      <template #header>
        <div class="ops-card-head">
          <div>
            <div class="ops-section-title"><span class="ops-q">Q3</span>哪类事件推给哪些通道</div>
            <div class="ops-hint">按事件勾通道；一个都不勾＝该事件不推。保存时仍写回原来的逗号分隔值（feishu,dingtalk,wecom,telegram）。</div>
          </div>
          <el-tag size="small" type="info" effect="light">事件映射 {{ eventRows.length }} 条</el-tag>
        </div>
      </template>
      <el-table :data="eventRows" size="small" style="width:100%;" empty-text="暂无事件" aria-label="推送事件通道配置">
        <el-table-column prop="label" label="事件" min-width="120" />
        <el-table-column prop="event" label="代码" width="120" />
        <el-table-column
          v-for="ch in MATRIX_CHANNELS"
          :key="ch"
          :label="CHANNEL_LABEL[ch]"
          width="86"
          align="center"
          header-align="center"
        >
          <template #default="s">
            <el-checkbox
              :model-value="eventChannels(s.row.event).includes(ch)"
              :aria-label="`${s.row.label} 推 ${CHANNEL_LABEL[ch]}`"
              @change="(v) => onToggleEventChannel(s.row.event, ch, v)"
            />
          </template>
        </el-table-column>
        <el-table-column label="原始值（保存时写回）" min-width="200" show-overflow-tooltip>
          <template #default="s">
            <span class="num-cell">{{ notifyEventDraft[s.row.event] || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Q4 手动推一把（一次性） -->
    <el-card shadow="never" class="ops-card">
      <template #header>
        <div class="ops-card-head">
          <div>
            <div class="ops-section-title"><span class="ops-q">Q4</span>手动推一把（一次性）</div>
            <div class="ops-hint">晚报会先弹窗预览；存款 / 纪律是强制检查后推。日常「试推一条」在右上角操作区。</div>
          </div>
        </div>
      </template>
      <div class="ops-action-grid">
        <button type="button" class="ops-action" :disabled="eveningBriefDialog?.loading" @click="() => onOpenEveningBrief(false)">
          <div class="ops-action-title">生成晚间简报</div>
          <div class="ops-action-sub">只预览，不推送</div>
        </button>
        <button type="button" class="ops-action is-primary" :disabled="eveningBriefDialog?.loading" @click="() => onOpenEveningBrief(true)">
          <div class="ops-action-title">生成并推送晚报</div>
          <div class="ops-action-sub">预览后可再推</div>
        </button>
        <button type="button" class="ops-action" :disabled="notifyLoading" @click="onPushDepositDue">
          <div class="ops-action-title">推送·存款到期</div>
          <div class="ops-action-sub">近 30 天到期项</div>
        </button>
        <button type="button" class="ops-action" :disabled="notifyLoading" @click="onPushDiscipline">
          <div class="ops-action-title">推送·纪律摘要</div>
          <div class="ops-action-sub">破线/再平衡提醒</div>
        </button>
      </div>
    </el-card>

    <!-- Q5 最近发送日志 -->
    <el-card shadow="never" class="ops-card">
      <template #header>
        <div class="ops-card-head">
          <div>
            <div class="ops-section-title"><span class="ops-q">Q5</span>最近发送日志</div>
            <div class="ops-hint">最多 20 条 · 成功 / 失败一眼看；失败那行的「原因」直接写清哪一步断了。</div>
          </div>
          <el-tag size="small" type="info" effect="light">{{ notifyLogs.length }} 条</el-tag>
        </div>
      </template>
      <el-table :data="notifyLogs" size="small" style="width:100%;" empty-text="暂无发送记录" max-height="360" aria-label="推送发送日志">
        <el-table-column prop="created_at" label="时间" width="160" />
        <el-table-column prop="event" label="事件" width="110" />
        <el-table-column prop="channel" label="通道" width="90" />
        <el-table-column prop="title" label="标题" min-width="120" show-overflow-tooltip />
        <el-table-column label="结果" width="80" align="center">
          <template #default="s">
            <el-tag :type="s.row.ok ? 'success' : 'danger'" size="small">{{ s.row.ok ? '成功' : '失败' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="reason" label="原因" min-width="140" show-overflow-tooltip />
      </el-table>
    </el-card>
  </PageShell>
</template>

<script setup>
import PageShell from '../components/PageShell.vue';
import { computed, ref, watch } from 'vue';
import { ElMessageBox } from 'element-plus';
import { useAppCtx } from '../composables/useAppCtx.js';

const {
  notifyStatus, notifyLogs, notifyLoading, notifyEventDraft,
  notifyChannelDraft, notifyChannelClear,
  fetchNotifyPanel, saveNotifyPanel, testNotifyPush, pushDepositDueNow, pushDisciplineNow,
  eveningBriefDialog, openEveningBrief,
} = useAppCtx();

// 写操作/推送防连点：模块里的 notifyLoading 在 saveNotifyPanel / testNotifyPush / push* 开头
// 就置位，这里补一层入口判断挡住同一 tick 的第二次点击；晚报推送用 eveningBriefDialog.loading。
async function onSaveNotifyPanel() {
  if (notifyLoading.value) return;
  // 破坏性操作（清除已存凭据）补一次二次确认：勾了才问，取消就不发保存请求。
  const cleared = CLEAR_FIELDS.filter((key) => notifyChannelClear.value?.[key]);
  if (cleared.length) {
    try {
      await ElMessageBox.confirm(
        `将从库里删除 ${cleared.length} 项已存凭据：${cleared.map((key) => FIELD_LABEL[key]).join('、')}。删除后不可撤销；.env 里还有的话仍会兜底。`,
        '清除已存凭据',
        { type: 'warning' },
      );
    } catch {
      return;
    }
  }
  await saveNotifyPanel();
}

async function onTestNotifyPush() {
  if (notifyLoading.value) return;
  await testNotifyPush();
}

async function onPushDepositDue() {
  if (notifyLoading.value) return;
  await pushDepositDueNow();
}

async function onPushDiscipline() {
  if (notifyLoading.value) return;
  await pushDisciplineNow();
}

async function onOpenEveningBrief(notify) {
  if (eveningBriefDialog.value?.loading) return;
  await openEveningBrief(notify);
}

const CHANNEL_LABEL = {
  feishu: '飞书',
  dingtalk: '钉钉',
  wecom: '企业微信',
  telegram: 'Telegram',
};

const EVENT_LABEL = {
  price_alert: '价格预警',
  evening_brief: '晚间简报',
  deposit_due: '存款到期',
  discipline: '纪律破线',
  ops: '运维',
  test: '试推',
};

const FIELD_LABEL = {
  feishu_webhook: '飞书 Webhook',
  feishu_app_id: '飞书自建应用 App ID',
  feishu_app_secret: '飞书自建应用 App Secret',
  feishu_open_id: '飞书接收人 Open ID',
  dingtalk_webhook: '钉钉 Webhook',
  dingtalk_secret: '钉钉加签 Secret',
  wecom_webhook: '企业微信 Webhook',
  telegram_bot_token: 'Telegram Bot Token',
  telegram_chat_id: 'Telegram Chat ID',
};

const SOURCE_LABEL = {
  db: '页面已存',
  env: '来自 .env',
};

// 事件 → 通道矩阵的列序（与保存写回的逗号分隔值同序）
const MATRIX_CHANNELS = ['feishu', 'dingtalk', 'wecom', 'telegram'];
// 可「清除已存」的凭据字段（与 notifyChannelClear 一一对应）
const CLEAR_FIELDS = [
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

const channelRows = computed(() => {
  const ch = notifyStatus.value?.channels || {};
  return Object.keys(CHANNEL_LABEL).map((k) => ({
    key: k,
    name: CHANNEL_LABEL[k],
    configured: !!(ch[k] && ch[k].configured),
    hint: (ch[k] && ch[k].hint) || '',
    sourceLabel: SOURCE_LABEL[(ch[k] && ch[k].source) || ''] || '',
  }));
});

const eventRows = computed(() => {
  const keys = notifyStatus.value?.events?.length
    ? notifyStatus.value.events
    : Object.keys(EVENT_LABEL);
  return keys.map((event) => ({
    event,
    label: EVENT_LABEL[event] || event,
  }));
});

const notifyOn = computed(() => !!notifyStatus.value?.enabled);
const configuredCount = computed(() => channelRows.value.filter((r) => r.configured).length);
const configuredNames = computed(() => {
  const names = channelRows.value.filter((r) => r.configured).map((r) => r.name);
  return names.length ? names.join(' · ') : '';
});

// 渠道行默认收起（参考图 idiom）：行头常驻「已配置 / 未配置」胶囊，展开才编辑凭据
const openChans = ref({});
const chanOpen = (key) => !!openChans.value[key];
function toggleChan(key) {
  openChans.value = { ...openChans.value, [key]: !openChans.value[key] };
}
// 按渠道试推：复用 maintenanceHelpers 的 testNotifyPush（新增可选 channels 参数）
async function onTestChannel(key) {
  if (notifyLoading.value) return;
  await testNotifyPush([key]);
}
const templateLabel = computed(() => {
  const t = notifyStatus.value?.template || 'medium';
  return t === 'short' ? '短' : '中';
});

// 状态带格 3：上一条的「时间 · 事件 → 通道」（没有日志就留空，模板里回退成占位文案）
const lastLog = computed(() => {
  const rows = notifyLogs?.value ?? notifyLogs;
  return Array.isArray(rows) ? rows[0] || null : null;
});
const lastSendText = computed(() => {
  const row = lastLog.value;
  if (!row) return '';
  return [
    row.created_at,
    EVENT_LABEL[row.event] || row.event,
    CHANNEL_LABEL[row.channel] || row.channel,
  ].filter(Boolean).join(' · ');
});

// 危险区：已勾选「清除」的项数（只在页面上提示影响面，保存逻辑仍在模块里）
const clearedCount = computed(() => CLEAR_FIELDS.filter((key) => notifyChannelClear.value?.[key]).length);

function fieldLabel(key) {
  return FIELD_LABEL[key] || key;
}
function flagOf(key) {
  return !!(notifyStatus.value?.credential_flags && notifyStatus.value.credential_flags[key]);
}

// 事件 → 通道矩阵：勾选后写回同一份逗号分隔草稿（字段类型不变），未知取值原样保留在末尾
function eventChannels(event) {
  return String((notifyEventDraft.value || {})[event] || '')
    .split(',')
    .map((x) => x.trim())
    .filter(Boolean);
}
function onToggleEventChannel(event, channel, checked) {
  const picked = eventChannels(event).filter((k) => k !== channel);
  if (checked) picked.push(channel);
  const ordered = MATRIX_CHANNELS.filter((k) => picked.includes(k));
  const extra = picked.filter((k) => !MATRIX_CHANNELS.includes(k));
  notifyEventDraft.value[event] = ordered.concat(extra).join(',');
}

// 飞书模式：有 app_id 就用自建应用，否则 Webhook
// 飞书模式：本地可写选择器，初始跟随当前已存配置。
const feishuMode = ref('webhook');
watch(
  () => notifyStatus.value?.channels?.feishu?.mode,
  (m) => { feishuMode.value = m === 'app' ? 'app' : 'webhook'; },
  { immediate: true },
);
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
.cred-form { margin-top: 4px; }
.cred-flag {
  color: var(--app-ok, #3d9a5f);
  font-weight: 600;
}
.ops-action-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}
.ops-action {
  text-align: left;
  border: 1px solid var(--app-border);
  border-radius: 12px;
  background: color-mix(in srgb, var(--app-surface) 94%, var(--app-bg0));
  padding: 14px 14px 12px;
  cursor: pointer;
  font-family: inherit;
  color: inherit;
  transition: border-color .15s ease, background .15s ease, box-shadow .15s ease;
}
.ops-action:hover:not(:disabled) {
  border-color: color-mix(in srgb, var(--app-primary) 35%, var(--app-border));
  box-shadow: var(--app-shadow-sm);
}
.ops-action:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.ops-action.is-primary {
  border-color: color-mix(in srgb, var(--app-primary) 28%, var(--app-border));
  background:
    linear-gradient(135deg, var(--app-primary-soft), transparent 50%),
    var(--app-surface);
}
.ops-action-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--app-text);
}
.ops-action-sub {
  margin-top: 4px;
  font-size: 12px;
  color: var(--app-soft);
  line-height: 1.4;
}
@media (max-width: 960px) {
  .ops-action-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 560px) {
  .ops-action-grid { grid-template-columns: 1fr; }
}

/* —— 参考图 idiom：卡片更轻、渠道行可折叠、输入框更高 —— */
.ops-card {
  border: 1px solid var(--app-hairline);
  border-radius: 12px;
  box-shadow: none;
}
.ops-card + .ops-card { margin-top: 16px; }
.chan {
  border: 1px solid var(--app-hairline);
  border-radius: 12px;
  box-shadow: none;
}
.chan-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 0;
  padding: 12px 14px;
  border-radius: 10px;
  cursor: pointer;
  user-select: none;
  transition: background .15s ease;
}
.chan-head:hover { background: color-mix(in srgb, var(--app-bg0) 45%, transparent); }
.chan-head:focus-visible { outline: 2px solid var(--app-primary); outline-offset: 2px; }
.chan-chev {
  width: 14px;
  font-size: 16px;
  line-height: 1;
  color: var(--app-soft);
  transition: transform .15s ease;
}
.chan-chev.is-open { transform: rotate(90deg); }
.chan-tools { display: flex; align-items: center; gap: 8px; margin-left: auto; }
.chan .field-grid { padding: 0 14px 14px; }
.ops-card :deep(.el-card__body) { padding: 18px 20px; }
.ops-card :deep(.el-input__wrapper) { min-height: 40px; }
@media (max-width: 768px) {
  .chan-hint { max-width: 100%; }
  .chan-tools { margin-left: 0; width: 100%; justify-content: flex-end; }
}
</style>
