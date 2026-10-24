# 布局改造计划（2026-10-24 实测基线）

这份文档记录**改造前实测出来的数字**和据此定下的方案，不是推测。每一步都写死了验收
标准，方便跨天对照、中断后接续，或者交接给别人。

背景：v1.6.0 之后项目已经能本机直接跑（单进程托管前端），但前端几何仍是「网页」——
`.app-container` 是居中定宽 + 四边留白，没有持久化外壳；手机端 37 张表全靠横向滚动。
应用外壳、阶段 0（路由收口）、阶段 1 的 `DataTable` 基础件已交付，这里规划的是剩下的部分。

---

## 一句话结论

外壳、路由收口、`DataTable` 基础件已完成。剩下两块：**逐页移动卡片（1.5–2 天）
→ 桌面 / 手机壳（1 天 + 3~5 天）**。

最大不确定性不在前端工作量，而在手机端的**账本模型**：手机独立 SQLite 会产生双账本。
这个问题不定，写多少代码都是白搭。

---

## 已交付的基线

| 项目 | 状态 |
|---|---|
| `v1.6.0` 单进程本地运行 + 平台数据目录 + AGPL-3.0 | 已发布（tag `v1.6.0`） |
| 应用外壳吸顶 + 断点收敛三档 | `8438d61`，三档实测通过 |
| observer 幂等清理 + 自检名单补 `app_paths.py` | `c56204d` |
| 阶段 0 路由命名空间收口（本地拓扑接口挂 `/api`） | 已交付，12 个页签路径实测 `text/html` |
| 阶段 1 `DataTable` 基础件 + 首个接入 | 已交付，三档视口包裹层几何零影响 |
| 阶段 2 批次 A（总览 / 持仓 / 交易 / 存款，6 张表） | `a544562`，640 档 6 张表全部卡片化 |
| 阶段 2 批次 B（业绩 / 现金 / 配置 / 券商对账，15 张表） | `2377c9f`，13 张卡片化 + 2 张 selection 表保留表格 |
| 阶段 3 本地桌面外壳（Tauri 2 + 侧车） | `5ad6633`，已产出 `InvestTracker.app` 与 `.dmg` |
| 阶段 4 移动端 PWA 与主屏幕原生化 | `267c05e`，Manifest + iOS Safari + Safe Area + SW |
| 阶段 5 版本发布 | `v1.7.0` |
| 前端测试 | 30 文件 / 241 项 |
| 后端测试 | 602 项（阶段 0 新增 24 项，原有 578 项未改） |
| 媒体查询断点 | 仅 `1100`（3 处）/ `900`（10 处）/ `640`（10 处） |

---

## 现状实测

复现命令（在仓库根目录执行）：

```bash
# 表格与列的真实数量（不能只数 <el-table[ >]，多行标签会漏）
cd frontend/src
for f in views/*.vue components/*.vue; do
  a=$(grep -o '<el-table' "$f" | wc -l)
  c=$(grep -o '<el-table-column' "$f" | wc -l)
  echo "$f $((a-c)) $c"
done

# 列的写法分布
grep -c 'prop=' views/*.vue
grep -c '<template #default' views/*.vue

# 断点是否真的只剩三档
grep -o '@media[^{]*{' styles/styles.css | sort | uniq -c
```

实测结果：

| 指标 | 数值 | 含义 |
|---|---|---|
| `el-table` 实例 | **37 张**（12 view + `AppDialogs` 3 + `SnapshotPanel` 2） | 迁移面比原估的 28 张大 |
| `el-table-column` | **235 列** | — |
| 列写法：`prop` 直出 | 84 | — |
| 列写法：`#default` 插槽 | 120 | **配置驱动不可行**，一半以上是自定义渲染 |
| 列写法：`#header` 插槽 | 38 | — |
| `type="selection"` | 3 | 卡片模式要保留多选时需额外设计 |
| `type="expand"` / `index` / `row-key` / `show-summary` | 0 | 无复杂交互包袱 |
| `sortable` | 2 | 可忽略 |
| 分页 | 仅 `TransactionsTab` 2 处 | 卡片模式复用同一分页组件 |
| `.table-scroll` 现有使用 | 2 处（`BrokerReconcileTab`） | 已有横向滚动兜底先例 |
| JS 侧响应式分支 | 0（`matchMedia` 只用于暗色主题） | 需新建，无先例可抄 |

