# 桌面应用（macOS）

Tauri 2 外壳 + PyInstaller 打出来的后端侧车。双击 `.app` 就能用：不需要另起 Python、
不需要 Node，账本仍然是本机那一份 SQLite。

## 结构

```
InvestTracker.app/Contents/
├── MacOS/invest-tracker              # Tauri 壳（Rust，10 MB 量级）
├── MacOS/invest-tracker-backend      # PyInstaller 侧车（--onefile，40 MB 量级）
└── Resources/frontend/dist/          # 前端产物，由 bundle.resources 带进来
```

壳启动时依次做四件事：

1. 挑一个端口（见下）
2. 拉起侧车，把 `PORT` / `HOST` / `INVEST_TRACKER_NO_BROWSER=1` / `FRONTEND_DIST` 写进它的环境
3. 轮询 `/api/health`，就绪后把主窗口导航到 `http://127.0.0.1:<port>`
4. 窗口关闭或 `Cmd+Q` 时对侧车发 SIGTERM，等它把 SQLite WAL 落盘（2 秒还没退才强杀）

前端产物走 `bundle.resources` 而不是默认的 `frontendDist`：Tauri 2 会把 `frontendDist`
编进壳二进制，`.app/Contents/` 里看不到它，侧车就找不到 dist、退化成纯 API，窗口一开是 404。
换成资源后改前端只需重打 10 MB 量级的壳，不用碰 40 MB 的侧车。

代价是 `bundle.resources` 一旦声明，`tauri-build` 就要求该路径在**编译期**存在，所以干净
clone 上要先 `mkdir -p frontend/dist`（`beforeDevCommand` 已经代劳），CI 也放了空目录占位。

## 端口

默认 8000，占用了就往后找 8000–8099 里第一个空着的。两个判断是分开的：

- **能复用吗**：只有 `/api/health` 返回本应用独有的 `"database":"ok"` 才算数
- **空着吗**：先 `connect` 探一下没人应答、再 `bind` 成功，才认为端口可用

为什么不只认 `{"status":"ok"}`：同机常驻的其他服务也可能这么答，壳会把窗口导航到别人家的
界面上。为什么不只看 `bind` 成不成功：macOS 允许 `127.0.0.1:8000` 和 `*:8000` 同时存在，
只看 bind 会让两个服务挤在同一个端口上（换到 Linux 又变成直接失败，行为不跨平台一致）。

想钉死端口就设 `PORT`，壳照用不误（冲突了自己负责）。

## 打包

```bash
bash scripts/build-desktop.sh
```

四步：检查工具链 → 构建前端 → PyInstaller 打侧车 → Tauri 构建 + 生成 DMG。产物在
`src-tauri/target/release/bundle/`（`.app` 与 `dmg/InvestTracker_<triple>.dmg`）。

需要 Node、Rust 工具链、`pyinstaller`（`pip install pyinstaller`）；`PYTHON_BIN` 可以指定
解释器。

## 开发模式

```bash
# 终端 1：后端照旧
PYTHONPATH=backend python3 backend/main.py

# 终端 2：仓库根执行
./frontend/node_modules/.bin/tauri dev
```

`tauri dev` 时窗口直接指向 `devUrl`（vite 8080，带热更新），壳**不拉侧车、也不导航**——
`src-tauri/src/lib.rs` 里用 `cfg!(dev)` 把这一段短路了。前端 `/api` 走
`frontend/vite.config.js` 的代理，target 写死 `http://localhost:8000`；本机 8000 若被别的
服务占着，得先改代理 target 或让后端换端口。

`@tauri-apps/cli` 的版本锁在 `frontend/package.json`，请在仓库根用本地那一份
（`./frontend/node_modules/.bin/tauri`）。直接敲 `npx tauri` 会从 npm 装一个同名的无关包
（`tauri@0.x`），报 `could not determine executable to run`。

## 数据

`~/Library/Application Support/InvestTracker/`（由 `platform_data_root()` 决定）：

- `data/invest.db`（连带 `-wal` / `-shm`）
- `backups/`

想让 `.app` 用别的位置（验证、多实例测试），注环境变量给新实例：

```bash
open --env DB_PATH=/tmp/probe/invest.db \
     --env BACKUP_DIR=/tmp/probe/backups \
     /path/to/InvestTracker.app
```

`open --env` 只对**新启动**的实例生效；已经开着的话先
`osascript -e 'tell application "InvestTracker" to quit'`。

侧车二进制本身也认 `DB_PATH` / `BACKUP_DIR` / `PORT` / `FRONTEND_DIST`，
`INVEST_TRACKER_BACKEND_BIN` 可以指定壳该拉起哪个后端。

## 已知限制

- 只打 macOS（`bundle.targets` 是 `["app"]`），窗口尺寸与图标按 macOS 调的
- adhoc 签名、未公证：拷到别的机器双击会被 Gatekeeper 拦，需要右键打开，或自备开发者证书签名后公证
- 侧车是 `--onefile`，首次启动要解压到临时目录，冷启动需几秒
