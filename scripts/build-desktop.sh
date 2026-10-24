#!/usr/bin/env bash
set -euo pipefail

trap 'rc=$?; echo "" >&2; echo "!! 构建失败：scripts/build-desktop.sh 第 $LINENO 行 (exit $rc)" >&2' ERR


ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "==> [1/4] 检查桌面打包工具链"

# 1. Node & npm
if ! command -v node >/dev/null 2>&1; then
  if [ -x "/Users/jian/.workbuddy-ai/binaries/node/versions/22.22.2-2/bin/node" ]; then
    export PATH="/Users/jian/.workbuddy-ai/binaries/node/versions/22.22.2-2/bin:$PATH"
  fi
fi
if ! command -v node >/dev/null 2>&1; then
  echo "错误：未找到 Node.js，请确保 node 在 PATH 中" >&2
  exit 1
fi
echo "    Node: $(node -v)"

# 2. Rust & Cargo
if ! command -v cargo >/dev/null 2>&1; then
  if [ -x "$HOME/.cargo/bin/cargo" ]; then
    export PATH="$HOME/.cargo/bin:$PATH"
  fi
fi
if ! command -v cargo >/dev/null 2>&1; then
  echo "错误：未找到 cargo，请确保 Rust 工具链在 PATH 中" >&2
  exit 1
fi
echo "    Cargo: $(cargo --version)"

# 3. Target triple
TARGET_TRIPLE="$(rustc -vV | sed -n 's/host: //p')"
echo "    Target Triple: $TARGET_TRIPLE"

# 4. Python & PyInstaller
PYTHON_BIN="${PYTHON_BIN:-python3}"
PYINSTALLER_BIN=""
if command -v pyinstaller >/dev/null 2>&1; then
  PYINSTALLER_BIN="$(command -v pyinstaller)"
elif [ -x "/Users/jian/.gemini/antigravity-ide/brain/529f738e-37ac-46f6-bd24-5729f7f0b198/scratch/venv/bin/pyinstaller" ]; then
  PYINSTALLER_BIN="/Users/jian/.gemini/antigravity-ide/brain/529f738e-37ac-46f6-bd24-5729f7f0b198/scratch/venv/bin/pyinstaller"
  PYTHON_BIN="/Users/jian/.gemini/antigravity-ide/brain/529f738e-37ac-46f6-bd24-5729f7f0b198/scratch/venv/bin/python"
fi

if [ -z "$PYINSTALLER_BIN" ]; then
  echo "错误：未找到 pyinstaller，请在虚拟环境中安装（pip install pyinstaller）" >&2
  exit 1
fi
echo "    PyInstaller: $PYINSTALLER_BIN"
echo "    Python: $PYTHON_BIN"

echo "==> [2/4] 构建前端生产包 (frontend/dist)"
npm --prefix frontend run build
test -f frontend/dist/index.html
echo "    前端产物就绪：frontend/dist/index.html"

echo "==> [3/4] 打包后端侧车独立二进制 (PyInstaller --onefile)"
mkdir -p src-tauri/binaries
mkdir -p scratch/pyinstaller-build

BACKEND_SIDECAR="src-tauri/binaries/invest-tracker-backend-${TARGET_TRIPLE}"

"$PYINSTALLER_BIN" \
  --name "invest-tracker-backend-${TARGET_TRIPLE}" \
  --onefile \
  --clean \
  --noconfirm \
  --distpath "src-tauri/binaries" \
  --workpath "scratch/pyinstaller-build" \
  --collect-all uvicorn \
  --collect-all starlette \
  --collect-all fastapi \
  --collect-all pydantic \
  --collect-all pydantic_core \
  --paths backend \
  backend/main.py

cp -f "$BACKEND_SIDECAR" "src-tauri/binaries/invest-tracker-backend"
rm -rf scratch/pyinstaller-build

echo "    后端侧车产物就绪："
ls -lh "$BACKEND_SIDECAR"

echo "==> [4/4] 构建 Tauri 桌面应用 (InvestTracker.app)"
export PATH
npx --yes @tauri-apps/cli build --bundles app "$@"

APP_PATH="src-tauri/target/release/bundle/macos/InvestTracker.app"
DMG_DIR="src-tauri/target/release/bundle/dmg"
mkdir -p "$DMG_DIR"
DMG_PATH="${DMG_DIR}/InvestTracker_${TARGET_TRIPLE}.dmg"

if [ -d "$APP_PATH" ]; then
  echo "==> 生成 DMG 安装镜像: $DMG_PATH"
  rm -f "$DMG_PATH"
  hdiutil create -volname "InvestTracker" -srcfolder "$APP_PATH" -ov -format UDZO "$DMG_PATH" >/dev/null
fi

echo ""
echo "============================================================"
echo "  InvestTracker 桌面端打包成功！"
echo "============================================================"
echo "产物列表："
ls -lh "$APP_PATH" 2>/dev/null || true
ls -lh "$DMG_PATH" 2>/dev/null || true
echo "============================================================"