| 页面 | 表格 | 列 |
|---|---|---|
| `AllocationTab.vue` | 5 | 30 |
| `DecisionTab.vue` | 6 | 30 |
| `BrokerReconcileTab.vue` | 3 | 27 |
| `CashTab.vue` | 4 | 21 |
| `HoldingsTab.vue` | 2 | 17 |
| `PerformanceTab.vue` | 3 | 17 |
| `DepositsTab.vue` | 2 | 15 |
| `AiOpsTab.vue` | 2 | 11 |
| `NotifyOpsTab.vue` | 2 | 10 |
| `TransactionsTab.vue` | 1 | 10 |
| `OverviewTab.vue` | 1 | 5 |
| `BackupOpsTab.vue` | 1 | 4 |
| `components/AppDialogs.vue` | 3 | 23 |
| `components/SnapshotPanel.vue` | 2 | 15 |

---

## 目标与非目标

**目标**

1. 12 个页签路径刷新、直接打开、深链都能出页面，不出现裸 JSON。
2. 手机上不需要横向拖动就能读完一张表的关键字段。
3. 同一套前端能装进桌面壳和手机壳。

**非目标（明确不做）**

- 视觉重设计（配色、字体、间距体系、图标）
- 暗色模式扩展
- 组件库替换或升级 Element Plus
- 把 235 列重构成配置化 schema
- 新增第四个断点

---

## 阶段 0：路由命名空间收口（0.5 天，已交付）

### 问题

本地单进程模式下 `/holdings` `/transactions` `/deposits` 返回裸 JSON：

```
/holdings      -> 200  首字符 [     ← 裸 JSON
/transactions  -> 200  首字符 {
/deposits      -> 200  首字符 [
/performance   -> 200  首字符 <     ← 正常 HTML
```

原因：`/api` 前缀在 ASGI 层被 `StripApiPrefixMiddleware` 剥掉后，API 路由本身就注册在
`/holdings` 上，优先级高于 SPA 兜底。

**这个 bug 只存在于本地单进程模式。** 生产上 nginx 的 `location /api/` 配
`proxy_pass http://backend:8000/`（带尾斜杠）剥掉前缀，非 `/api` 路径根本到不了后端，
所以 VPS 没有这个问题。这意味着修复**不应该动生产路径**。

### 方案 B（推荐）：按需前缀

```python
SERVE_FRONTEND = find_frontend_dist() is not None
API_PREFIX = "/api" if SERVE_FRONTEND else ""
if not SERVE_FRONTEND:
    app.add_middleware(StripApiPrefixMiddleware)
```

19 处 `include_router` 统一加 `prefix=API_PREFIX`。

| 运行模式 | 路由注册在 | 中间件 | 结果 |
|---|---|---|---|
| 本地单进程（有 dist） | `/api/*` | 不挂 | `/holdings` 走 SPA 回落，出页面 |
| Docker / VPS（无 dist） | `/*` | 挂 | 与现在完全一致，零变化 |
| pytest（`conftest.py` 把 `FRONTEND_DIST` 固定指向不存在的目录） | `/*` | 挂 | **285 处测试零改动** |

方案 B 的前提条件逐条验证过：

1. `tests/conftest.py` 早就把 `FRONTEND_DIST` 固定指向不存在目录，正好落在 else 分支，
   打根路径的测试一个都不用改。
2. `backend/main.py` 已经把 `/api/health` 和 `/health` **双注册**——双命名空间在这个项目里
   已有先例，不是新发明。
3. 生产镜像的构建上下文是 `./backend`（`docker-compose.prod.yml`），`COPY . .` 只拷后端
   目录，镜像里没有 `frontend/dist`，所以生产必然走 else 分支。
