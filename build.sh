#!/usr/bin/env bash
# 一键打包自包含 .app（仅 Apple Silicon，不签名）。
# 产物：dist/视频分析-darwin-arm64/视频分析.app —— 内置 Python 后端、可移植 ffmpeg、
# Vision OCR 工具，可拷到别的 Apple Silicon Mac 运行（首次右键打开，设置里填自己的 key）。
set -euo pipefail
cd "$(dirname "$0")"
VENV=.venv

echo "[1/5] 准备 Python 环境..."
[ -d "$VENV" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q -r backend/requirements.txt pyinstaller

echo "[2/5] 编译 macOS Vision OCR 工具..."
[ -f native/vision-ocr/vision-ocr ] || swiftc -O -o native/vision-ocr/vision-ocr native/vision-ocr/main.swift

echo "[3/5] PyInstaller 打包后端 (onedir)..."
rm -rf build dist/backend backend.spec
"$VENV/bin/pyinstaller" --noconfirm --console --name backend \
  --distpath dist --workpath build --specpath . \
  --paths backend \
  --add-data "frontend:frontend" \
  --add-data "native/vision-ocr/vision-ocr:native/vision-ocr" \
  --collect-submodules fastapi \
  --collect-all dashscope \
  --collect-all uvicorn \
  --collect-all imageio_ffmpeg \
  --hidden-import app.server --hidden-import app.media --hidden-import app.asr \
  --hidden-import app.subtitle --hidden-import app.ocr \
  --hidden-import app.config --hidden-import app.library \
  backend/run_server.py

echo "[4/5] 安装 Node 依赖并组装 .app..."
npm install --silent
node_modules/.bin/electron-packager . 视频分析 \
  --platform=darwin --arch=arm64 --out=dist --overwrite \
  --app-bundle-id=com.henry.videoanalysis \
  --extra-resource=dist/backend \
  --ignore="/\.venv($|/)" --ignore="/work($|/)" --ignore="/sample($|/)" \
  --ignore="/dist($|/)" --ignore="/build($|/)" --ignore="/\.git($|/)" \
  --ignore="/\.claude($|/)" --ignore="/backend($|/)" --ignore="\.spec\$"

APP="dist/视频分析-darwin-arm64/视频分析.app"
echo "[5/5] 去隔离标记（本机自用）..."
xattr -dr com.apple.quarantine "$APP" 2>/dev/null || true

echo ""
echo "✅ 打包完成：$APP"
echo "   分发给别人：压缩该 .app 发送；对方首次需「右键 → 打开」，或运行："
echo "   xattr -dr com.apple.quarantine 视频分析.app"
