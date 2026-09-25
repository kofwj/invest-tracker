# 设置组 4 页排版原型（notify / ai / cash / backup）

**这是什么**：`docs/design/prototype/settings/` 下 4 个单文件 HTML 原型，把「设置」组 4 页从
「卡片流 + 折叠区」重排成「状态带 + 按问题分区 + 危险区独立」。**只动布局 / 信息层级 / 样式，
不新增或删除功能语义**；数字与凭据是演示数据。

**打开方式**：双击任意 `*.html`（内联 CSS + 少量原生 JS，无构建、无依赖、无新字体）。

**视觉契约**（与 `overview.html` / `performance.html` 同一套，值取自 `frontend/src/styles/styles.css`）：

| 项 | 取值 |
|---|---|
| 页面底 | `radial-gradient(900px 380px at 12% -10%, primary-soft, transparent 60%)` + `bg1 → bg0` |
| 内容宽 | 1120px（原 1080 稍放宽，容纳费率表与凭据栅格） |
| 卡 | 圆角 16 / 1px `--app-border` / `--app-shadow-sm`；卡内分隔用 `--app-hairline` |
| 字阶 | 12 小字 / 13 正文 / 14 卡标题 15 / 状态带数值 20 / 页面标题 18 |
| 间距 | 4 / 8 / 10 / 12 / 14 / 16 / 18 / 22（卡间 22，字段 18×24，卡内 14–20） |
| 圆角 | 8（输入框、按钮）/ 10（单选段）/ 12（小卡、通道组）/ 16（卡）/ 999（药丸） |
| 颜色 | 只用现有 token：`--app-primary`、`--app-ok`、`--app-warn`、`--app-up`（红＝涨/出）、`--app-down`（绿＝跌/入）、`--app-soft` |
| 深色 | `html.dark` 一套（与 styles.css 同值），顶栏「暗色」按钮切换 |
| 断点 | ≤960 三列降两列；≤768 全部单列；表格包 `.scroll-x` 横向滚动 |

**每页只回答几个问题**

| 页 | 状态带回答 | 分区（按问题） |
|---|---|---|
| 消息推送 | 开没开 / 几个通道就绪 / 上次发送结果 / 冷却与模板 | Q1 要不要推（含飞书模式）· Q2 推到哪些通道 · Q3 哪类事件推给谁 · Q4 手动推一把 · Q5 发送日志 |
| AI 设置 | 总开关 / 影子模式 / 今日用量 n÷cap / 密钥 | Q1 连到哪个模型 · Q2 哪些用例允许调用 · Q3 最近一次连接测试 · Q4 最近调用（审计） |
| 证券账户 | 现金合计 / 费率配没配 / 最近一笔流水 | Q1 账户与费率 · Q2 余额校准（含其他调整）· Q3 资金流水 · Q4 银证勾稽 |
| 数据备份 | 数据库 / 备份数量 / 最近备份 / 建议 | Q1 备份文件（+创建、刷新）· Q2 危险操作（恢复 / 上传恢复 / 删除） |

**危险操作（单独成组，带二次确认视觉）**
- 推送页：清除已存凭据（9 项，勾选后锁定对应输入框并汇总影响面）
- AI 页：清除已存密钥（勾选 → 锁定输入框 + 展开确认样式）
- 账户页：恢复默认费率、删除当前账户（现有确认文案）
- 备份页：恢复备份、上传并恢复、删除备份（现有确认文案原样搬进确认面板）

**落地时要补的公共样式（本次不改 .vue / styles.css）**
1. `.app-stat-cell .s`：状态带每格的补充小字（12px / `--app-soft`）。
2. `.app-stat-row` 窄屏断点从 560 收到 768（任务要求 <768px 单列）。
3. 原型新类名建议收进 styles.css（或各页 scoped）：`.field-grid` `.field` `.hazard` `.hazard-grid`
   `.confirm-demo` `.confirm-note` `.badge-confirm` `.use-grid` `.use-card` `.chan` `.mx`
   `.table-scroll`（已存在）`.ec-tag`（对应 `el-tag`）`.ipt`（对应 `el-input`）。
4. 数字一律 `.num`（等宽 + tabular-nums），金额列右对齐。

