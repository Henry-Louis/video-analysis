# 视频分析 · video-analysis

一个分析**口播视频内容**与**热度流量**的 Mac 桌面应用 —— 不是剪辑工具。

把视频拖进来，它会：① 把口播内容转成**可搜索的带时间戳字幕**；② 让你框选画面上任意区域（在线人数 / 弹幕 / 点赞数等），每 0.5s OCR 一次，输出随时间变化的**热度趋势**。

## 功能

**① 口播内容（语音转字幕）**
- 阿里云百炼 **Paraformer** 云端识别，句级 + 字级时间戳
- 可搜索 / 高亮的字幕列表、播放跟随高亮、点击跳转、双击编辑、导出 SRT/VTT

**② 热度流量（框选区域定时 OCR）**
- **macOS 原生 Vision** 做 OCR（中文，**本机离线**，零额外依赖）
- 框选区域 → 每 0.5s 识别一次 → 弹幕/文字去重事件 + 数字（在线人数等）的**热度趋势图**（坐标轴 / 峰值标注 / 悬停读数 / 点击跳转）

**视频库**
- 导入即拷贝进库、自动缩略图；可重命名 / 搜索 / 删除；分析结果按视频缓存

## 技术栈

- **Electron** 桌面壳 + 本地 **FastAPI** 后端 + 纯静态前端（HTML/CSS/JS，无框架无构建）
- ASR：阿里云 Paraformer（云端，需自备 DashScope API Key）
- OCR：macOS Vision（原生、离线，源码 `native/vision-ocr/main.swift`）
- 视频处理：ffmpeg（由 `imageio-ffmpeg` 自带，打包即可移植）
- 平台：**仅 Apple Silicon（macOS）**

## 普通用户使用

1. 拿到 `视频分析.app`，首次「右键 → 打开」（应用未签名）。
2. 点右上角 ⚙️ 设置，填入你自己的**阿里云百炼 DashScope API Key**（[获取](https://bailian.console.aliyun.com/)），点「测试连接」。
3. 拖入视频 → 「生成字幕」分析口播内容；「框选区域」→「开始分析」看热度趋势。

> 语音识别会把音频上传到阿里云；区域 OCR 在本机完成；API Key 只存在本机用户目录。

## 开发

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
npm install
npm start          # Electron 桌面应用（自动拉起后端）
```

- 开发态 Key：在设置界面填入，或放 `backend/.env`（`DASHSCOPE_API_KEY=...`，仅本机回退用）。
- 首次区域 OCR 会用 `swiftc` 自动编译 `native/vision-ocr`（需 Xcode Command Line Tools）。
- 纯 Web 调试：`.venv/bin/python -m uvicorn app.server:app --app-dir backend`，浏览器开 http://127.0.0.1:8731

## 打包成可分发的 .app

```bash
./build.sh
```

产物 `dist/视频分析-darwin-arm64/视频分析.app` **自带** Python 后端、可移植 ffmpeg、Vision 工具，可拷到别的 Apple Silicon Mac 运行（不依赖对方的 Python/Homebrew）。未签名，分发时对方首次需「右键 → 打开」，或执行：

```bash
xattr -dr com.apple.quarantine 视频分析.app
```

## 命令行（无界面，调试 / 批处理）

```bash
.venv/bin/python backend/scripts/transcribe.py <video>                  # 视频 → SRT/VTT
.venv/bin/python backend/scripts/ocr_region.py <video> --region X Y W H  # 区域定时 OCR
```

## 目录结构

```
backend/app/    media.py(ffmpeg) · asr.py(Paraformer) · ocr.py(Vision) · subtitle.py
                config.py(设置/用户目录) · library.py(视频库) · server.py(FastAPI)
backend/run_server.py   PyInstaller 打包入口
native/vision-ocr/      main.swift —— macOS Vision OCR 工具（编译为 vision-ocr）
frontend/       index.html · app.js · style.css（视频库视图 + 分析视图）
electron/       main.js（桌面壳，自动起后端）
build.sh        一键打包自包含 .app
```

## 隐私

- 语音识别走云端（阿里云），音频会上传；区域 OCR 用 macOS Vision **完全在本机**。
- DashScope API Key 仅存本机用户目录（`~/Library/Application Support/`），**不进代码库、不进 .app 包**。

## License

[MIT](LICENSE)