4. `docker-compose.prod.yml` 的 healthcheck 直连 `http://127.0.0.1:8000/api/health`，不经
   nginx；方案 B 下 Docker 模式仍挂中间件，该检查照常通过。

5. **但这条路会踩到自检脚本**：`scripts/check.sh` 会先 `npm --prefix frontend run build` 产出
   `dist`，随后导入 `main.py` 断言路由表。届时 `SERVE_FRONTEND=True`，而它
   `required_routes` 里的 25 条写的是根路径（`/transactions` `/holdings` `/cron/*` 等），不改
   就会硬失败。改法见下。

#### 自检脚本必须同步改（已核实可行）

`backend/app_paths.py:191-193` 的判定是
`return explicit if os.path.isdir(explicit) else None`——`FRONTEND_DIST` 显式指向不存在的
目录时**直接返回 None，不会回落到仓库 `frontend/dist`**。所以只要在导入前设一个不存在的
目录，`main.py` 就落回「纯 API」分支：

```bash
# scripts/check.sh 的导入段，原来是 PYTHONPATH=backend "$python_bin" - <<'PY'
PYTHONPATH=backend FRONTEND_DIST="$tmpdir/no-frontend-dist" "$python_bin" - <<'PY'
```

这与 `tests/conftest.py:216` 是同一手法，自检断言的仍是 VPS 实际运行的拓扑；本地 `/api`
拓扑由下面新增的 pytest 用例覆盖。反过来做（把断言的路径改成 `r in routes or f"/api{r}" in
routes`）也能过，但那是让自检同时接受两种拓扑，等于没验到「VPS 拓扑没变」，不如固定环境变
量干净。

**改动清单**

| 文件 | 改动 |
|---|---|
| `backend/main.py` | `SERVE_FRONTEND` / `API_PREFIX` 判定；19 处 `include_router` 加 `prefix`；中间件改条件挂载 |
| `tests/test_route_prefix.py`（新增 8 个函数 / 24 项） | 复用 `conftest.py` 的 `spa_app` fixture（临时 dist 含 `index.html` + `assets`）：12 个页签路径断言 `text/html`、3 个撞车接口的 `/api/*` 断言 JSON、未知 `/api/*` 断言 404 JSON 且不回落首页、`/health` 与 `/api/health` 双通、`app.user_middleware` 里没有 `StripApiPrefixMiddleware` |
| `scripts/check.sh` | 「Checking backend importability」导入前固定 `FRONTEND_DIST` 到不存在的目录，并断言 `API_PREFIX` 为空，使 25 条路由断言仍对应 VPS 拓扑 |
| `CHANGELOG.md` | 记一条修复 |

**验收**

- 本地起服务，12 个页签路径逐个 `curl -sI` 断言 `content-type: text/html`
- `/api/holdings` `/api/transactions` `/api/deposits` 断言 `application/json`
- 后端 602 项测试全绿（原有 578 项一字未改，新增 24 项）
- `bash scripts/check.sh` 全绿——这条最容易漏，它自己会先构建出 `dist`
- **VPS 无需任何动作**（这是选方案 B 的主要理由）

### 方案 A（备选，更彻底）

统一 `/api` 前缀、删掉中间件、nginx 的 `proxy_pass` 去掉尾斜杠。语义最干净，只保留一种
拓扑。代价：要批量改 285 处测试路径，且要求 VPS 同步重建容器，漏一处就是运行时 404。

除非决定长期只维护一种拓扑，否则不建议现在做。

---

## 阶段 1：`DataTable` 基础件（1 天，基础件已交付）

### 设计原则：透传式包装，不是配置化重写

235 列里有 120 个是 `#default` 插槽，把列抽象成配置对象意味着重写绝大多数表格模板，
diff 巨大且难评审。所以 `DataTable` 只做「响应式布局切换」，桌面端原样透传：

