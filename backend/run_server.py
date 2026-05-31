"""PyInstaller 入口：把 FastAPI 后端打成自包含可执行（onedir）。

打包态（sys.frozen / sys._MEIPASS）下，资源都被收进解包目录：
    <_MEIPASS>/frontend/                  纯静态前端（server.py 据 _MEIPASS 托管）
    <_MEIPASS>/native/vision-ocr/vision-ocr   macOS Vision OCR 二进制
    <_MEIPASS>/imageio_ffmpeg/binaries/ffmpeg-*  自带 ffmpeg（含 libass）

本入口在导入 app 之前先据 _MEIPASS 把 VA_VISION_OCR / VA_FFMPEG 默认值设好，
使 ocr.py / media.py 在脱离项目 .venv 与 Homebrew 时也能定位到二进制。
端口取环境变量 VA_PORT（默认 8731）。配置目录由 Electron 注入 VA_CONFIG_DIR。
"""
import glob
import os
import sys


def _setup_frozen_env() -> None:
    """打包态：据 sys._MEIPASS 设好 VA_VISION_OCR / VA_FFMPEG（不覆盖已有显式值）。"""
    base = getattr(sys, "_MEIPASS", None)
    if not base:
        return  # 非打包态：交给 media.py(imageio) 与 ocr.py 的项目内相对路径

    # vision-ocr 二进制
    if not os.environ.get("VA_VISION_OCR"):
        vbin = os.path.join(base, "native", "vision-ocr", "vision-ocr")
        if os.path.exists(vbin):
            os.environ["VA_VISION_OCR"] = vbin

    # imageio-ffmpeg 自带的 ffmpeg（文件名带平台/版本，用 glob 兜住）
    if not os.environ.get("VA_FFMPEG"):
        hits = glob.glob(os.path.join(base, "imageio_ffmpeg", "binaries", "ffmpeg-*"))
        hits = [h for h in hits if os.path.isfile(h)]
        if hits:
            os.environ["VA_FFMPEG"] = hits[0]


_setup_frozen_env()

from app.server import app  # noqa: E402  （须在设置环境变量之后导入）

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("VA_PORT", "8731"))
    uvicorn.run(app, host="127.0.0.1", port=port)
