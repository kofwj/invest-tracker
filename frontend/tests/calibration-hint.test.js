import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createApp, h, provide, inject, computed, ref } from 'vue';
import { APP_CTX_KEY } from '../src/composables/useAppCtx.js';
import CalibrationHint from '../src/components/CalibrationHint.vue';
import BackupOpsTab from '../src/views/BackupOpsTab.vue';
import api from '../src/api/index.js';

const elMock = vi.hoisted(() => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}));

vi.mock('element-plus', () => ({
  ElMessage: elMock.message,
}));

vi.mock('../src/api/index.js', () => ({
  default: {
    applyTotalAssetCalibration: vi.fn(),
  },
}));

const passthrough = (name) => ({
  name,
  setup(_, { slots, attrs }) {
    return () => h('div', attrs, slots.default ? slots.default() : []);
  },
});

const TABLE_ROWS = Symbol('table-rows');
const ElTableStub = {
  name: 'ElTable',
  props: { data: { type: Array, default: () => [] } },
  setup(props, { slots, attrs }) {
    provide(TABLE_ROWS, computed(() => props.data || []));
    return () => h('div', attrs, slots.default ? slots.default() : []);
  },
};
const ElTableColumnStub = {
  name: 'ElTableColumn',
  props: { label: { type: String, default: '' } },
  setup(props, { slots }) {
    const rows = inject(TABLE_ROWS, null);
    return () => h(
      'div',
      { class: 'stub-col', 'data-label': props.label },
      (rows ? rows.value : []).map((row, $index) => h(
        'div',
        { class: 'stub-cell' },
        slots.default ? slots.default({ row, $index }) : [],
      )),
    );
  },
};

const ElDialogStub = {
  name: 'ElDialog',
  props: ['modelValue'],
  setup(props, { slots }) {
    return () => props.modelValue ? h('div', { class: 'el-dialog-stub' }, [
      slots.default ? slots.default() : null,
      slots.footer ? slots.footer() : null,
    ]) : null;
  },
};

const ElCardStub = {
  name: 'ElCard',
  setup(_, { slots, attrs }) {
    return () => h('div', attrs, [
      slots.header ? h('div', { class: 'el-card__header' }, slots.header()) : null,
      slots.default ? slots.default() : null,
    ]);
  },
};

const STUBS = {
  ElDialog: ElDialogStub,
  ElForm: passthrough('ElForm'),
  ElFormItem: passthrough('ElFormItem'),
  ElInput: {
    name: 'ElInput',
    props: ['modelValue'],
    emits: ['update:modelValue'],
    setup(props, { emit, attrs }) {
      return () => h('input', {
        ...attrs,
        value: props.modelValue,
        onInput: (e) => emit('update:modelValue', e.target.value),
      });
    },
  },
  ElButton: passthrough('ElButton'),
  ElCard: ElCardStub,
  ElTag: passthrough('ElTag'),
  ElAlert: passthrough('ElAlert'),
  ElUpload: passthrough('ElUpload'),
  ElTable: ElTableStub,
  ElTableColumn: ElTableColumnStub,
  PageShell: passthrough('PageShell'),
};

function mountComponent(comp, ctx, props = {}) {
  const host = document.createElement('div');
  const App = {
    setup() {
      provide(APP_CTX_KEY, ctx);
      return () => h(comp, props);
    },
  };
  const app = createApp(App);
  for (const [name, stub] of Object.entries(STUBS)) {
    app.component(name, stub);
  }
  app.directive('loading', {});
  app.mount(host);
  return { host, app };
}

const flush = () => new Promise((r) => setTimeout(r, 20));

