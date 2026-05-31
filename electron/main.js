"use strict";
const { app, BrowserWindow } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const http = require("http");

// 开发时项目根 = 上一级。打包成 .app 后 __dirname 在 bundle 内，
// 需用环境变量 VA_PROJECT_DIR 指向项目目录以复用其后端环境（自包含打包前的过渡方案）。
const PROJECT_DIR = process.env.VA_PROJECT_DIR || path.join(__dirname, "..");
const ROOT = app.isPackaged ? PROJECT_DIR : path.join(__dirname, "..");
const PORT = 8731;
const BASE = `http://127.0.0.1:${PORT}`;
let backend = null;

function startBackend() {
  const py = path.join(ROOT, ".venv", "bin", "python");
  // 配置目录用 Electron 的 userData（开发与打包都生效），后端据此存读 config.json
  const env = { ...process.env, VA_CONFIG_DIR: app.getPath("userData") };
  backend = spawn(
    py,
    ["-m", "uvicorn", "app.server:app", "--host", "127.0.0.1",
     "--port", String(PORT), "--app-dir", "backend"],
    { cwd: ROOT, stdio: "inherit", env },
  );
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
