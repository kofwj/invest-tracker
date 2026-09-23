# Figma 重做交接说明

先读这两份再动手：**[figma-basics.md](figma-basics.md)**（Figma 操作速成，只教要用的）、
**[page-performance-layers.md](page-performance-layers.md)**（「收益与快照」页的图层树，照着搭）。

配套文件：`docs/design/figma-tokens.tokens.json`（颜色 / 圆角 / 间距 / 字阶，含 Light · Dark 两个主题）。

三件事按顺序做：**导 token → 建组件库 → 按区块组装页面**。下面是每一步的输入。

---

## 1. 导入 token

1. Figma 里装插件 **Tokens Studio for Figma**（免费版够用）。
2. 插件 → Settings → Import → 选 `docs/design/figma-tokens.tokens.json`。
3. 会得到三个 token set：`global`（圆角/间距/字体/尺寸/层级）、`light`、`dark`；
   文件里的 `$themes` 已经配好 Light / Dark 两个主题，切主题即切 mode。
4. 插件里 **Export → Figma Variables**，就得到一套变量集合 + 两个 mode。

注意两点：

- **颜色是红涨绿跌**。`up` = 红（`#D64545`），`down` = 绿（`#3D9A5F`）。别按西方惯例反过来。
- 带透明度的颜色已转成 8 位 hex（Figma 原生），原文是 `rgba()`：
  `rgba(47,111,126,0.12)` = `#2F6F7E1F`。
- 如果用的是读 W3C DTCG 格式的插件（认 `$value` / `$type`），把文件里的
  `"value"` 换成 `"$value"`、`"type"` 换成 `"$type"` 即可。

---

## 2. 要顺手收敛的数值

现在代码里的取值比需要的多，Figma 阶段正好定死一套。

### 字号：12 种 → 7 档

| 现状（出现次数） | 收敛到 |
|---|---|
| 11px(18)、11.5px(5)、12px(64)、12.5px(14) | `font.size.xs` 12 |
| 13px(58) | `font.size.sm` 13 |
| 14px(18) | `font.size.base` 14 |
| 15px(11)、16px(7) | `font.size.md` 16 |
| 17px(1)、18px(10) | `font.size.lg` 18 |
| 20px(3)、22px(4)、24px(1) | `font.size.xl` 22 |
| 30px(1) | `font.size.2xl` 30 |
| `clamp(26px, 3.2vw, 36px)` | `font.size.display` 36 |

数字一律用等宽字体（`font.family.mono`）+ `tracking.numeral -0.03em` + `tabular-nums`。

### 圆角：7 种 → 6 档

现状 6 / 8 / 10 / 12 / 14 / 16 / 999px。收敛为 6（chip）/ 8（输入框）/ 10（按钮）/
12（小卡）/ 16（卡）/ 999（药丸）。14px 归到 12 或 16。

### 间距：10 种 → 8 档

现状 2 / 4 / 6 / 7 / 8 / 10 / 12 / 14 / 16 / 18 / 20 / 22 / 40px，最常用是 8 / 10 / 12。
收敛为 4 / 8 / 12 / 16 / 20 / 24 / 32 / 40。卡片内边距用 16，卡片间距用 12。

### 断点：12 个 → 3 个

现在代码里出现 420 / 520 / 560 / 640 / 720 / 768 / 900 / 960 / 1000 / 1100 / 1240 / 1280px，
是历史堆积。只保留：

- 桌面：内容宽 **1240px**（`.app-container` 上限，左右 padding 20）
- 平板：**900px**（多列栅格降为 2 列）
- 手机：**560px**（全部单列）

---

## 3. Figma 里做不到、需要手工处理的