```vue
<DataTable :rows="holdings" :loading="loading" row-key="code" empty-text="暂无持仓" label="持仓明细">
  <!-- 宽屏直接透传，一行都不用改 -->
  <el-table :data="holdings"> …原样… </el-table>

  <!-- 窄屏卡片，选填 -->
  <template #card="{ row }"> …紧凑卡片… </template>
</DataTable>
```

| 视口 | 有 `#card` | 无 `#card` |
|---|---|---|
| > 640 | 原表格 | 原表格 |
| ≤ 640 | 卡片列表 | **退回横向滚动表格（等于现状）** |

「没有卡片就退回现状」是这个设计的关键：迁移可以停在任何一步，未覆盖的表不会变差。

### 三条实现约束

1. **用 `matchMedia` 切分支，不做双份 DOM。** 双份 DOM 会让窄屏仍然渲染 el-table，
   屏幕阅读器读两遍，DOM 体积也翻倍。抽 `composables/useMediaQuery.js`，在 `setup` 里
   **同步**读初始值，不要等 `onMounted`——虽然纯 SPA 没有 SSR，但延后一拍会让手机首屏闪过
   一帧被截断的桌面表格：

   ```js
   const isMobile = ref(
     typeof window !== 'undefined' && typeof window.matchMedia === 'function'
       ? window.matchMedia('(max-width: 640px)').matches
       : false,
   );
   ```

   `matchMedia` 不存在时兜底 `false`（当作宽屏）——jsdom 因此默认走表格分支，**接入前的 220 项
   前端测试一条没改**。
2. **切卡片点定 640。** `styles.css` 已有 `@media (max-width: 640px)` 的移动端整体块，
   不新增断点。769–900 平板区间保持现在的表格行为。
3. **`loading` 交给外壳。** 全仓共 **10 处**真实 `v-loading` 绑定（`grep` 命中 12 行，其中 2 行是
   `BackupOpsTab` 的注释文字），其中 5 处直接挂在 `<el-table>` 上（`AllocationTab` 1 处、
   `BackupOpsTab` 1 处、`DecisionTab` 3 处）。窄屏 `el-table` 被卸载后，卡片列表会**完全
   没有加载态**。所以 `DataTable` 接收 `:loading`，把 `v-loading` 挂在外层容器；迁移时同步
   摘掉 el-table 上的那一份，否则宽屏会出现两层遮罩。
   `AllocationTab` 是例外：它的 `<el-card>` 本来就带同款 `v-loading`，摘不摘视觉上一样，所以
   阶段 1 保留原样（零行为变化），等阶段 2 给这张表加 `#card` 时一起清。

### 实际交付：基础件 + 一处接入，不是 37 张全包

原计划是把 37 张表机械包一遍、声称「DOM 输出完全不变」。**实际做不到**——包裹层必然多一层
`div`，而阶段 2 反正要逐表改，批量包装的收益是零、布局风险却集中一次。所以阶段 1 只交付
基础件，并选 `AllocationTab` 的「再平衡建议」作唯一接入点跑通真实链路，其余表随阶段 2
逐页一起包。

「零影响」有实测背书（同源 iframe 三档视口，打开 `/allocation` 后点「处理偏离」）：

| 视口 | 包裹层 rect | `el-table` rect | 是否重合 | 卡片 |
|---|---|---|---|---|
| 1440 | x153 y1702.85 w1134 h92 | 同左 | 是 | 0（无 `#card`） |
| 900 | x73 y1933.36 w754 h92 | 同左 | 是 | 0（无 `#card`） |
| 640 | x57 y2070.86 w526 h92 | 同左 | 是 | 0（`matchesNarrow=true`，正确退回表格） |

包裹层 margin / padding / border 全 0、`display: block`，所以宽屏多这一层不产生任何偏移。

**新增测试** `frontend/tests/data-table.test.js`（8 项）：宽屏透传且不渲染卡片、`loading`
只挂一个外壳、窄屏按行渲染卡片并卸载默认插槽（含 `aria-label`）、无 `#card` 退回表格、
空态文案、`emit(false)` 后卡片卸载表格回来、`cardKeyOf` 三种入参形态加字段缺失。

---

