# Android 安装包可行性（2026-10-23 实测）

目标：把 invest-tracker 装到 Android 手机上，出一个 `.apk`。

这份文档记录的是**跑过的实验和硬数据**，不是推测。结论当前的状态：核心障碍已打通，
剩下的是打包工程和真机验证。

---

## 一句话结论

**pydantic-core（Rust 扩展，整个瘦依赖里唯一编不过去的包）已经成功交叉编译到
Android arm64，产物形态正确。** 后端业务代码 96% 不依赖 pandas/akshare，可以在
Android 上跑。剩下的是打包（Chaquopy 或 python-for-android）和真机验证。

---

## 实验一：砍掉 pandas / akshare 后后端还剩多少

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

**结论**：记账、持仓、现金、快照、收益、纪律、Excel 导出、SPA 路由全部可用。
挂掉的只是「在线抓财报 / 股东 / 分红」这类增强功能，而这些在 Android 上本来也不现实
——akshare 依赖的 numpy/pandas 没有 Android 预编译 wheel，要自己编译一整套。

关键前提：`backend/` 里所有 `import akshare` / `import pandas` **都是函数内 lazy import**
（`price_sync.py:440`、`kline_cache.py:107`、`return_sync.py:49`、`broker_reconcile.py:254`），
模块顶层没有硬依赖，所以没装这两个包也能启动、也能跑核心逻辑。

---

## 实验二：pydantic-core 交叉编译到 Android

### 为什么它卡住

瘦环境里只有 3 个二进制扩展：

| 扩展 | 性质 | Android 可行性 |
|---|---|---|
| `charset_normalizer/cd.*.so` | C，加速用 | 可删，有纯 Python 回退 |
| `charset_normalizer/md.*.so` | C，加速用 | 同上 |
| **`pydantic_core/_pydantic_core.*.so`** | **Rust（PyO3）** | **硬门槛** |

PyPI 上 pydantic-core 只有 manylinux / macOS / Windows wheel。Android 是 bionic libc，
不是 glibc，manylinux wheel 装不上。

### 做法

| 项 | 值 |
|---|---|
| pydantic-core | 2.46.5（`pydantic==2.13.5` 要求） |
| PyO3 | 0.28，**未启用 abi3**（编译期需要 `-lpython3.12`） |
| Rust | 1.98.1，target `aarch64-linux-android` |
| NDK | r27c，clang 18.0.3，`aarch64-linux-android24-clang` |

关键点：Linux/Android 上的 Python 扩展**本来就不链接 libpython**，CPython C API 的符号
在运行时由宿主解释器提供。所以 PyO3 索要 `-lpython3.12` 时，塞一个空的占位 `.so` 即可，
这不是作弊——产物的 `NEEDED` 里确实没有 libpython。

### 结果

编译 **31 秒**，一次通过。

| 检查项 | 结果 |
|---|---|
| 产物 | `lib_pydantic_core.so`，**4.3 MB**，stripped |
| 架构 | ELF64 / AArch64 / DYN（shared object） |
| `NEEDED` | 只有 `libdl.so`、`libm.so`、`libc.so` —— **没有 libpython** ✅ |
| 导出符号 | `PyInit__pydantic_core` ✅（Python 加载扩展的入口） |
| 未定义符号 | 204 个，其中 154 个是 `Py*` / `_Py*`（运行时由 CPython 提供） |
| 非 Python 符号 | 50 个，**49 个**能在 NDK 的 bionic `libc.so` / `libm.so` / `libdl.so` 里找到 |

### 唯一未解决的符号

`getrandom` —— NDK 各 API 版本（21–35）的 stub `libc.so` 都不导出它。它在 bionic 里是
API 28（Android 9）引入的，真机上大概率存在，但本地无法验证。

风险与对策：
- 链接参数带 `-z now`（立即绑定），理论上缺符号会在**加载时**失败，而不是调用时。
- 对策一：`minSdkVersion` 定 **28**（Android 9，2018 年后的机器都覆盖）。
- 对策二：如果真机加载报 `cannot locate symbol "getrandom"`，提供一个 shim：
  用 `syscall(SYS_getrandom, ...)` 实现后随 app 一起打包。

---

## 三条路线的取舍

| | TWA 套壳 | 内嵌 Python APK | Kotlin 重写 |
|---|---|---|---|
| 工作量 | 1–2 小时 | 2–4 周 | 数月 |
| APK 体积 | < 2 MB | 60–80 MB | ~10 MB |
| 离线 | ❌ | ✅ | ✅ |
| 功能 | 100% 现有 | 记账全有；行情/财报/AI 要砍或改联网 | 看写到哪 |
| 前置 | 域名 HTTPS + 数字资产链接 | 打包工具链 + 真机验证 | — |
| 现状 | 可立即做 | **核心障碍已排除**（本文档） | 不推荐 |

### 一个产品层面的判断

记账工具最怕**两份账**。手机里塞独立 SQLite，桌面和手机就是两个账本，之后要写同步、
要处理冲突，比打包本身麻烦得多。TWA 那种「手机看的是同一个库」在数据一致性上更省心；
内嵌 Python 的离线能力更强，代价是双账本。

---

## 后续工作分解（内嵌 Python APK）

1. **打包方案选型**（1 天）
   - Chaquopy：Gradle 插件，嵌 CPython，pip 装纯 Python 包。闭源商业产品，开源项目可免费申请。
     需确认它能否吃下自编译的 `pydantic_core` wheel。
   - python-for-android：全开源，`--requirements=python3,sqlite3,openssl`，要自己写 recipe。
2. **打首个 APK**（3–5 天）
   - 启动时在后台线程起 uvicorn（`127.0.0.1:8000`），主界面 WebView 指过去。
   - 前端 `dist`（2.0 MB）放 assets，启动时解压到 `filesDir`，用 `FRONTEND_DIST` 指过去。
   - 数据目录用 `INVEST_TRACKER_HOME` 指到 app 私有目录。
3. **真机验证**（1–2 天）
   - 验证 `getrandom` 符号、uvicorn 事件循环、SQLite WAL、后台被杀。
   - Android 会杀后台进程：长时间同步要前台服务。
4. **功能裁剪**（2–3 天）
   - 行情/财报/K线/AI 这些依赖 akshare 的能力在 APK 里降级或隐藏，避免用户点了报错。

---

## 复现步骤

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

注：本机没有 JDK，`sdkmanager` 用不了，所以 NDK 是直接下 zip 解压的。真要打 APK 时
还得装 JDK + Gradle（或 Android Studio）。
