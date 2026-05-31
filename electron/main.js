"use strict";
const { app, BrowserWindow } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const http = require("http");

const PORT = 8731;
const BASE = `http://127.0.0.1:${PORT}`;
let backend = null;

function startBackend() {
  // 配置目录用 Electron 的 userData（开发与打包都生效），后端据此存读 config.json、
  // 并在打包态把可写工作目录 work/ 放到这里（bundle 只读）。
  const env = {
    ...process.env,
    VA_CONFIG_DIR: app.getPath("userData"),
    VA_PORT: String(PORT),
  };

  if (app.isPackaged) {
    // 打包态：直接跑收进 .app 的自包含后端可执行（PyInstaller onedir，自带 Python）。
    // 它据 sys._MEIPASS 自行定位 bundle 内的 frontend / ffmpeg / vision-ocr，
    // 不再依赖项目 .venv / Homebrew / VA_PROJECT_DIR。
    const exe = path.join(process.resourcesPath, "backend", "backend");
    backend = spawn(exe, [], { stdio: "inherit", env });
  } else {
    // 开发态：沿用项目 .venv 的 uvicorn（带热路径、便于调试）。
    const root = path.join(__dirname, "..");
    const py = path.join(root, ".venv", "bin", "python");
    backend = spawn(
      py,
      ["-m", "uvicorn", "app.server:app", "--host", "127.0.0.1",
       "--port", String(PORT), "--app-dir", "backend"],
      { cwd: root, stdio: "inherit", env },
    );
  }
  backend.on("error", (e) => console.error("[backend] spawn error:", e));
  backend.on("exit", (code) => console.log("[backend] exited:", code));
}

function ping() {
  return new Promise((resolve) => {
    const req = http.get(`${BASE}/health`, (res) => { res.destroy(); resolve(true); });
    req.on("error", () => resolve(false));
    req.setTimeout(800, () => { req.destroy(); resolve(false); });
  });
}

async function ensureBackend() {
  if (await ping()) return;          // 已有健康后端（如开发时手动起的），复用
  startBackend();
  for (let i = 0; i < 60; i++) {
    await new Promise((r) => setTimeout(r, 500));
    if (await ping()) return;
  }
  throw new Error("后端启动超时");
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1200, height: 900, title: "视频分析",
    webPreferences: { contextIsolation: true },
  });
  win.loadURL(`${BASE}/`);
}

app.whenReady().then(async () => {
  try {
    await ensureBackend();
  } catch (e) {
    console.error(e);
  }
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

function shutdown() { if (backend) { backend.kill(); backend = null; } }
app.on("window-all-closed", () => { shutdown(); if (process.platform !== "darwin") app.quit(); });
app.on("quit", shutdown);