**原型里的交互只用前端状态**（不伪造后端）：主题切换、飞书模式切字段、清除勾选联动、
事件→通道勾选同步「原始值」列、密码显示/隐藏、开关文案。保存/刷新/试推/测试连接等按钮不带处理器。

## 现有控件 → 新位置（映射表）

### notify.html
| 现有控件 / 字段 | 新位置 |
|---|---|
| `notifyStatus.enabled` 总开关 | Q1 · 总开关 |
| `notifyStatus.template`（short/medium） | Q1 · 正文模板 + 状态带格 4 小字 |
| `notifyStatus.cooldown_minutes` | Q1 · 同事件冷却（分钟）+ 状态带格 4 |
| 飞书模式（webhook/app 选择器） | Q1 · 飞书模式（Q2 飞书组字段跟着切） |
| `channel-grid` 4 通道 chip（name / configured / source / hint） | Q2 · 各通道组标题行（飞书 / 钉钉 / 企业微信 / Telegram） |
| `feishu_webhook` | Q2 · 飞书组（Webhook 模式字段） |
| `feishu_app_id` / `feishu_app_secret` / `feishu_open_id` | Q2 · 飞书组（自建应用模式字段） |
| `dingtalk_webhook` / `dingtalk_secret` | Q2 · 钉钉组 |
| `wecom_webhook` | Q2 · 企业微信组 |
| `telegram_bot_token` / `telegram_chat_id` | Q2 · Telegram 组 |
| `credential_flags`「库里已有」 | 字段 label 旁小标签 |
| show-password / clearable | 密码框「显示 / 隐藏」按钮（清除即清空输入框） |
| `notifyChannelClear` 9 个「清除已存」 | Q2 · 危险区（9 项勾选 + 影响面提示） |
| 事件 → 通道（逗号分隔输入） | Q3 · 矩阵（4 通道勾选）+「原始值（保存时写回）」列 |
| `eventRows.length` | 状态带格 4 小字「事件映射 6 条」 |
| 折叠区「模板与事件通道」 | 拆成 Q1（模板/冷却）+ Q3（事件表） |
| 折叠区「立刻推一把」4 个按钮 | Q4 · 一次性推送（样式沿用原 `.ops-action`） |
| 折叠区「最近发送日志」表 | Q5 · 卡片（时间/事件/通道/标题/结果/原因，失败行有底色） |
| 页头 刷新 / 试推一条 / 保存设置 | 页头 `#actions`（原位置） |
| 提示「改完点右上角「保存设置」才生效…」 | 状态带格 1 小字 |

### ai.html
| 现有控件 / 字段 | 新位置 |
|---|---|
| `form.enabled` | Q1 · 总开关 + 状态带格 1 |
| `form.shadow_mode` | Q1 · 影子模式（文案随状态变：只记日志 / 正式拦截）+ 状态带格 2 |
| `form.daily_call_cap` | Q1 · 每日上限（0＝不限）。状态带格 3 显示 `n / cap`，cap=0 时显示 `n / 不限` |
| `status.today_used` | 状态带格 3 + Q1 每日上限小字 |
| `form.base_url` | Q1 · Base URL（整行宽） |
| `form.model` + `modelOptions` 可搜索下拉 + 允许新建 | Q1 · 模型（`input` + `datalist`，保持「可搜索 + 可手填」） |
| 「拉取模型」按钮 + `modelsLoading` | Q1 · 模型行右侧按钮 |
| `modelsHint`（含 `modelUnknown`） | Q1 · 模型字段下方的成功 / 警告状态条 |
| `form.api_key` + `status.api_key_masked` + show-password | Q1 · API Key（placeholder 显示打码值） |
| `clearApiKey` 清除已存密钥 | Q1 · 危险区（勾选后锁定输入框 + 展开二次确认样式） |
| `form.timeout_seconds` | Q1 · 超时（秒） |
| `form.features.brief / alert_note / nl_rule` | Q2 · 三张用例开关卡（switch + 一句说明 + 已开计数） |
| `lastTest.ok / reason / duration_ms / status / provider_error / request_url` | Q3 · 结果 / 耗时 / HTTP / 时间 + 真实请求 URL + 供应方原文（失败示例收在折叠里） |
| `status.recent` 审计表（时间/用例/模型/结果/原因/耗时） | Q4 · 最近调用表 |
| `status.last_error` 警告条 | 状态带下方的 alert（跨分区置顶） |
| 页头 刷新 / 测试连接 / 保存设置 | 页头 `#actions` |

