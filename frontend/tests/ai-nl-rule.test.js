/**
 * A5 自然语言建规则（`/ai/nl-rule`）前端侧的行为。
 *
 * 关键点：AI 只把草稿**填进既有规则表单并打开对话框** —— 落库仍要用户点对话框里的「保存」
 * （走既有 POST /market/alert-rules），所以这里断言"只改表单、不发保存请求"。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ref } from 'vue';

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), alert: vi.fn() },
}));

const apiMock = vi.hoisted(() => ({ nlRule: vi.fn(), createAlertRule: vi.fn() }));
vi.mock('../src/api/index.js', () => ({ default: apiMock }));

import { createMarketModule } from '../src/modules/market.js';

function buildModule() {
  const alertForm = ref({
    target_type: 'holding',
    rule_type: 'price',
    code: '',
    name: '',
    condition: 'above',
    threshold: 0,
    enabled: true,
  });
  const alertEditDialog = ref(false);
  const mod = createMarketModule({
    marketSummary: ref({}),
    alertRules: ref([]),
    alertEvents: ref([]),
    marketLoading: ref(false),
    alertChecking: ref(false),
    alertEventsLoading: ref(false),
    alertForm,
    alertEditDialog,
    triggeredAlerts: ref([]),
    alertEventCodeFilter: ref(''),
    alertEventStartDate: ref(''),
    alertEventEndDate: ref(''),
    watchlistDraft: ref([]),
    watchlistSaving: ref(false),
  });
  return { mod, alertForm, alertEditDialog };
}

beforeEach(() => {
  apiMock.nlRule.mockReset();
  apiMock.createAlertRule.mockReset();
});

describe('一句话建规则：草稿 → 规则表单', () => {
  it('预填规则表单并打开对话框，且**不**调用保存接口', async () => {
    const { mod, alertForm, alertEditDialog } = buildModule();
    apiMock.nlRule.mockResolvedValue({
      data: {
        ok: true,
        mode: 'ok',
        draft: {
          target_type: 'holding',
          code: '000651',
          name: '格力电器',
          rule_type: 'price',
          condition: 'below',
          threshold: 60,
        },
      },
    });

    const data = await mod.parseNlRule('格力跌到 60 块提醒我');

    expect(apiMock.nlRule).toHaveBeenCalledWith('格力跌到 60 块提醒我');
    expect(data.ok).toBe(true);
    expect(alertForm.value.code).toBe('000651');
    expect(alertForm.value.name).toBe('格力电器');
    expect(alertForm.value.condition).toBe('below');
    expect(alertForm.value.threshold).toBe(60);
    expect(alertForm.value.id).toBeUndefined(); // 新建，不是编辑既有规则
    expect(alertEditDialog.value).toBe(true);
    expect(apiMock.createAlertRule).not.toHaveBeenCalled();
  });

  it('组合规则（归一后的 portfolio_pnl + 负阈值）也能照填', async () => {
    const { mod, alertForm } = buildModule();
    apiMock.nlRule.mockResolvedValue({
      data: {
        ok: true,
        mode: 'ok',
        draft: {
          target_type: 'portfolio',
          code: 'PORTFOLIO',
          name: '组合当日盈亏',
          rule_type: 'portfolio_pnl',
          condition: 'below',
          threshold: -2,
        },
      },
    });

    await mod.parseNlRule('组合跌 2% 提醒我');

    expect(alertForm.value.target_type).toBe('portfolio');
    expect(alertForm.value.rule_type).toBe('portfolio_pnl');
    expect(alertForm.value.threshold).toBe(-2);
  });

  it('没听懂（ok=false）时不动表单、不开对话框', async () => {
    const { mod, alertForm, alertEditDialog } = buildModule();
    apiMock.nlRule.mockResolvedValue({
      data: { ok: false, mode: 'invalid_rule', reason: 'invalid_rule', detail: '阈值越界', draft: null },
    });

    await mod.parseNlRule('随便说点什么');

    expect(alertForm.value.code).toBe('');
    expect(alertForm.value.threshold).toBe(0);
    expect(alertEditDialog.value).toBe(false);
  });

  it('空原话不发请求', async () => {
    const { mod, alertEditDialog } = buildModule();

    const data = await mod.parseNlRule('   ');

    expect(apiMock.nlRule).not.toHaveBeenCalled();
    expect(data.ok).toBe(false);
    expect(alertEditDialog.value).toBe(false);
  });
});
