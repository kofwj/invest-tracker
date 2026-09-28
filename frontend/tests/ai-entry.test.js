/**
 * N1 一句话记账（`/ai/nl-entry`）前端侧的行为。
 *
 * 为什么值得测：
 *  - 草稿只填字段、**不落库**——提交仍走「提交记录 → POST /transactions」，这里必须证明
 *    解析成功也不会自己调提交接口；
 *  - 影子模式必须"只记录、不生效"（与 A3 同语义）：草稿回来但不许写进表单，
 *    否则"先影子跑一周"这条红线在界面上就失效了；
 *  - 金额由「数量 × 单价」在本地算，AI 不给金额；日期不在原话里就保留表单默认的"今天"。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ref } from 'vue';
import { todayLocalIso } from '../src/utils/index.js';

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), alert: vi.fn() },
}));

const apiMock = vi.hoisted(() => ({ nlEntry: vi.fn() }));
vi.mock('../src/api/index.js', () => ({ default: apiMock }));
import { createTransactionsModule, nlEntryReasonText } from '../src/modules/transactions.js';

function buildModule() {
  const transForm = ref({
    date: '2026-09-26',
    code: '',
    name: '',
    category: '',
    account: '华泰证券',
    direction: '买入',
    quantity: 0,
    price: 0,
    amount: 0,
    fee: 0,
  });
  const mod = createTransactionsModule({
    activeTab: ref('transactions'),
    allTransactions: ref([]),
    filteredTransactions: ref([]),
    pendingTransactions: ref([]),
    pendingPurchaseTotal: ref(0),
    transDialog: ref({ visible: false }),
    transEditDialog: ref({ visible: false }),
    transForm,
    transQuery: ref({}),
    transPage: ref({ page: 1, pageSize: 10, total: 0 }),
    activeFeeAccount: ref('华泰证券'),
    feeAccounts: ref(['华泰证券']),
    feeManuallyEdited: ref(false),
    feeAutoHint: ref(''),
    holdings: ref([{ code: '510880', name: '红利ETF华泰柏瑞', category: 'ETF' }]),
    estimateFeeIfAuto: vi.fn(() => {
      // 诚实的费率桩：按金额算手续费，否则 applyEntryDraft 的
      // 「买入 +费 / 卖出 −费」对齐逻辑在测试里等于没跑。
      const amount = Number(transForm.value.amount || 0);
      transForm.value.fee = Math.round(amount * FEE_RATE * 100) / 100;
    }),
    fetchData: vi.fn(),
  });
  return { mod, transForm };
}

const draft = (over = {}) => ({
  code: '510880',
  name: '红利ETF华泰柏瑞',
  direction: '买入',
  date: null,
  quantity: 2000,
  price: 1.85,
  fee: null,
  ...over,
});

const FEE_RATE = 0.0003; // 3700 元 × 0.03% ≈ 1.11 元

beforeEach(() => {
  apiMock.nlEntry.mockReset();
});
describe('一句话记账草稿 → 表单', () => {
  it('字段落位：代码/名称/方向/数量/单价，金额本地按数量×单价算', () => {
    const { mod, transForm } = buildModule();

    mod.applyEntryDraftFields(transForm.value, draft());

    expect(transForm.value.code).toBe('510880');
    expect(transForm.value.name).toBe('红利ETF华泰柏瑞');
    expect(transForm.value.direction).toBe('买入');
    expect(transForm.value.quantity).toBe(2000);
    expect(transForm.value.price).toBe(1.85);
    expect(transForm.value.amount).toBe(3700);
  });

  it('原话没写日期（date=null）时补应用时区的"今天"，不沿用表单里被改过的旧日期', () => {
    const { mod, transForm } = buildModule();
    transForm.value.date = '2026-09-01'; // 用户手填改过、但还没提交

    mod.applyEntryDraftFields(transForm.value, draft({ date: null }));
    expect(transForm.value.date).toBe(todayLocalIso());

    mod.applyEntryDraftFields(transForm.value, draft({ date: '2026-09-25' }));
    expect(transForm.value.date).toBe('2026-09-25');
  });

  it('买入：总额 = 数量×单价 + 手续费（与提交前的反向校验同一口径）', async () => {
    const { mod, transForm } = buildModule();
    apiMock.nlEntry.mockResolvedValue({
      data: { ok: true, mode: 'ok', draft: draft(), shadow: false, warnings: [] },
    });

    await mod.parseNlEntry('1.85 买了 2000 份红利ETF');

    expect(transForm.value.fee).toBeCloseTo(1.11, 2);
    expect(transForm.value.amount).toBeCloseTo(3701.11, 2);
  });

  it('卖出：总额 = 数量×单价 − 手续费', async () => {
    const { mod, transForm } = buildModule();
    apiMock.nlEntry.mockResolvedValue({
      data: { ok: true, mode: 'ok', draft: draft({ direction: '卖出' }), shadow: false, warnings: [] },
    });

    await mod.parseNlEntry('1.85 卖了 2000 份红利ETF');

    expect(transForm.value.fee).toBeCloseTo(1.11, 2);
    expect(transForm.value.amount).toBeCloseTo(3698.89, 2);
  });

  it('非法数量/单价不覆盖已有表单值', () => {
    const { mod, transForm } = buildModule();
    transForm.value.quantity = 500;
    transForm.value.price = 3.5;

    mod.applyEntryDraftFields(transForm.value, draft({ quantity: 0, price: -1 }));

    expect(transForm.value.quantity).toBe(500);
    expect(transForm.value.price).toBe(3.5);
  });

  it('解析成功即填表，且**不**触碰提交接口（不落库）', async () => {
    const { mod, transForm } = buildModule();
    apiMock.nlEntry.mockResolvedValue({
      data: { ok: true, mode: 'ok', draft: draft(), shadow: false, warnings: [] },
    });

    const data = await mod.parseNlEntry('1.85 买了 2000 份红利ETF');

    expect(data.ok).toBe(true);
    expect(transForm.value.code).toBe('510880');
    expect(transForm.value.quantity).toBe(2000);
    // 模块不持有「提交」动作：入账只能由用户在页面上点「提交记录」
    expect(apiMock.nlEntry).toHaveBeenCalledTimes(1);
  });

  it('影子模式：草稿回来但不填表（只记录、不生效）', async () => {
    const { mod, transForm } = buildModule();
    apiMock.nlEntry.mockResolvedValue({
      data: { ok: true, mode: 'ok', draft: draft(), shadow: true, warnings: [] },
    });

    await mod.parseNlEntry('1.85 买了 2000 份红利ETF');

    expect(transForm.value.code).toBe('');
    expect(transForm.value.quantity).toBe(0);
    expect(transForm.value.amount).toBe(0);
  });

  it('没听懂（ok=false）时不产生半截草稿', async () => {
    const { mod, transForm } = buildModule();
    apiMock.nlEntry.mockResolvedValue({
      data: { ok: false, mode: 'unknown_code', draft: null, reason: 'unknown_code', shadow: false },
    });

    await mod.parseNlEntry('买了点茅台');

    expect(transForm.value.code).toBe('');
    expect(transForm.value.quantity).toBe(0);
  });

  it('空原话不发请求', async () => {
    const { mod } = buildModule();

    const data = await mod.parseNlEntry('   ');

    expect(apiMock.nlEntry).not.toHaveBeenCalled();
    expect(data.ok).toBe(false);
  });
});


describe('一句话记账：后端原因 → 人话', () => {
  it('按 mode 查表', () => {
    expect(nlEntryReasonText({ mode: 'empty_universe' })).toContain('先手填第一笔');
    expect(nlEntryReasonText({ mode: 'timeout' })).toContain('超时');
  });

  it('mode 是笼统的 blocked 时用 reason 兜底（否则人话表白写）', () => {
    expect(nlEntryReasonText({ mode: 'blocked', reason: 'assets_unavailable' })).toContain('读持仓清单失败');
  });

  it('认不出的原因不把供应方原文甩给用户（笼统说不可用，原文留在审计表里）', () => {
    const text = nlEntryReasonText({ mode: 'blocked', reason: 'http_404: not found' });
    expect(text).toBe('AI 暂时不可用，请手动填写。');
    expect(text).not.toContain('http_404');
  });
});