### cash.html
| 现有控件 / 字段 | 新位置 |
|---|---|
| `dashboard.securities_cash` | 状态带格 1 + Q2「当前自动余额」+ Q3 区间四数之一 |
| `feeSettings[activeFeeAccount]` | 状态带格 2「费率 已配置 / 默认费率」 |
| `cashFlows[0]`（最近一笔） | 状态带格 3 |
| `activeFeeAccount` 下拉 | Q1 · 工具栏「当前账户」 |
| `newFeeAccountName` + 新增账户 | Q1 · 工具栏 |
| `removeFeeAccount` 删除当前账户（≤1 个禁用） | Q1 · 危险区 + 现有确认文案面板 |
| `resetFeeSettings` 恢复默认费率 | Q1 · 危险区（原来在页头，无确认框 → 建议补） |
| 费率表 7 类 × 4 项（`feeCategories`） | Q1 · 原生栅格表（窄屏横向滚动） |
| 默认费率说明文案 | Q1 · 表下方 hint |
| 页头「保存费率」 | 页头 `#actions` |
| `dashboard.securities_cash` 只读余额 | Q2 · 上半左格 |
| `cashForm.amount` + `updateCash` 保存校准 | Q2 · 上半右格（校准会写一条「现金校准」流水） |
| 类型为「现金校准 / 其他调整」的流水 + 编辑 / 删除 | Q2 · 下半「其他调整」表 |
| 新增流水表单（日期 / 账户 / 类型 / 金额 / 新增流水） | Q3 · 上半 3 列栅格 |
| 新增流水备注 | Q3 · 上半（与金额同排的宽字段） |
| `cashFlowSummary`（区间转入 / 转出 / 净额 / 当前现金） | Q3 · 中部 `app-brief cols-4` |
| 筛选栏（日期范围 / 账户 / 类型 / 查询 / 重置） | Q3 · 表上方 |
| `cashFlows` 表（日期/账户/类型/金额/调整前/调整后/备注/编辑/删除） | Q3 · 表（窄屏 `.scroll-x`；原 fixed 左右列原型未画，落地建议保留） |
| `openCashFlowEditDialog` / `deleteCashFlow` | Q3 · 行内「编辑（弹窗）」「删除（现有确认）」 |
| `fetchCashAudit` 刷新勾稽 | Q4 · 卡片右上按钮 |
| `cashAudit.summary_text` alert | Q4 · 顶部 alert（成功 / 警告两态） |
| `cashAudit.bank_in / portfolio_in / bank_out / portfolio_out` | Q4 · `app-brief cols-4` |
| `unmatched_bank` / `unmatched_portfolio` 两张表 | Q4 · 有未配对时展示（无则整块不渲染），示例收在折叠里 |

### backup.html
| 现有控件 / 字段 | 新位置 |
|---|---|
| `maintenanceStatus.db_exists` + `db_size` | 状态带格 1 |
| `backup_count` / `backups.length` | 状态带格 2 + Q1 卡头标签 |
| `maintenanceStatus.latest_backup` | 状态带格 3（含文件名与大小） |
| 静态「建议：先下本地」 | 状态带格 4（保留原文案） |
| 页头「刷新列表」 | Q1 · 卡头右侧（与它刷新的表同处） |
| 页头「创建备份」 | Q1 · 卡头右侧 |
| `backups` 表（文件名 / 大小 / 创建时间 / 下载 / 恢复 / 删除） | Q1 · 表（列序改为 备份文件 / 创建时间 / 大小 / 操作） |
| `downloadBackup` | Q1 · 行内「下载」 |
| `restoreBackup` 恢复 | Q1 · 行内「恢复」+ Q2 二次确认面板（现有文案：会先自动备份当前库…） |
| `deleteBackup` 删除 | Q1 · 行内「删除」+ Q2 确认文案说明 |
| `restoreUploadedBackup`（el-upload，.db/.bak） | Q2 · 危险区「上传并恢复」 |
| 原恢复风险 `el-alert` 文案 | Q2 · 危险区内 alert（原文照搬） |
| `maintenanceLoading` / `backupBusy` 禁用与行内 loading | 原型未画，落地保留 |
