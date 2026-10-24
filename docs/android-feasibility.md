# 手机端路线：中心后端 + PWA 终端（2026-10-24 定稿）

> 本文档 2026-10-23 的第一版是「在 Android 上跑 Python 后端、打一个自包含 APK」的可行性实验。
> 实验做通了（硬数据保留在文末附录），但**路线本身被否掉了**。
> 现行决策：**手机只做终端，服务器是唯一的账本。** 下面的“为什么”是这次否掉它的理由，
> 留着是为了三个月后不要有人（包括我自己）拿着附录里的实验数据重新踩一遍。

---

## 一句话结论

**不在手机上跑后端，不在手机上放 SQLite。** 手机通过 PWA（或可选的 WebView/TWA 瘦壳）访问中心后端，
只有服务器那一份数据库。端侧 Python 打包这条路技术上可行、方向上不可取。

---

## 为什么砍掉端侧账本

这四条是按“会不会真的毁掉这个工具”排序的，不是按技术难度。

### 1. 两份 SQLite 就是两本账，直接毁掉对账

现在的账实一致是建立在一个前提上的：**只有一个数需要跟券商 App 对得上**。

- 券商 CSV 导入 → 只读 diff → 写「持仓校正」（`backend/broker_reconcile.py`）
- 现金差额 → 一键记「现金校准」流水（`backend/routers_securities_cash.py`）
- 总资产实测 → 校准平差（本文档同批新增）

手机上一旦有一份独立库，这些通道全部只覆盖一半：手机上录的一笔交易，中心不知道；
中心校正过的成本，手机不知道。**于是“看板数字对不对”这件事永远没有答案**，而这是这个工具唯一的价值主张。

### 2. Android 不会让你常驻跑后台任务

记账 App 本身不需要后台，但这个工具的核心增量恰恰都在后台：日终快照、K 线/净值同步、除权除息扫描、
预警检查、晚间简报、周报。Android 的 Doze + 各厂商电池策略会强杀这些。要活只能前台服务常驻通知栏，
那是把一个“打开看一眼”的工具做成“永远在跑的电池黑洞”。

### 3. 双向同步 = 分布式并发冲突，这才是真正的时间黑洞

两台设备离线各改一条同一持仓、各自生成一条资产快照、主键还不同——要合并就得写 CRDT 或账本合并协议。
打包（Chaquopy / python-for-android）是几天的事，同步引擎是几个月的事，而且**没有正确性上限**。

### 4. 端侧能力上限本来就低

砍掉 pandas / akshare 之后后端还剩 96%（附录实验一），听着不错，但砍掉的正是行情、财报、股东、分红日历、
AI 简报这些“帮你决策”的部分。也就是说：端侧 APK 拿到的是一个**更弱且更容易失真的**版本。

### 那离线怎么办

离线唯一真实的需求是“地铁上想起来要记一笔”。这不需要第二本账，只需要**待提交草稿**：
本地先存草稿，联网后补提交，冲突面为零（草稿只有一个归属：中心）。

---

## 现行路线

| | PWA（现行） | TWA / WebView 瘦壳（可选） | 端侧 Python APK（已否） |
|---|---|---|---|
| 数据 | 中心唯一一份 ✅ | 中心唯一一份 ✅ | 手机独立一份 ❌ |
| 工作量 | 已完成 | 1–2 小时（域名 HTTPS + 数字资产链接） | 2–4 周 + 同步引擎 |
| 后台任务 | 服务器跑 | 服务器跑 | 被 Doze 杀 |
| 功能 | 100% | 100% | 记账可用，行情/财报/AI 要砍 |
| 前置 | 无 | 域名 + 证书 | 打包工具链 + 真机验证 |

PWA 的落地件已经在仓库里（`frontend/public/manifest.webmanifest`、`sw.js`、图标全套，
`frontend/tests/pwa-static.test.js` 守着它们）：Android Chrome「添加到主屏幕」即为独立窗口应用。

**瘦壳 APK 只在一种情况下值得做**：希望有应用图标、免浏览器地址栏、能进应用商店。
那时 TWA 指向中心后端即可，**不要**在壳里塞后端。

---

## 这条线上的待办（按性价比排序）

1. **PWA 安装提示**：首次用手机访问时给出「添加到主屏幕」的一次性提示，避免用户一直用浏览器标签页。
2. **待提交草稿**：断网时记流水落 local 草稿、联网后补提交。解决 90% 的离线场景，冲突面为零。
3. **手机端只保留两屏**：看盘（总资产 / 今日盈亏）+ 快速记一笔。列表页在窄屏上做减法即可，不需要单独实现。
4. **TWA 瘦壳**（可选，最后做）：有稳定域名再加。

---

## 附录：端侧 Python 的实测记录（已归档，不再推进）

保留这段是因为当时测出来的数据是真的，将来若有人翻旧账，至少不用重测。

