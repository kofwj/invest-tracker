<template>
  <PageShell
    title="消息推送"
    subtitle="VPS 自有通道，独立于 Hermes。密钥在服务器 .env；这里管开关、事件、试推和日志。"
  >
    <template #actions>
      <el-space wrap>
        <el-button size="small" @click="fetchNotifyPanel" :loading="notifyLoading">刷新</el-button>
        <el-button size="small" type="success" plain :loading="notifyLoading" @click="testNotifyPush">试推一条</el-button>
        <el-button size="small" type="primary" :loading="notifyLoading" @click="saveNotifyPanel">保存设置</el-button>
      </el-space>
    </template>

    <div class="ledger-metrics cols-4">
      <MetricCard
        label="总开关"
        :value="notifyOn ? '已开启' : '已关闭'"
        :sub="notifyOn ? '会按事件推送' : '全部事件暂停'"
        :tone="notifyOn ? 'ok' : 'warn'"
        main
      />
      <MetricCard
        label="已配置通道"
        :value="`${configuredCount} / ${channelRows.length}`"
        :sub="configuredNames || '密钥在 .env'"
        :tone="configuredCount ? 'ok' : 'warn'"
      />
      <MetricCard
        label="正文模板"
        :value="templateLabel"
        sub="短=摘要 · 中=稍详"
      />
      <MetricCard
        label="同事件冷却"
        :value="`${Number(notifyStatus.cooldown_minutes || 0)} 分`"
        sub="防重复刷屏"
      />
    </div>

    <el-card shadow="never" class="ops-card">
      <template #header>
        <div class="ops-card-head">
          <div>
            <div class="ops-section-title">基础设置</div>
            <div class="ops-hint">改完点右上角「保存设置」才生效</div>
          </div>
        </div>
      </template>
      <el-row :gutter="16">
        <el-col :xs="24" :sm="8">
          <div class="ops-field-label">总开关</div>
          <el-switch v-model="notifyStatus.enabled" active-text="开" inactive-text="关" />
        </el-col>
        <el-col :xs="24" :sm="8">
          <div class="ops-field-label">正文模板</div>
          <el-radio-group v-model="notifyStatus.template" size="small">
            <el-radio-button label="short">短</el-radio-button>
            <el-radio-button label="medium">中</el-radio-button>
          </el-radio-group>
        </el-col>
        <el-col :xs="24" :sm="8">
          <div class="ops-field-label">同事件冷却（分钟）</div>
          <el-input-number
            v-model="notifyStatus.cooldown_minutes"
            :min="0"
            :max="10080"
            :step="30"
            size="small"
          />
        </el-col>
      </el-row>
    </el-card>

    <el-card shadow="never" class="ops-card">
      <template #header>
        <div class="ops-card-head">
          <div>
            <div class="ops-section-title">通道就绪</div>
            <div class="ops-hint">只显示是否配好；密钥不进网页</div>
          </div>
        </div>
      </template>
      <div class="channel-grid">
        <div
          v-for="row in channelRows"
          :key="row.key"
          class="channel-chip"
          :class="row.configured ? 'is-ok' : 'is-off'"
        >
          <div class="channel-name">{{ row.name }}</div>
          <el-tag :type="row.configured ? 'success' : 'info'" size="small" effect="light">
            {{ row.configured ? '已配置' : '未配置' }}
          </el-tag>
          <div class="channel-hint" :title="row.hint">{{ row.hint }}</div>
        </div>
      </div>
    </el-card>

    <el-card shadow="never" class="ops-card">
      <template #header>
        <div class="ops-card-head">
          <div>
            <div class="ops-section-title">事件 → 通道</div>
            <div class="ops-hint">逗号分隔：feishu,dingtalk,wecom,telegram</div>
          </div>
        </div>
      </template>
      <el-table :data="eventRows" size="small" style="width:100%;" empty-text="暂无事件">
        <el-table-column prop="label" label="事件" min-width="120" />
        <el-table-column prop="event" label="代码" width="120" />
        <el-table-column label="通道" min-width="240">
          <template #default="s">
            <el-input
              v-model="notifyEventDraft[s.row.event]"
              size="small"
              placeholder="例如 feishu,telegram"
            />
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="ops-card">
      <template #header>
        <div class="ops-card-head">
          <div>
            <div class="ops-section-title">立刻推一把</div>
            <div class="ops-hint">晚报会先弹窗预览；存款/纪律是强制检查后推</div>
          </div>
        </div>
      </template>
      <div class="ops-action-grid">
        <button type="button" class="ops-action" :disabled="eveningBriefDialog?.loading" @click="() => openEveningBrief(false)">
          <div class="ops-action-title">生成晚间简报</div>
          <div class="ops-action-sub">只预览，不推送</div>
        </button>
        <button type="button" class="ops-action is-primary" :disabled="eveningBriefDialog?.loading" @click="() => openEveningBrief(true)">
          <div class="ops-action-title">生成并推送晚报</div>
          <div class="ops-action-sub">预览后可再推</div>
        </button>
        <button type="button" class="ops-action" :disabled="notifyLoading" @click="pushDepositDueNow">
          <div class="ops-action-title">推送·存款到期</div>
          <div class="ops-action-sub">近 30 天到期项</div>
        </button>
        <button type="button" class="ops-action" :disabled="notifyLoading" @click="pushDisciplineNow">
          <div class="ops-action-title">推送·纪律摘要</div>
          <div class="ops-action-sub">破线/再平衡提醒</div>
        </button>
      </div>
    </el-card>

    <el-card shadow="never" class="ops-card">
      <template #header>
        <div class="ops-card-head">
          <div>
            <div class="ops-section-title">最近发送日志</div>
            <div class="ops-hint">最多 20 条 · 成功/失败一眼看</div>
          </div>
          <el-tag size="small" type="info">{{ notifyLogs.length }} 条</el-tag>
        </div>
      </template>
      <el-table :data="notifyLogs" size="small" style="width:100%;" empty-text="暂无发送记录" max-height="360">
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
import MetricCard from '../components/MetricCard.vue';
import { computed } from 'vue';
import { useAppCtx } from '../composables/useAppCtx.js';