## 阶段 2：逐页加移动卡片（1.5–2 天，批次 A / B 已交付）

按使用频次分批，每批独立可交付、可发版。每批里表与其 `#card` 一次做到位（不再单独有「包装」步骤）。

| 批次 | 页面 | 表 / 列 | 说明 |
|---|---|---|---|
| A | `HoldingsTab`、`TransactionsTab`、`DepositsTab`、`OverviewTab` | 6 / 47 | 日频操作 + 首页第一屏 |
| B | `PerformanceTab`、`CashTab`、`AllocationTab`、`BrokerReconcileTab` | 15 / 95 | 分析类，卡片结构统一为「名称 + 核心数值 + 涨跌」三行 |
| C | `DecisionTab`、`NotifyOpsTab`、`AiOpsTab`、`BackupOpsTab`、`SnapshotPanel`、`AppDialogs` | 16 / 93 | 低频 / 运维 / 弹窗，多数接受横向滚动兜底 |

**A、B 已交付**（`a544562` / `2377c9f`），C 未开始。

### 已交付批次的三档实测

640 档逐页打开，8 个页签全部卡片化、`el-table` 卸载：

| 页签 | 640 档卡片 | 页面里仍以表格呈现的部分 |
|---|---|---|
| `/` | 9 | 无 |
| `/holdings` | 9 | 无 |
| `/transactions` | 51 | 无 |
| `/deposits` | 10 | 无 |
| `/performance` | 34 | `SnapshotPanel` 的 2 张表（批次 C，且在默认收起的折叠区里） |
| `/cash` | 8 | 无（未配对银证分组无数据，整块未渲染） |
| `/allocation` | 14 | 纪律草稿表（selection，按计划兜底） |
| `/broker` | 0 | 无（对账历史为空，走卡片区空态） |

| 检查项 | 结果 |
|---|---|
| 横向溢出 | 8 个页签 `scrollWidth - clientWidth` 全为 0；9 张持仓卡片逐张查过，没有内部横向滚动 |
| 1440 / 900 档（`/holdings` `/cash`） | 卡片 0 张、卡片分支不渲染，表格行数与宽屏一致，包裹层与 `el-table` 矩形完全重合 |
| 卡片外观 | 外层 `.data-card` 管外观（`padding: 10px 12px` + 1px 边框 + 8px 圆角），内层 `.m-card` 只做纵向排版，**没有双层边框**（实测卡片 179px = 内层 157px + padding + 边框） |
| `#card` 覆盖 | 21 处 `DataTable` 里 19 处带 `#card`，差的 2 处正是 2 张 selection 表 |
| 加载态 | 原本挂在 `el-table` 上的 `v-loading` 已移交外壳（`AllocationTab` 再平衡建议）；批次 A/B 其余表本来就没有表级 loading，无回归 |
| 分页 | 卡片跟服务端分页走、不渲染全量：`/transactions` 每页 100 时 51 张，切到 50 后 50 张、第 2 页 1 张（`filteredTransactions` 拿到的就是当前页切片） |
| 测试 | 前端 29 文件 / 236 项，`check.sh` All checks passed；后端 602 项不受影响 |

`/performance` 的卡片在默认收起的折叠面板里，`visibleCards = 0` 是收起所致，不是没渲染。

**每批验收标准（三条都要过）**

1. 三档视口实测，沿用同源 iframe 独立视口方案（批次 A / B 实际用 1440 / 900 / 640；1100 与
   1440 同属 >900 区间、走同一套 CSS 分支，等价）
2. 卡片必须覆盖该表的**排序依据字段与首要决策字段**（例如持仓必须有市值和浮盈，不能
   只放名称和代码）
3. 新增 `<页面>-cards.test.js` 断言窄屏渲染 N 张卡片、关键文案存在；现有测试零回归

**两个不能忘的交互**

- **`HoldingsTab` 持仓表的 `@row-click="showTransactions"` 是手机端查看该持仓历史交易与 K 线的
  唯一入口。** 卡片必须自己绑 `@click="showTransactions(row)"`，否则窄屏下这个功能直接消失。
  已交付：卡片根节点绑了 `showTransactions`，K 线按钮单独绑 `openKline` 并用 `@click.stop`
  挡住冒泡，两个入口都还在。