| 代码里的写法 | Figma 怎么办 |
|---|---|
| `font-size: clamp(18px, 2vw, 24px)`（自适应字号） | 按 1240 / 900 / 560 三档 frame 各写固定字号，别指望自动 |
| 媒体查询 | 改 frame 宽度时手动切，或做三个 frame 并列 |
| `color-mix(in srgb, var(--app-surface) 92%, transparent)`，**全项目 105 处** | Figma 算不出来。把它当成「同一个色 + 透明度」，用 fill opacity 或叠一层，别新建色值 |
| 背景（`body`）：径向主色 10% + `bg1→bg0` 线性渐变 | Figma 一个填充只能一层渐变，需要额外叠一个矩形层 |
| `--app-shadow` / `--app-shadow-sm`（两个主题各一套） | 建两个 **Effect Style**（阴影不是变量） |

---

## 4. 暗色模式怎么画

代码里靠 `html` 上的 `dark` 类切换（不是 `prefers-color-scheme`），所以 Figma 只需要
**两个 mode**，不需要第三个。

另外，Element Plus 自己的变量被主题接管了这些（Figma 用官方 kit 时要同步覆盖，否则颜色两套）：

- `--el-table-bg-color`、`--el-table-tr-bg-color`、`--el-table-row-hover-bg-color`、
  `--el-table-header-bg-color`、`--el-table-header-text-color`、`--el-table-text-color`、
  `--el-table-border-color`
- `--el-text-color-primary`、`--el-text-color-regular`、`--el-text-color-secondary`
- `--el-card-bg-color`、`--el-border-color-light`

---

## 5. 页面框架

```
.app-container（max-width 1240，padding 22 20 40）
└── .page-shell                     ← Figma 的页面 frame
    ├── .page-shell-header
    │   ├── h1（视觉隐藏，只给读屏）   ← 页头不再显示文字标题
    │   ├── .page-tabs              ← 同组 tab 按钮，屏显「标题」其实是它
    │   ├── .page-shell-heading     ← #heading 插槽
    │   └── .page-shell-actions     ← #actions 插槽（页头右侧按钮）
    └── .page-shell-body            ← 默认插槽，页面内容
```

组件 `PageShell`：props `title`（已全部不传）、`flush`、`compact`（默认 true）；插槽
`default` / `heading` / `actions`。总览页不用它，根节点自己画 `div.overview-page`。

---

## 6. 自研组件 → Figma 组件

| 组件 | Figma 组件 | 变体维度 |
|---|---|---|
| `MetricCard` | 指标卡 | `main`/`secondary` × 色调 `up`/`down`/`warn`/`ok`/`neutral` × 状态 `正常`/`骨架`/`长值` |
| `PageShell` | 页面 frame | 三档宽度；有/无 actions |
| `SnapshotReminder` | 提醒条 | 有快照 / 未快照 / 已跳过 |
| `SnapshotPanel` | 快照明细组 | 有数据 / 空态 |
| `KlineDialog` | 弹窗 | 加载中 / 有数据 / 报错（宽 1080，`top: 4vh`） |
| `AppHeader` | 顶栏 | 桌面一行 / ≤720 两行；展开·收起分组 |
| `HomeDashboard` | 持仓页顶部指标区 | 正常 / 加载 |
| `LoginOverlay` | 登录遮罩 | — |
| `AppDialogs` | 全局弹窗（分红草稿等） | — |

`MetricCard` 的 props：`label` / `value` / `main` / `secondary` / `tone` / `color` / `title`，
插槽 `default`（自定义值，例如「最好一天」那两张卡）和 `#icon`。

**长值必做**：数值卡放一个 7 位数示例（`2,926,708.51`）和一个最长的组合值
（`09-15 -¥16,483.00`，18 字符）。以前就是没画这种，上线后被 `text-overflow: ellipsis`
截成了 `09-15 -¥16,`。

---

## 7. Element Plus

全项目 34 个 `el-*` 标签，按出现文件数：

