# 布局改造计划（2026-10-24 实测基线）

这份文档记录**改造前实测出来的数字**和据此定下的方案，不是推测。每一步都写死了验收
标准，方便跨天对照、中断后接续，或者交接给别人。

背景：v1.6.0 之后项目已经能本机直接跑（单进程托管前端），但前端几何仍是「网页」——
`.app-container` 是居中定宽 + 四边留白，没有持久化外壳；手机端 37 张表全靠横向滚动。
第 1 步（应用外壳）已交付，这里规划的是剩下的部分。

---

## 一句话结论

外壳已完成。剩下三块：**路由命名空间收口（0.5 天）→ DataTable 与移动卡片（2.5–3 天）
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
| 前端测试 | 26 文件 / 220 项 |
| 后端测试 | 578 项 |
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

## 阶段 0：路由命名空间收口（0.5 天）

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

方案 B 之所以划算，是因为四件事已经被验证过：

1. `tests/conftest.py` 早就把 `FRONTEND_DIST` 固定指向不存在目录，正好落在 else 分支，
   285 处打根路径的测试一个都不用改。
2. `backend/main.py:175` 与 `:185` 已经把 `/api/health` 和 `/health` **双注册**——双命名
   空间在这个项目里已有先例，不是新发明。
3. 生产镜像的构建上下文是 `./backend`（`docker-compose.prod.yml`），`COPY . .` 只拷后端
   目录，镜像里没有 `frontend/dist`，所以生产必然走 else 分支。
4. `docker-compose.prod.yml` 的 healthcheck 直连 `http://127.0.0.1:8000/api/health`，不经
   nginx；方案 B 下 Docker 模式仍挂中间件，该检查照常通过。

**改动清单**

| 文件 | 改动 |
|---|---|
| `backend/main.py` | `SERVE_FRONTEND` / `API_PREFIX` 判定；19 处 `include_router` 加 `prefix`；中间件改条件挂载 |
| `tests/test_route_prefix.py`（新增） | monkeypatch `FRONTEND_DIST` 指向临时目录，断言 `/api/holdings` 命中 JSON、`/holdings` 返回 `text/html`、`/api/health` 仍 200 |
| `CHANGELOG.md` | 记一条修复 |

**验收**

- 本地起服务，12 个页签路径逐个 `curl -sI` 断言 `content-type: text/html`
- `/api/holdings` `/api/transactions` `/api/deposits` 断言 `application/json`
- 后端 578 项测试全绿
- **VPS 无需任何动作**（这是选方案 B 的主要理由）

### 方案 A（备选，更彻底）

统一 `/api` 前缀、删掉中间件、nginx 的 `proxy_pass` 去掉尾斜杠。语义最干净，只保留一种
拓扑。代价：要批量改 285 处测试路径，且要求 VPS 同步重建容器，漏一处就是运行时 404。

除非决定长期只维护一种拓扑，否则不建议现在做。

---

## 阶段 1：`DataTable` 基础件（1 天）

### 设计原则：透传式包装，不是配置化重写

235 列里有 120 个是 `#default` 插槽，把列抽象成配置对象意味着重写绝大多数表格模板，
diff 巨大且难评审。所以 `DataTable` 只做「响应式布局切换」，桌面端原样透传：