describe('CalibrationHint 总资产校准提示组件', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('dashboard.calibration 为空时整块不渲染，不破坏首屏', async () => {
    const ctx = {
      dashboard: ref({ total_assets: 100000 }),
    };
    const { host, app } = mountComponent(CalibrationHint, ctx);
    await flush();

    expect(host.querySelector('.ov-cal-hint')).toBeNull();
    app.unmount();
  });

  it('有 calibration 数据时渲染提示与平差额，且携带对应 level 属性', async () => {
    const ctx = {
      dashboard: ref({
        total_assets: 1024500,
        calibration: {
          hint: '距上次校准 12 天',
          level: 'due',
          adjustment: -2700,
          last_calibration_date: '2026-10-12',
          last_manual_total_assets: 1021800,
        },
      }),
      formatMoney: (v, d = 2, s = false) => `${s && v >= 0 ? '+' : ''}${v}`,
    };
    const { host, app } = mountComponent(CalibrationHint, ctx);
    await flush();

    const hintEl = host.querySelector('.ov-cal-hint');
    expect(hintEl).not.toBeNull();
    expect(hintEl.getAttribute('data-level')).toBe('due');

    const linkBtn = host.querySelector('.ov-cal-link');
    expect(linkBtn.textContent.trim()).toBe('距上次校准 12 天');

    const adjEl = host.querySelector('.ov-cal-adj');
    expect(adjEl).not.toBeNull();
    expect(adjEl.textContent).toContain('平差 -2700');
    app.unmount();
  });

  it('点击校准按钮弹出对话框并支持输入实测金额进行提交', async () => {
    const fetchData = vi.fn(async () => {});
    api.applyTotalAssetCalibration.mockResolvedValueOnce({
      data: { gap: -2700, new_adjustment: -2700 },
    });

    const ctx = {
      dashboard: ref({
        total_assets: 1024500,
        calibration: {
          hint: '距上次校准 35 天',
          level: 'overdue',
          adjustment: 0,
        },
      }),
      fetchData,
      formatMoney: (v, d = 2, s = false) => `${s && v >= 0 ? '+' : ''}${v}`,
    };
    const { host, app } = mountComponent(CalibrationHint, ctx);
    await flush();

    const linkBtn = host.querySelector('.ov-cal-link');
    linkBtn.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await flush();

    // 弹窗表单里的 input
    const inputs = host.querySelectorAll('input');
    expect(inputs.length).toBeGreaterThanOrEqual(1);

    // 默认预填了当前总资产 1024500
    expect(inputs[0].value).toBe('1024500');

    // 修改为实测总额 1021800
    inputs[0].value = '1021800';
    inputs[0].dispatchEvent(new Event('input', { bubbles: true }));
    await flush();

    // 确认校准按钮
    const buttons = [...host.querySelectorAll('div')].filter(
      (el) => el.textContent.trim() === '确认校准'
    );
    const submitBtn = buttons.find((el) => el.children.length === 0) || buttons[0];
    expect(submitBtn).toBeTruthy();
    submitBtn.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await flush();

    expect(api.applyTotalAssetCalibration).toHaveBeenCalledTimes(1);
    expect(api.applyTotalAssetCalibration).toHaveBeenCalledWith({
      manual_total_assets: 1021800,
      note: '',
    });
    expect(elMock.message.success).toHaveBeenCalledWith('已校准：本次差额 -2700');
    expect(fetchData).toHaveBeenCalledTimes(1);

    app.unmount();
  });
});

describe('BackupOpsTab Q0 流水线心跳卡片', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('渲染 Q0 流水线心跳状态与外部 dead-man 标记', async () => {
    const ctx = {
      maintenanceStatus: ref({
        db_exists: true,
        db_size: 1024 * 1024 * 5,
        backup_count: 3,
        latest_backup: 'invest_20261024.db.bak',
        heartbeats: {
          jobs: [
            {
              job: 'backup',
              label: '数据备份',
              level: 'ok',
              last_ok_at: '2026-10-24 18:00',
              age_hours: 1.5,
              max_age_hours: 30,
              external_url: 'https://hc-ping.com/xxx',
            },
            {
              job: 'sync_prices',
              label: '行情同步',
              level: 'overdue',
              last_ok_at: '2026-10-20 15:00',
              age_hours: 98,
              max_age_hours: 96,
              external_url: null,
            },
          ],
        },
      }),
      backups: ref([
        { filename: 'invest_20261024.db.bak', size: 1024 * 1024 * 5, mtime: '2026-10-24 18:00' },
      ]),
      maintenanceLoading: ref(false),
      latestBackupText: ref(''),
      fetchMaintenance: vi.fn(),
      createDbBackup: vi.fn(),
      downloadBackup: vi.fn(),
      restoreBackup: vi.fn(),
      deleteBackup: vi.fn(),
      restoreUploadedBackup: vi.fn(),
    };

    const { host, app } = mountComponent(BackupOpsTab, ctx);
    await flush();

    // Q0 标题存在
    expect(host.textContent).toContain('Q0');
    expect(host.textContent).toContain('流水线还在跑吗（心跳）');

    // 总结状态标为 1 条逾期 (danger)
    expect(host.textContent).toContain('1 条逾期');

    // 检查各任务行与外部 dead-man 标志
    const rows = host.querySelectorAll('.hb-row');
    expect(rows.length).toBe(2);

    expect(rows[0].textContent).toContain('数据备份');
    expect(rows[0].textContent).toContain('外部 dead-man 已配');

    expect(rows[1].textContent).toContain('行情同步');
    expect(rows[1].textContent).toContain('96 小时');
    expect(rows[1].classList.contains('hb-danger')).toBe(true);

    app.unmount();
  });
});