`el-button 16` · `el-table-column 13` · `el-table 13` · `el-tag 12` · `el-alert 12` ·
`el-card 10` · `el-input-number 9` · `el-input 9` · `el-form-item 8` · `el-form 8` ·
`el-date-picker 7` · `el-select 6` · `el-row 6` · `el-option 6` · `el-col 6` · `el-upload 5` ·
`el-space 5` · `el-empty 4` · `el-dialog 4` · `el-tooltip 3` · `el-radio-group 3` ·
`el-radio-button 3` · `el-collapse-item 3` · `el-collapse 3` · `el-switch 2` · `el-progress 2` ·
其余各 1（`el-tabs` / `el-tab-pane` / `el-statistic` / `el-pagination` / `el-divider` /
`el-checkbox` / `el-autocomplete` / `el-config-provider`）

前 12 个覆盖了绝大部分界面。官方 Element Plus Figma kit 可以当地基，但**表格 / 卡片 / 文字色
必须换成上面第 1 节的变量**，否则和实现不一致。

---

## 8. 逐页区块（自上而下）

### 总览 `/`（不用 PageShell）
1. 快照提醒条
2. ①今天：指标栅格（今日盈亏·主 / 本月 / 今年）+ 待办列表
3. ②资产与仓位：5 张卡（总资产·主 / 持仓浮盈 / 现金+存款 / 权益·防御占比 / 当日参考）
4. ③明细与入口：左列（近半月资产卡 + `#overviewWeekChart` + 持仓速览表 4 列·冻结首列）
   / 右列（今天可做、组合脉搏）+ 底部状态条 3 卡

### 今天该看 `/decision`
1. 页头动作：xirr/日期 tag + 刷新 + 立即检查预警
2. ①今天该看什么：今日看点卡（含 `el-alert` 结论行）→ 行情带：**12 张指标卡**一行 +
   破线摘要行 + 跳转链接
3. ②我的持仓今天怎么样：持仓今日贡献表 **5 列**（不冻结）
4. ③观察与预警（默认折叠）：关键指数 4 列 / 自选关注 5 列 / 价格预警规则 7 列 /
   最近触发表 4 列 / 预警历史 5 列
5. 弹窗「编辑·添加预警」460px

### 收益与快照 `/performance`
1. 页头动作
2. 快照提醒条
3. 提示条（外部流水未录入）
4. 一句话故事卡
5. 核心指标：指标栅格 **2 列**（总资产 / 净投入）
6. 收益尺：5 张卡（今天 / 本月 / 今年 / 近一年 / 开仓至今），是**时间范围选择器**
7. 最近 7 个交易日：指标栅格 **4 列**（7 日累计 / 涨跌天数 / 最好一天 / 最差一天）
8. 每日收益：范围单选 + 指标栅格 4 列 + `#dailyPnlChart` + 每日收益表 **5 列**
9. 快照明细：工具条（日期范围 / 记录今日快照 / 导出 / 压缩）+ 快照历史表 + 区间变化 +
   资产结构饼图 + 人工对账表单
10. 辅助小信息：指标栅格 **2 列**
11. 风险一览：指标栅格 3 列
12. 组合资金流水：建议草稿表 5 列 + 录入表单 + 流水表 **6 列**

### 结构与目标 `/allocation`
1. 页头动作：总资产 tag + 刷新诊断 / 调整参数 / 建议转草稿
2. 顶部指标栅格 **4 列**（权益占比·主 / 防守 / 预计年化 / 需关注问题）
3. 三个 tab：
   - 看现状：故事卡 → 当前结构（`#allocationChart` + `#categoryChart`）→ 配置健康检查 →
     流动性 → 权益情景粗估表 3 列 → 资产大类汇总表 5 列
   - 设目标：目标与纪律面板（预设段 + 缺口进度列表）→ 卫星仓进度卡（每只一行：
     名称 + 当前/目标百分比 + 进度条）
   - 处理偏离：纪律检查 → 问题清单 → 个人计划 → 再平衡建议表 5 列 → 折叠区
     （细分类别明细表 **8 列**·冻结首列 / 纪律草稿表 **10 列**·勾选+名称冻结）