- 全仓 3 处 `type="selection"`（`AllocationTab` 的纪律草稿、`BrokerReconcileTab` 的校正建议、
  `AppDialogs` 的分红草稿）**明确不做卡片**，走横向滚动兜底。为极低频的移动端批量操作去封装
  卡片勾选通信机制不划算。前两处已随批次 A/B 交付，第三处在批次 C。

**已知细节**：`TransactionsTab` 的 `max-height="500"` 在卡片模式下没有意义；卡片高度交给
既有分页控制，不引入新的「加载更多」交互。

---

## 阶段 3：桌面壳（1 天，已交付）

后端单进程托管 dist，通过 Tauri 2 外壳包裹，实现原生 macOS 桌面运行体验。已交付：

1. **架构方案**：Tauri 2 + PyInstaller 独立二进制侧车（`invest-tracker-backend`）。
2. **源码结构**：新增 `src-tauri/`（含 Tauri 2 配置文件 `tauri.conf.json`、`Cargo.toml`、`src/lib.rs`、`src/main.rs` 及多规格高清应用图标）。
3. **原生窗口**：默认尺寸 1280x860（居中，最小支持 380x600 以便调试移动端卡片布局）。
4. **生命周期与优雅退出**：Rust 主线程探测端口、并发拉起后端并以无阻塞轮询验证 `/api/health` 探针后导航；窗口销毁或退出应用（`Cmd+Q`）时自动向后端发送 SIGTERM 优雅退出，确保 SQLite WAL 完整落盘。
5. **一键构建脚本**：新增 `scripts/build-desktop.sh` 串联前端构建、PyInstaller 侧车打包与 Tauri release 构建，一键生成 `InvestTracker.app` 与 DMG 安装镜像。


---

## 阶段 4：手机端（PWA 路线已交付，独立客户端延后）

按决策 D4 落地路线 4（中心后端 + 手机 PWA），单中心账本零冲突。已交付：

1. **Web App Manifest**：`frontend/public/manifest.webmanifest`，包含 `display: standalone`、多规格图标与主题色，支持 Android Chrome「安装应用」提示。
2. **iOS Safari 原生化**：`index.html` 接入 `apple-mobile-web-app-capable`、`apple-touch-icon`、`apple-mobile-web-app-status-bar-style` 与 `viewport-fit=cover`，支持添加到 iPhone 主屏幕全屏运行。
3. **刘海屏与安全区**：`styles.css` 接入 `env(safe-area-inset-*)`，顶栏、二级导航与主容器自适应贴合，去除移动端触摸灰框。
4. **Service Worker 外壳**：`frontend/public/sw.js` 缓存应用外壳与静态资源，严密保证 `/api/*` 财务接口一律直连网络不缓存。
5. **配套测试**：新增 `frontend/tests/pwa-static.test.js`（5 项）。

注：独立离线手机客户端（单机 APK 模式）在后续版本再行规划评估。


---

## 阶段 5：发版 1.7.0（已交付）

按既有发布惯例已完成：
1. `backend/version.py`：版本号提升至 `1.7.0`（单一来源）。
2. `src-tauri/Cargo.toml` 与 `src-tauri/tauri.conf.json`：桌面壳版本同步至 `1.7.0`。
3. `frontend/public/sw.js`：更新缓存命名空间 `invest-tracker-v1.7.0`。
4. `CHANGELOG.md`：记录 `## [1.7.0] — 2026-10-24`。
5. `git tag -a v1.7.0`。

注意：阶段 0 走方案 B 时 VPS **无需重建容器**；若改走方案 A 或改了 `frontend/nginx.conf`，
则必须重建，容器只能在 VPS 上操作。

---

## 验证矩阵