const {
  notifyStatus, notifyLogs, notifyLoading, notifyEventDraft,
  fetchNotifyPanel, saveNotifyPanel, testNotifyPush, pushDepositDueNow, pushDisciplineNow,
  eveningBriefDialog, openEveningBrief,
} = useAppCtx();

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

const channelRows = computed(() => {
  const ch = notifyStatus.value?.channels || {};
  return Object.keys(CHANNEL_LABEL).map((k) => ({
    key: k,
    name: CHANNEL_LABEL[k],
    configured: !!(ch[k] && ch[k].configured),
    hint: (ch[k] && ch[k].hint) || '—',
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
const templateLabel = computed(() => {
  const t = notifyStatus.value?.template || 'medium';
  return t === 'short' ? '短' : '中';
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
.ops-field-label {
  margin-bottom: 8px;
  font-size: 13px;
  color: var(--app-muted);
  font-weight: 600;
}
.channel-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}
.channel-chip {
  min-width: 0;
  border: 1px solid var(--app-border);
  border-radius: 12px;
  padding: 12px;
  background: color-mix(in srgb, var(--app-surface) 94%, var(--app-bg0));
}
.channel-chip.is-ok {
  border-color: color-mix(in srgb, #16a34a 28%, var(--app-border));
  background: color-mix(in srgb, #16a34a 6%, var(--app-surface));
}
.channel-name {
  font-size: 14px;
  font-weight: 700;
  color: var(--app-text);
  margin-bottom: 8px;
}
.channel-hint {
  margin-top: 8px;
  font-size: 12px;
  color: var(--app-soft);
  line-height: 1.4;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
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
  .channel-grid,
  .ops-action-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 560px) {
  .channel-grid,
  .ops-action-grid { grid-template-columns: 1fr; }
}
</style>
