# Figma 上手（只教这次要用的）

你的 Figma 界面是英文的，所以下面括号里给的是界面上实际显示的字。找不到某个按钮就截图给我。

目标只有一个：**画出一套能照着实现的界面稿**。不需要学 Figma 的其它功能（原型、动画、自动布局的高级技巧都跳过）。

---

## 一、6 个必须认识的词

| Figma | 对应你们代码里的 | 说明 |
|---|---|---|
| Frame | `div` + 宽高 | 一切容器。画页面就是画一个大 Frame |
| Layer | DOM 节点 | 图层，左侧 Layers 面板里就是树 |
| Auto layout | `display:flex` / `grid` | 自动排列子元素，**必须用**，否则内容一动就乱 |
| Component / Variant | Vue 组件 / props | 组件 + 变体，改主组件所有实例跟着变 |
| Variable | CSS 变量 | 已经导好了：颜色 `color/*`、间距 `space/*`、圆角 `radius/*` |
| Style | 全局 class | 文字样式、阴影样式 |

---

## 二、快捷键（这些就够）

| 键 | 作用 |
|---|---|
| `V` | 选择工具（默认） |
| `F` | 画 Frame |
| `R` | 画矩形 |
| `T` | 加文字 |
| `⇧A` | 给选中的东西加 Auto layout |
| `⌥⇧A` | 去掉 Auto layout |
| `⌘D` | 复制 |
| `⌘G` / `⌥⌘G` | 编组 / 用选中项建 Frame |
| `⌥⌘K` | 把选中的 Frame 变成组件 |
| `⌘R` | 重命名选中图层 |
| `⇧1` / `⇧2` / `⌘0` | 缩放到全部 / 缩放到选中 / 100% |
| `⌘\` | 收起/展开左右面板（画布能变宽，方便看整体） |

---

## 三、先练一个：画一张指标卡（12 步）

这张卡在 15 个页面里出现最多，练完它你就掌握全部必需操作了。

1. 按 `F`，在画布上拖出一个框。
2. 选中它，右侧 **W / H** 填 `280` / `108`。
3. 按 `⌘R` 改名叫 `MetricCard`。
4. **填背景**：右侧 **Fill** → 点颜色方块 → 弹出面板里找 `light` 集合的 `color/surface` → 点它。框变白色。
5. **加边框**：**Stroke** → 点 `+` → 颜色同样用变量 `color/border` → 粗细 `1`。
6. **圆角**：右侧 **Appearance → Corner radius** 填 `12`。
7. **加阴影**：**Effects** → 点 `+` → 选 `shadow/sm`（这是之前导进去的 Effect style）。
8. **加自动布局**：选中框按 `⇧A`。右侧出现 **Auto layout** 面板：方向选 `↓`（垂直），**padding** 四边 `16`，**gap** `6`。
9. 按 `T`，在框里点一下，输入 `现在总资产`。选中这段字，右侧 **Text**：字号 `12`、字重 `Semi Bold`、颜色用变量 `color/muted`。
10. 再按 `T` 加一段 `2,926,708.51`：字号 `22`、字重 `Semi Bold`、字族选等宽那个（`SF Mono` / `Menlo`）、颜色用变量 `color/text`。
11. 选中外层框（点左侧 Layers 里的 `MetricCard`），按 `⌥⌘K` 变成组件。左侧图层名变成紫色的组件图标。
12. 做「主卡」变体：选中组件按 `⌘D` 复制一份，把数值字号改成 `30`、颜色改成 `color/primary`。同时选中这两个组件 → 右键 **Combine as variants**（或右侧面板 Variants 那一行的 `+`）。

做完你就有 `MetricCard` 组件，含两个变体。

---

## 四、Auto layout ≈ flex

| Auto layout 里的东西 | CSS |
|---|---|
| 方向 `↓` / `→` | `flex-direction: column / row` |
| `gap` | `gap` |
| `padding`（四个数） | `padding: 上 右 下 左` |
| 对齐九宫格 | `align-items` + `justify-content` |
| 选中子元素 → **Fill container** | `flex: 1` |
| **Hug contents** | 宽度/高度由内容撑开（`width: auto`） |
| **Fixed** | 固定宽高 |

画页面时的两条规矩：

- 页面 Frame：宽 **Fixed**、高 **Hug contents**（内容多了自动变高）。
- 里面的卡片：宽 **Fill container**（跟着栅格走），高 **Hug**。

## 五、栅格怎么画

代码里的「指标栅格」是 CSS grid，比如 4 列。Figma 里没有直接用 grid，做法是：

**外层 Frame（Auto layout，方向 →，gap 12）+ 里面 4 个卡片，每个卡片宽度选 Fill container。**

3 列就放 3 个，2 列放 2 个。间距都用 Variable 里的 `space/*`（8/12/16/20/24），别手打数字。

---

## 六、用变量上色（关键，别手填色号）

任何地方要填颜色（背景 Fill、边框 Stroke、文字 Fill），流程都一样：

点颜色方块 → 弹出面板里找变量列表（按集合分组，如 `light` → `color/surface`）→ 点一下绑定。

面板里如果只看到调色板，就在搜索框输入 `bg0`、`surface` 之类，或者点 **Libraries** 切换。

**手填色号的后果**：以后想改主色，得一个个改回来。绑变量就只需要改变量。

当前插件主题停在 **Light**，所以用 `light` 集合里的颜色（`dark` 集合建议删掉，避免绑错）。

---

## 七、文字样式（一次性建好 7 个）

每次手调字号迟早会乱，所以先建样式。做法：选中一段文字 → 右侧 **Text** → 点样式图标 → **Create style**，按下面命名：

| 样式名 | 字号 | 字重 | 用在哪 |
|---|---|---|---|
| `text/xs` | 12 | Semi Bold | 卡片标签、表头 |
| `text/sm` | 13 | Regular | 副文案、表格正文 |
| `text/base` | 14 | Regular | 正文 |
| `text/md` | 16 | Semi Bold | 区块标题 |
| `text/lg` | 18 | Semi Bold | 页面大标题 |
| `text/xl` | 22 | Semi Bold | 指标卡数值（等宽字体） |
| `text/2xl` | 30 | Semi Bold | 主指标卡数值（等宽字体） |

数值类的另外把 **Letter spacing** 设成 `-3%`，跟代码里的 `-0.03em` 对齐。

---

## 八、画完之后怎么给我

1. 按住 `⌘` 点选页面最外层 Frame（或用左侧 Layers 点）。
2. 右侧 **Export** → `+` → 格式选 **PNG**、倍数选 **2x** → 点 **Export**。
3. 每页给我两张：桌面（宽 1280）和手机（宽 560）。

我按图改 Vue，用内置浏览器逐页对比。**不用给我 Figma 链接**，我这边连不上 Figma，截图最准。

---

## 九、卡住了怎么办

截图**整个窗口**（要能看到底部工具栏和右侧面板）发我，指出你想做的那一步，我告诉你点哪里 —— 比你自己摸索快。