4. 弹窗：纪律·目标参数 560px、编辑纪律草稿 440px

### 持仓明细 `/holdings`
1. 页头动作：同步近一年收益率
2. 持仓概览（指标栅格 4 列 + 状态条 3 卡 + 在途提示）
3. 说明提示条
4. 空态提示
5. 持仓明细表 **12 列**：首列冻结、末列（操作）右冻结
6. K 线弹窗（惰性挂载）

### 其余 7 个页面（只列主要区块）

- **银行存款 `/deposits`**：动作条 → 存款总额全宽卡 + 4 列指标 → 缺起存日提示 →
  左「银行集中度」卡（含 `el-progress`）/ 右「到期分布」表 3 列 → 存款明细表 **12 列**·冻结首列
- **交易录入 `/transactions`**：新增交易卡（表单 + 自动补全）→ 分隔线 → 查询卡（工具条 +
  筛选行 + 交易流水表 **10 列**·首列冻结·末列右冻结 + 分页）
- **券商对账 `/broker`**：用法提示 → 对账卡（工具条 → 解析信息 → 现金提示 → 差异表 9 列 /
  校正建议表 9 列，均冻结首列）→ 对账历史表 9 列·冻结首列
- **证券账户 `/cash`**：动作条 → 费率卡（工具条 + 原生费率表）→ 现金余额卡（校准表单）→
  资金流水卡（录入表单 + 4 个统计 + 筛选条 + 表 **8 列**·首尾冻结）→ 银证勾稽（提示 +
  4 个统计 + 两张 4 列表）
- **消息推送 `/ops/notify`**：动作条 → 4 列指标 → 基础设置卡 → 通道密钥卡（通道网格）→
  折叠区（模板与事件通道表 3 列 / 操作网格 / 最近发送日志表 6 列）
- **数据备份 `/ops/backup`**：动作条 → 4 列指标 → 高风险提示 → 备份文件表 4 列

---

## 9. 布局事实（做组件时必须支持）

- 指标栅格 `.ledger-metrics` 有 `cols-2/3/4/5/6`，实际只用到 **2 / 3 / 4**（5、6 没出现）；
  断点：≤1100 降 3 列、≤900 降 2 列、≤560 单列。另有无列数的单栏用法（存款总额全宽卡）。
- 有一处例外：今天该看的行情带用 `.ledger-metrics.band-metrics.decision-metrics`，
  一行 **12 张卡**，横向可滚动（不是标准栅格）。
- `.merge-grid`（左右两栏）**只有结构与目标页在用**，且拆成三段 tab 后每段只有一个 pane，
  实际是单列。
- **12 个表格冻结首列**（共 17 处 `fixed`），其中 3 个还把「操作」列右冻结。
  表宽最大 12 列（持仓明细 / 存款明细），最宽约 1182px。冻结列在 Figma 里要单独画一层。
- 所有表格都带 `aria-label`（无障碍），设计稿里不用体现，但实现时别漏。

---

## 10. 从 Figma 回到代码

- 出图后给我**每页 PNG（桌面 1440 + 手机 560 各一张）**加标注（间距 / 字号 / 颜色），
  我按图改 Vue，用内置浏览器预览逐页比对。我这边没接 Figma MCP，走截图最稳。
- 或者只确认**一页「视觉规范页」**（颜色、字阶、间距、卡片样式、表格样式），
  剩下的页面我按规范推导，你抽查。
- 改动会落在 `frontend/src/styles/styles.css` 的变量 + 各组件，之后 `scripts/check.sh`
  和 171 条前端用例保证不回归。

建议做成**一次性重做**：Figma 定规范 → 落到 token 和组件 → 以后直接在代码里改，
Figma 只归档。长期双轨（Figma 一套、Element Plus 默认样式一套）一定会飘。