| 检查项 | 命令 / 方法 | 通过标准 |
|---|---|---|
| 后端单测 | `PYTHONPATH=backend python3 -m pytest -q tests` | 602 项全绿 |
| 前端单测 | `cd frontend && npx vitest run` | 现有 220 项 + 新增全绿 |
| 前端构建 | `cd frontend && npm run build` | 成功，无新增 warning |
| 自检脚本 | `bash scripts/check.sh` | `All checks passed` |
| 三档视口 | 同源 iframe 独立视口 + 浏览器实测 | 顶栏吸顶、二级导航贴合、卡片/表格切换正确 |
| 深链 | 12 个页签路径逐个 `curl` | `text/html` |
| 数据安全 | `sha256sum data/invest.db` | 改造前后一致（`94a4965…`） |

**本地预览必须显式设 `DB_PATH`**：`migrate_on_first_run()` 在 `DB_PATH` 为空时会把仓库里
真实的 `data/invest.db` 改名，那次改动不可逆。

---

## 风险与回退

| 风险 | 影响 | 应对 |
|---|---|---|
| 阶段 0 漏改某个 `include_router` | 本地模式某接口 404 | 新增测试逐条覆盖 19 个路由；本地起服务后逐个 `curl` |
| 阶段 0 改了前缀，`check.sh` 自检因 `dist` 已存在而走错分支 | 断言 25 条根路径全缺失，自检硬失败 | 导入前固定 `FRONTEND_DIST`（`check.sh` 的「Checking backend importability」导入段），与 `conftest.py:216` 同一手法 |
| `DataTable` 引入后 `el-table` 内部滚动与吸顶冲突 | 表头吸顶错位 | 阶段 1 已实测包裹层几何零影响（三档视口矩形完全重合）；真冲突时去掉表格内的 sticky |
| 窄屏卡片漏关键字段 | 手机上看不到决策依据 | 每批验收强制检查「排序依据字段 + 首要决策字段」 |
| 双份 DOM 导致 a11y 重复朗读 | 屏幕阅读器体验差 | 用 `matchMedia` 单份 DOM，不做 CSS `display:none` 切换 |
| 手机端账本模型定错 | 返工，数据可能对不上 | 阶段 4 开工前必须先拍板路线 |

回退策略：每个阶段独立提交，阶段 0 和阶段 1 都是零行为变化或纯新增，回退只需 revert 单个
提交；阶段 2 分批，任一批出问题不影响其余批次。

---

## 待拍板事项

| 编号 | 事项 | 选项 | 建议（依据） | 状态 |
|---|---|---|---|---|
| D1 | 阶段 0 走哪个方案 | B（VPS 零动作）/ A（更彻底，要重建容器） | **B**——VPS 零动作、原有 578 项后端测试零改动，代价只是自检脚本加一行环境变量 | 已定：B，已实施 |
| D2 | 阶段 2 批次 C 的 16 张低频表 | 只做横向滚动兜底 / 也要卡片 | **只做兜底**——运维、配置、弹窗在手机上操作概率极低，横向滚动够用，投入产出比最高 | 已定：只做兜底 |
| D3 | 阶段 3 与 4 的顺序 | 先出 `.dmg`（1 天见效）/ 先啃手机端 | **先阶段 3**——后端单进程已打通，桌面壳 1 天能闭环；手机端还卡在账本路线 | 已定：先阶段 3 |
| D4 | 手机端账本模型 | 中心后端 + PWA / 只读镜像 / 导出导入 / 不做 | **路线 4（中心后端 + 手机 PWA）**——零双账本、零同步代码，拉行情与 AI 简报留在服务器 | 已定：路线 4 |
| D5 | `deploy/vps` 是否快进 | 落后于 `main`（起点 `6f9390e`，进度看 `git log --oneline deploy/vps..main`） | **可随时快进**——落后的提交只碰前端与文档，不触碰生产拓扑，全量测试已过 | 已定：随阶段 0 提交快进 |

---

## 参考

- `docs/android-feasibility.md` — Android 可行性实测（NDK、交叉编译、测试通过率）
- `docs/deploy-vps.md` — VPS 部署
- `CHANGELOG.md` — 1.6.0 起的变更记录