### 实验一：砍掉 pandas / akshare 后后端还剩多少

用一个只装 `fastapi / uvicorn / pydantic / requests / openpyxl / python-multipart /
urllib3 / httpx` 的干净 venv（**没有** pandas / numpy / akshare）跑全量测试：

| 指标 | 结果 |
|---|---|
| 测试总数 | 578 |
| 通过 | **556（96%）** |
| 失败 | 7，全部在 `tests/test_fundamentals.py`（财报 / 股东 / 分红明细，要 akshare） |
| 收集失败 | 1 个文件（`tests/test_reason_sources.py`，测试自身在顶层 `import pandas`） |
| 依赖包数 | 26 |
| site-packages | 50 MB |

关键前提（这条对任何精简部署都有用）：`backend/` 里所有 `import akshare` / `import pandas`
**都是函数内 lazy import**（`price_sync.py:440`、`kline_cache.py:107`、`return_sync.py:49`、
`broker_reconcile.py:254`），模块顶层没有硬依赖，所以没装这两个包也能启动、也能跑核心逻辑。

### 实验二：pydantic-core 交叉编译到 Android

瘦环境里只有 3 个二进制扩展：

| 扩展 | 性质 | Android 可行性 |
|---|---|---|
| `charset_normalizer/cd.*.so` | C，加速用 | 可删，有纯 Python 回退 |
| `charset_normalizer/md.*.so` | C，加速用 | 同上 |
| **`pydantic_core/_pydantic_core.*.so`** | **Rust（PyO3）** | **硬门槛** |

PyPI 上 pydantic-core 只有 manylinux / macOS / Windows wheel。Android 是 bionic libc，
不是 glibc，manylinux wheel 装不上。

做法与结果：

| 项 | 值 |
|---|---|
| pydantic-core | 2.46.5（`pydantic==2.13.5` 要求） |
| PyO3 | 0.28，**未启用 abi3**（编译期需要 `-lpython3.12`） |
| Rust | 1.98.1，target `aarch64-linux-android` |
| NDK | r27c，clang 18.0.3，`aarch64-linux-android24-clang` |
| 编译耗时 | 31 秒，一次通过 |
| 产物 | `lib_pydantic_core.so`，**4.3 MB**，stripped |
| `NEEDED` | 只有 `libdl.so`、`libm.so`、`libc.so` —— **没有 libpython** ✅ |
| 导出符号 | `PyInit__pydantic_core` ✅ |
| 未定义符号 | 204 个，其中 154 个是 `Py*` / `_Py*`（运行时由 CPython 提供） |

关键点：Linux/Android 上的 Python 扩展**本来就不链接 libpython**，CPython C API 的符号在运行时由宿主解释器提供。
所以 PyO3 索要 `-lpython3.12` 时塞一个空的占位 `.so` 即可——产物的 `NEEDED` 里确实没有 libpython。

唯一未解决的符号是 `getrandom`：它在 bionic 里是 API 28（Android 9）引入的，NDK 21–35 的 stub
`libc.so` 都不导出它，真机上大概率存在。对策是 `minSdkVersion 28`，或补一个
`syscall(SYS_getrandom, ...)` 的 shim。

### 复现步骤（仅为记录，不需要再跑）

```bash
# 1. NDK
curl -L -o ndk.zip https://dl.google.com/android/repository/android-ndk-r27c-darwin.zip
unzip -q ndk.zip

# 2. Rust target
rustup target add aarch64-linux-android

# 3. 源码
pip download pydantic-core==2.46.5 --no-binary=:all: --no-deps
tar xzf pydantic_core-2.46.5.tar.gz

# 4. 占位 libpython（Android 扩展不链接 libpython）
printf 'int _stub;\n' > stub.c
aarch64-linux-android24-clang -shared -fPIC -o libpython3.12.so stub.c

# 5. 交叉编译
TC=<ndk>/toolchains/llvm/prebuilt/darwin-x86_64
export CC_aarch64_linux_android=$TC/bin/aarch64-linux-android24-clang
export AR_aarch64_linux_android=$TC/bin/llvm-ar
export CARGO_TARGET_AARCH64_LINUX_ANDROID_LINKER=$TC/bin/aarch64-linux-android24-clang
export PYO3_CROSS=1 PYO3_CROSS_PYTHON_VERSION=3.12
export RUSTFLAGS="-C link-arg=-L$(pwd)"   # 指向 stub 所在目录
cargo build --release --target aarch64-linux-android

# 6. 验证
$TC/bin/llvm-readelf -d target/aarch64-linux-android/release/lib_pydantic_core.so | grep NEEDED
$TC/bin/llvm-nm -D --defined-only target/aarch64-linux-android/release/lib_pydantic_core.so | grep PyInit
```

注：本机没有 JDK，`sdkmanager` 用不了，所以 NDK 是直接下 zip 解压的。
