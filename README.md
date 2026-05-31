# video-analysis

Mac 桌面 App：上传视频，自动生成字幕，并对框选区域定时 OCR。

## 功能

1. **语音字幕（功能一）** —— 识别视频中的对白，输出带时间戳的字幕（SRT/VTT），像电影台词那样。
   - 引擎：阿里云百炼 **Paraformer**（云端，带句级+字级时间戳）
2. **框选区域 OCR（功能二）** —— 用户在画面上框一个矩形，每 0.5s 对该区域做一次 OCR，
   持续识别弹幕、在线人数等会变化的屏上文字。
   - 引擎：**PaddleOCR**（本地，中文模型）
   - 输出：弹幕/文字去重列表（含首次出现时间）+ 在线人数等数字的时间序列

## 技术栈

- **前端壳**：Electron（视频播放器 + canvas 框选浮层 + 结果展示/导出）
- **后端**：Python + FastAPI（localhost），ffmpeg 抽音轨/抽帧
- **平台**：macOS (Apple Silicon)，仅本机使用（开发模式运行，不打包）

## 环境依赖

- **Python 3.11**（项目用 `.venv`）、**Node ≥ 20**（Electron）
- **ffmpeg-full**（带 libass，用于抽帧/抽音轨/烧字幕；常规 `ffmpeg` 精简版不含 libass）：
  ```bash
  brew install ffmpeg-full   # keg-only，代码自动使用 /opt/homebrew/opt/ffmpeg-full/bin/ffmpeg
  ```
- 功能一需阿里云百炼 **DASHSCOPE_API_KEY**，放在 `backend/.env`
- 功能二首次运行自动下载 PaddleOCR PP-OCRv5 中文模型到 `~/.paddlex`

## 安装

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
cp backend/.env.example backend/.env    # 填入 DASHSCOPE_API_KEY
npm install                              # Electron
```

## 运行

```bash
# 桌面应用（Electron，自动拉起后端并开窗口）
npm start

# 或仅 Web UI：启动后端后浏览器访问 http://127.0.0.1:8731
.venv/bin/python -m uvicorn app.server:app --host 127.0.0.1 --port 8731 --app-dir backend
```

## 命令行工具（无界面，便于批处理/调试）

```bash
# 功能一：视频 → 字幕（可选 --burn 烧录进视频）
.venv/bin/python backend/scripts/transcribe.py <video> [--burn]

# 功能二：对框选区域每 0.5s 做一次 OCR
.venv/bin/python backend/scripts/ocr_region.py <video> --region X Y W H [--fps 2]
```

## 目录结构

```
backend/app/      media.py(ffmpeg) · asr.py(Paraformer) · subtitle.py · ocr.py(PaddleOCR) · server.py(FastAPI)
backend/scripts/  check_asr.py · transcribe.py · check_ocr.py · ocr_region.py
frontend/         index.html · app.js · style.css（播放器 + 框选 + 结果）
electron/         main.js（桌面壳，自动起后端）
work/             运行产物（字幕 / 抽帧 / 烧录视频）
```