```vue
<DataTable :rows="holdings" row-key="code" empty-text="暂无持仓" label="持仓明细">
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

### 两个实现约束

1. **用 `matchMedia` 切分支，不做双份 DOM。** 双份 DOM 会让窄屏仍然渲染 el-table，
   屏幕阅读器读两遍，DOM 体积也翻倍。抽 `composables/useMediaQuery.js`，在
   `typeof window.matchMedia !== 'function'` 时兜底 `false`（当作宽屏）——jsdom 环境因此
   默认走表格分支，**现有 220 项前端测试不受影响**。
2. **切卡片点定 640。** `styles.css` 已有 `@media (max-width: 640px)` 的移动端整体块，
   不新增断点。769–900 平板区间保持现在的表格行为。

### 这一步只包不改

把 37 张表包进 `<DataTable>`，DOM 输出完全不变。跑通全量测试后可以先发版，零行为变化。

**新增测试** `frontend/tests/data-table.test.js`：宽屏透传、有 card 渲染卡片、无 card 兜底、
空态、`row-key` 取值。

---

## 阶段 2：逐页加移动卡片（1.5–2 天）

按使用频次分批，每批独立可交付、可发版。

| 批次 | 页面 | 表 / 列 | 说明 |
|---|---|---|---|
| A | `HoldingsTab`、`TransactionsTab`、`DepositsTab` | 5 / 42 | 日频操作，投入产出比最高 |
| B | `PerformanceTab`、`CashTab`、`AllocationTab`、`BrokerReconcileTab` | 15 / 95 | 分析类，卡片结构统一为「名称 + 核心数值 + 涨跌」三行 |
| C | `DecisionTab`、`NotifyOpsTab`、`AiOpsTab`、`BackupOpsTab`、`OverviewTab`、`SnapshotPanel`、`AppDialogs` | 17 / 98 | 低频 / 运维 / 弹窗，多数接受横向滚动兜底 |

**每批验收标准（三条都要过）**

1. 三档视口（1100 / 900 / 640）实测，沿用同源 iframe 独立视口方案
2. 卡片必须覆盖该表的**排序依据字段与首要决策字段**（例如持仓必须有市值和浮盈，不能
   只放名称和代码）
3. 新增 `<页面>-cards.test.js` 断言窄屏渲染 N 张卡片、关键文案存在；现有测试零回归

**已知细节**：`TransactionsTab` 的 `max-height="500"` 在卡片模式下没有意义；卡片高度交给
既有分页控制，不引入新的「加载更多」交互。

---

## 阶段 3：桌面壳（1 天）

后端已能单进程托管 dist，壳只需要包一层。

| 方案 | 体积 | 成本 | 风险 |
|---|---|---|---|
| Tauri 2 + 后端 sidecar | ~10MB + 后端 | 中 | 需 PyInstaller 打后端、代码签名、首次启动数据目录已就绪 |
| pywebview | 小 | 低 | macOS 尚可，跨平台表现不一致 |

建议 Tauri 2：Rust 工具链已在本机跑通过（`docs/android-feasibility.md` 里的 pydantic-core
交叉编译 spike）。

---

## 阶段 4：手机端（3–5 天，方案未定）

### 前置技术验证（都还没做）

`docs/android-feasibility.md` 已证明 pydantic-core 能交叉编译，但下面这些完全没验证：

- `getrandom` 在 bionic 上的符号解析（API 28+，需 shim 或抬 minSdk）
- uvicorn 事件循环在 Android 上能否稳定跑
- SQLite WAL 在 Android 应用沙盒里的行为
- 本机无 JDK，`sdkmanager` 不可用，打包前要先装

### 更要紧的是产品决策

手机端独立 SQLite 会产生**双账本**：手机上记了一笔，桌面上看不到；两边都改了同一笔，
没有合并规则。可选路线只有三条：

1. 手机只读（连同一后端，适合自建服务器用户）
2. 手机为主机，桌面通过导出 / 导入同步（需要冲突处理规则）
3. 不做手机端

**这个问题不定，阶段 4 的代码写多少都是白搭。**

---

## 阶段 5：发版 1.7.0（0.5 天）

按既有发布惯例：`backend/version.py` → `CHANGELOG.md` → `git tag v1.7.0`（附注标签）→
快进 `deploy/vps`。

注意：阶段 0 走方案 B 时 VPS **无需重建容器**；若改走方案 A 或改了 `frontend/nginx.conf`，
则必须重建，容器只能在 VPS 上操作。

---

## 验证矩阵

| 检查项 | 命令 / 方法 | 通过标准 |
|---|---|---|
| 后端单测 | `PYTHONPATH=backend python3 -m pytest -q tests` | 578 项全绿 |
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
| `DataTable` 引入后 `el-table` 内部滚动与吸顶冲突 | 表头吸顶错位 | 阶段 1 只包不改，先验证 DOM 无变化；真冲突时去掉表格内的 sticky |
| 窄屏卡片漏关键字段 | 手机上看不到决策依据 | 每批验收强制检查「排序依据字段 + 首要决策字段」 |
| 双份 DOM 导致 a11y 重复朗读 | 屏幕阅读器体验差 | 用 `matchMedia` 单份 DOM，不做 CSS `display:none` 切换 |
| 手机端账本模型定错 | 返工，数据可能对不上 | 阶段 4 开工前必须先拍板路线 |

回退策略：每个阶段独立提交，阶段 0 和阶段 1 都是零行为变化或纯新增，回退只需 revert 单个
提交；阶段 2 分批，任一批出问题不影响其余批次。

---

## 待拍板事项

| 编号 | 事项 | 选项 | 当前状态 |
|---|---|---|---|
| D1 | 阶段 0 走哪个方案 | B（VPS 零动作）/ A（更彻底，要重建容器） | **未定** |
| D2 | 阶段 2 批次 C 的 17 张低频表 | 只做横向滚动兜底 / 也要卡片 | **未定** |
| D3 | 阶段 3 与 4 的顺序 | 先出 `.dmg`（1 天见效）/ 先啃手机端 | **未定** |
| D4 | 手机端账本模型 | 只读镜像 / 导出导入 / 不做 | **未定** |
| D5 | `deploy/vps` 是否快进 | 现已落后 3 个提交（`6f9390e`） | **未定** |

---

## 参考

- `docs/android-feasibility.md` — Android 可行性实测（NDK、交叉编译、测试通过率）
- `docs/deploy-vps.md` — VPS 部署
- `CHANGELOG.md` — 1.6.0 起的变更记录
