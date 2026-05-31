"use strict";
const { contextBridge, webUtils } = require("electron");

// Electron 32+ 移除了 File.path。渲染进程开启了 contextIsolation、不能直接 require electron，
// 故在 preload 里用 webUtils.getPathForFile 取「拖入/选择的文件」的本地绝对路径，
// 经 contextBridge 暴露给前端（window.va.getPathForFile）。
contextBridge.exposeInMainWorld("va", {
  getPathForFile(file) {
    try {
      return webUtils.getPathForFile(file) || "";
    } catch (_) {
      return "";
    }
  },
});
