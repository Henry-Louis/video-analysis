const $ = (id) => document.getElementById(id);
const video = $("video");
const overlay = $("overlay");
const regionBox = $("regionBox");

let cues = [];
let currentVideoPath = "";  // 旧路径模式：手动加载的本地绝对路径
let currentVideoId = "";    // 库模式：当前分析的库内视频 id（与 currentVideoPath 互斥）
let region = null;        // [x, y, w, h] 原始视频像素（唯一真值）
let regionMode = false;
let drag = null;          // 画新框时的起点
let edit = null;          // 编辑已有框（移动/缩放）时的状态
let lastActiveIndex = -1; // 字幕跟随高亮守卫
let lastEvtIndex = -1;    // OCR 事件跟随高亮守卫
let exportUrls = [];      // 需回收的 Blob URL

// ---------- 状态 / 进度反馈 ----------
function setStatus(msg, busy = false, isError = false) {
  $("status").textContent = msg || "";
  $("status").classList.toggle("error", isError);
  $("progress").classList.toggle("hidden", !busy);
}

// busy 期间给按钮加 spinner + 禁用，返回恢复函数
function beginBtn(btn, busyText) {
  const original = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span class="btn-spin"></span>${busyText}`;
  // 主按钮态交给 setPrimary 统一管理；这里只负责 spinner + 禁用的还原
  return () => {
    btn.disabled = false;
    btn.innerHTML = original;
  };
}

// 同屏只允许一个实心主按钮
function setPrimary(btn) {
  ["transcribeBtn", "regionModeBtn", "ocrBtn"].forEach((id) => $(id).classList.remove("btn-primary"));
  if (btn) btn.classList.add("btn-primary");
}

function fmt(ms) {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  return `${String(m).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

// 时长（毫秒）-> 人类可读：含小时显示 1:02:03，否则 2:03
function fmtDuration(ms) {
  if (!ms || ms <= 0) return "—";
  const total = Math.round(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const mm = String(m).padStart(h ? 2 : 1, "0");
  const ss = String(s).padStart(2, "0");
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

// 导入时间（毫秒）-> 本地短日期
function fmtDate(ms) {
  if (!ms) return "";
  const d = new Date(ms);
  const y = d.getFullYear();
  const mo = String(d.getMonth() + 1).padStart(2, "0");
  const da = String(d.getDate()).padStart(2, "0");
  return `${y}-${mo}-${da}`;
}

// ==================================================================
//  视图导航：视频库 <-> 分析
// ==================================================================
const libraryView = $("libraryView");
const analysisView = $("analysisView");

function showLibrary() {
  analysisView.classList.add("hidden");
  libraryView.classList.remove("hidden");
  $("backToLibraryBtn").classList.add("hidden");
  $("advLoader").classList.add("hidden");
  $("appTitle").textContent = "视频库";
  // 离开分析：停掉播放、断开视频源，避免后台继续解码/占用
  try { video.pause(); } catch (_) {}
  loadLibrary();
}

function showAnalysis() {
  libraryView.classList.add("hidden");
  analysisView.classList.remove("hidden");
  $("backToLibraryBtn").classList.remove("hidden");
  $("advLoader").classList.remove("hidden");
  $("appTitle").textContent = "分析";
}

$("backToLibraryBtn").onclick = showLibrary;

// ==================================================================
//  视频库：列表 / 搜索 / 导入 / 重命名 / 删除
// ==================================================================
let libraryItems = [];     // 最近一次 GET /library 的结果
let librarySearchText = "";

async function loadLibrary() {
  try {
    const r = await fetch("/library");
    if (!r.ok) throw new Error(await r.text());
    const data = await r.json();
    libraryItems = data.videos || [];
    renderLibrary();
  } catch (e) {
    setLibStatus("加载视频库失败：" + e.message, true);
  }
}

function setLibStatus(msg, isError = false) {
  const el = $("libraryStatus");
  el.textContent = msg || "";
  el.classList.toggle("error", isError);
}

function filteredLibrary() {
  const q = librarySearchText.trim().toLowerCase();
  if (!q) return libraryItems;
  return libraryItems.filter((v) => (v.displayName || "").toLowerCase().includes(q));
}

function renderLibrary() {
  const grid = $("libraryGrid");
  grid.innerHTML = "";

  const total = libraryItems.length;
  const list = filteredLibrary();

  $("libraryEmpty").classList.toggle("hidden", total !== 0);
  $("libraryNoMatch").classList.toggle("hidden", !(total !== 0 && list.length === 0));

  list.forEach((v) => grid.appendChild(buildCard(v)));
}

function buildCard(v) {
  const card = document.createElement("div");
  card.className = "vid-card";
  card.dataset.id = v.id;

  // 缩略图（点击进入分析）
  const thumbWrap = document.createElement("div");
  thumbWrap.className = "vid-thumb";
  const img = document.createElement("img");
  img.loading = "lazy";
  img.alt = v.displayName || v.originalName || "";
  img.src = `/library/${encodeURIComponent(v.id)}/thumb`;
  img.onerror = () => { thumbWrap.classList.add("noimg"); img.remove(); };
  thumbWrap.appendChild(img);

  // 时长角标
  if (v.durationMs) {
    const dur = document.createElement("span");
    dur.className = "vid-dur";
    dur.textContent = fmtDuration(v.durationMs);
    thumbWrap.appendChild(dur);
  }

  // 播放图标 hover 提示
  const playHint = document.createElement("div");
  playHint.className = "vid-play";
  playHint.innerHTML = '<svg viewBox="0 0 24 24" width="34" height="34" aria-hidden="true"><circle cx="12" cy="12" r="11" fill="rgba(0,0,0,.45)"/><path d="M9.5 7.5v9l7-4.5z" fill="#fff"/></svg>';
  thumbWrap.appendChild(playHint);

  thumbWrap.onclick = () => enterAnalysis(v);

  // 删除按钮（右上角）
  const del = document.createElement("button");
  del.className = "vid-del icon-btn";
  del.title = "删除";
  del.setAttribute("aria-label", "删除");
  del.innerHTML = '<svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"><path d="M5 7h14M10 7V5h4v2M6 7l1 13h10l1-13" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  del.onclick = (e) => { e.stopPropagation(); deleteCard(v); };
  thumbWrap.appendChild(del);

  card.appendChild(thumbWrap);

  // 信息区
  const meta = document.createElement("div");
  meta.className = "vid-meta";

  // 就地重命名的标题
  const name = document.createElement("div");
  name.className = "vid-name";
  name.textContent = v.displayName || v.originalName || "(未命名)";
  name.title = "双击重命名";
  name.contentEditable = "false";
  name.spellcheck = false;
  enableRename(name, v);

  const sub = document.createElement("div");
  sub.className = "vid-sub";
  const dot = v.durationMs ? " · " : "";
  sub.textContent = `${fmtDuration(v.durationMs)}${dot}${fmtDate(v.importedAt)}`;

  meta.append(name, sub);
  card.appendChild(meta);
  return card;
}

// 双击标题进入编辑，回车 / 失焦提交（PATCH /library/{id}）
function enableRename(nameEl, v) {
  let committing = false;

  nameEl.addEventListener("dblclick", (e) => {
    e.stopPropagation();
    nameEl.contentEditable = "true";
    nameEl.classList.add("editing");
    nameEl.focus();
    document.getSelection().selectAllChildren(nameEl);
  });

  const commit = async () => {
    if (committing) return;
    committing = true;
    nameEl.contentEditable = "false";
    nameEl.classList.remove("editing");
    const next = nameEl.textContent.replace(/\n/g, " ").trim();
    if (!next || next === (v.displayName || "")) {
      nameEl.textContent = v.displayName || v.originalName || "(未命名)";
      committing = false;
      return;
    }
    try {
      const r = await fetch(`/library/${encodeURIComponent(v.id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ displayName: next }),
      });
      if (!r.ok) throw new Error(await r.text());
      const meta = await r.json();
      v.displayName = meta.displayName ?? next;
      // 同步本地缓存里的该条
      const it = libraryItems.find((x) => x.id === v.id);
      if (it) it.displayName = v.displayName;
      nameEl.textContent = v.displayName;
      // 重命名可能影响搜索过滤结果
      if (librarySearchText.trim()) renderLibrary();
    } catch (e) {
      setLibStatus("重命名失败：" + e.message, true);
      nameEl.textContent = v.displayName || v.originalName || "(未命名)";
    } finally {
      committing = false;
    }
  };

  nameEl.addEventListener("blur", commit);
  nameEl.addEventListener("keydown", (e) => {
    e.stopPropagation();
    if (e.key === "Enter") { e.preventDefault(); nameEl.blur(); }
    if (e.key === "Escape") {
      nameEl.textContent = v.displayName || v.originalName || "(未命名)";
      nameEl.contentEditable = "false";
      nameEl.classList.remove("editing");
      nameEl.blur();
    }
  });
  // 编辑态下点击不要冒泡到缩略图（避免进入分析）
  nameEl.addEventListener("click", (e) => { if (nameEl.isContentEditable) e.stopPropagation(); });
}

async function deleteCard(v) {
  const label = v.displayName || v.originalName || "该视频";
  if (!confirm(`删除「${label}」？\n这会从视频库移除它及其分析结果，不影响你磁盘上的原始文件。`)) return;
  try {
    const r = await fetch(`/library/${encodeURIComponent(v.id)}`, { method: "DELETE" });
    if (!r.ok) throw new Error(await r.text());
    libraryItems = libraryItems.filter((x) => x.id !== v.id);
    renderLibrary();
    setLibStatus("已删除");
  } catch (e) {
    setLibStatus("删除失败：" + e.message, true);
  }
}

// 搜索：即时过滤
$("librarySearch").addEventListener("input", (e) => {
  librarySearchText = e.target.value;
  renderLibrary();
});

// ---------- 导入：点按钮选文件 / 拖拽 ----------
$("importBtn").onclick = () => $("libraryPicker").click();

$("libraryPicker").addEventListener("change", (e) => {
  const files = [...e.target.files];
  e.target.value = "";
  importFiles(files);
});

const libraryDrop = $("libraryDrop");
libraryDrop.addEventListener("dragover", (e) => {
  e.preventDefault();
  libraryDrop.classList.add("drag-over");
});
libraryDrop.addEventListener("dragleave", (e) => {
  if (e.target === libraryDrop || !libraryDrop.contains(e.relatedTarget)) {
    libraryDrop.classList.remove("drag-over");
  }
});
libraryDrop.addEventListener("drop", (e) => {
  e.preventDefault();
  libraryDrop.classList.remove("drag-over");
  importFiles([...e.dataTransfer.files]);
});

// 逐个导入（Electron 渲染进程的 File 带绝对路径 .path）
async function importFiles(files) {
  const paths = files.map((f) => f.path).filter(Boolean);
  if (!paths.length) {
    setLibStatus("没有可导入的视频文件（拖入的需是本地视频）", true);
    return;
  }
  setLibStatus(`正在导入 ${paths.length} 个视频…`);
  let ok = 0, fail = 0;
  for (const p of paths) {
    try {
      const r = await fetch("/library/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: p }),
      });
      if (!r.ok) throw new Error(await r.text());
      ok++;
    } catch (e) {
      fail++;
      console.warn("导入失败", p, e);
    }
  }
  await loadLibrary();
  setLibStatus(fail ? `导入完成：成功 ${ok}，失败 ${fail}` : `已导入 ${ok} 个视频`, fail > 0);
}

// ---------- 点卡片进入分析：加载库内媒体 + 拉缓存结果 ----------
async function enterAnalysis(v) {
  showAnalysis();
  loadVideo(undefined, v.id);
  setStatus(`已加载：${v.displayName || v.originalName || ""}`);
  // 有缓存（字幕 / 区域热度）则直接渲染，省一次重算
  await Promise.allSettled([loadCachedSubtitles(v.id), loadCachedHeat(v.id)]);
}

async function loadCachedSubtitles(id) {
  try {
    const r = await fetch(`/library/${encodeURIComponent(id)}/result?kind=subtitles`);
    if (!r.ok) return;
    const data = await r.json();
    if (data && Array.isArray(data.cues) && data.cues.length) {
      cues = data.cues;
      renderCues();
      rebuildExports();
      $("subExport").classList.remove("hidden");
      lastActiveIndex = -1;
      setPrimary(null);
      setStatus(`已载入缓存字幕：${cues.length} 条`);
    }
  } catch (_) { /* 无缓存忽略 */ }
}

async function loadCachedHeat(id) {
  try {
    const r = await fetch(`/library/${encodeURIComponent(id)}/result?kind=heat`);
    if (!r.ok) return;
    const data = await r.json();
    if (data && Array.isArray(data.events)) {
      // 与 /ocr_region 返回结构一致：{frames, events, numbers}
      renderOcr(data);
    }
  } catch (_) { /* 无缓存忽略 */ }
}

// ---------- 清空一条视频的分析状态（字幕 / 框选 / OCR） ----------
function resetAnalysisState() {
  cues = [];
  $("cueList").innerHTML = '<li class="empty-hint">点「生成字幕」开始。</li>';
  $("subtitle").textContent = "";
  $("subExport").classList.add("hidden");
  revokeExportUrls();
  $("ocrResult").className = "ocr-result empty-hint";
  $("ocrResult").textContent = "框选一个区域，再点「开始分析」。";
  region = null;
  exitRegionMode();
  regionBox.classList.add("hidden");
  $("regionInfo").textContent = "";
  lastActiveIndex = -1;
  lastEvtIndex = -1;
}

// ---------- 加载视频 ----------
// 库模式：loadVideo(undefined, id)；旧路径模式：loadVideo(path)
function loadVideo(path, id) {
  if (!path && !id) return;
  currentVideoId = id || "";
  currentVideoPath = id ? "" : path;
  video.src = id ? `/library/${encodeURIComponent(id)}/media`
                 : "/media?path=" + encodeURIComponent(path);
  video.load();
  $("emptyState").classList.add("hidden");
  $("controls").classList.remove("hidden");

  resetAnalysisState();

  setPrimary($("transcribeBtn"));   // 刚加载视频：生成字幕是此刻该点的
  setStatus("已加载视频");
}

// 当前分析对象是否有效（库 id 或本地路径）
function hasVideo() { return !!(currentVideoId || currentVideoPath); }

$("loadBtn").onclick = () => loadVideo($("videoPath").value.trim());
$("videoPath").addEventListener("keydown", (e) => {
  if (e.key === "Enter") loadVideo($("videoPath").value.trim());
});

// 分析视图内手动选文件（隐藏 input，Electron 渲染进程的 File 带绝对路径 .path）
$("filePicker").addEventListener("change", (e) => {
  const f = e.target.files[0];
  if (f && f.path) loadVideo(f.path);
  e.target.value = "";
});
$("emptyState").addEventListener("click", () => $("filePicker").click());

// 分析视图内拖拽：直接加载该本地路径（不入库）
const stage = $("stage");
stage.addEventListener("dragover", (e) => {
  e.preventDefault();
  stage.classList.add("drag-over");
});
stage.addEventListener("dragleave", (e) => {
  if (e.target === stage || !stage.contains(e.relatedTarget)) stage.classList.remove("drag-over");
});
stage.addEventListener("drop", (e) => {
  e.preventDefault();
  stage.classList.remove("drag-over");
  const f = e.dataTransfer.files[0];
  if (f && f.path) loadVideo(f.path);
});

// ---------- 自定义播放控制条 ----------
const playBtn = $("playBtn");
const icPlay = playBtn.querySelector(".ic-play");
const icPause = playBtn.querySelector(".ic-pause");
const seek = $("seek");
const seekFill = $("seekFill");

function togglePlay() {
  if (video.paused) video.play(); else video.pause();
}
playBtn.onclick = togglePlay;
video.addEventListener("play", () => { icPlay.classList.add("hidden"); icPause.classList.remove("hidden"); });
video.addEventListener("pause", () => { icPlay.classList.remove("hidden"); icPause.classList.add("hidden"); });

function updateControls() {
  const d = video.duration || 0;
  const c = video.currentTime || 0;
  seekFill.style.width = (d ? (c / d) * 100 : 0) + "%";
  $("timeLabel").textContent = `${fmt(c * 1000)} / ${fmt(d * 1000)}`;
}
video.addEventListener("loadedmetadata", () => { updateControls(); syncRegionBox(); });

seek.addEventListener("mousedown", (e) => {
  const move = (ev) => {
    const rect = seek.getBoundingClientRect();
    const ratio = Math.min(1, Math.max(0, (ev.clientX - rect.left) / rect.width));
    if (video.duration) video.currentTime = ratio * video.duration;
  };
  move(e);
  const up = () => { window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up); };
  window.addEventListener("mousemove", move);
  window.addEventListener("mouseup", up);
});

// ---------- 实时字幕叠加 + 列表跟随高亮 ----------
video.addEventListener("timeupdate", () => {
  updateControls();
  const ms = video.currentTime * 1000;

  const idx = cues.findIndex((c) => ms >= c.begin_time && ms < c.end_time);
  $("subtitle").textContent = idx >= 0 ? cues[idx].text : "";
  if (idx !== lastActiveIndex) {
    const lis = $("cueList").querySelectorAll("li[data-index]");
    lis.forEach((li) => li.classList.remove("active"));
    if (idx >= 0) {
      const li = $("cueList").querySelector(`li[data-index="${idx}"]`);
      if (li) { li.classList.add("active"); li.scrollIntoView({ block: "nearest" }); }
    }
    lastActiveIndex = idx;
  }

  // OCR 事件跟随高亮（事件时间单位为秒）
  const evts = $("ocrResult").querySelectorAll(".evt[data-first]");
  if (evts.length) {
    const sec = video.currentTime;
    let hit = -1;
    evts.forEach((d, i) => {
      const f = parseFloat(d.dataset.first), l = parseFloat(d.dataset.last);
      if (sec >= f && sec <= l) hit = i;
    });
    if (hit !== lastEvtIndex) {
      evts.forEach((d) => d.classList.remove("active"));
      if (hit >= 0) evts[hit].classList.add("active");
      lastEvtIndex = hit;
    }
  }
});

function flash(el) {
  if (!el) return;
  el.classList.remove("flash");
  void el.offsetWidth;       // 重启动画
  el.classList.add("flash");
  setTimeout(() => el.classList.remove("flash"), 450);
}

function seekTo(sec) {
  video.currentTime = sec;
  flash($("subtitle"));
}

// ---------- 功能一：生成字幕 ----------
$("transcribeBtn").onclick = async () => {
  if (!hasVideo()) return alert("请先加载视频");
  const restore = beginBtn($("transcribeBtn"), "生成中…");
  setStatus("正在生成字幕…", true);
  try {
    const r = await fetch("/transcribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(currentVideoId ? { id: currentVideoId } : { video: currentVideoPath }),
    });
    if (!r.ok) throw new Error(await r.text());
    const data = await r.json();
    cues = data.cues || [];
    renderCues();
    rebuildExports();
    $("subExport").classList.remove("hidden");
    lastActiveIndex = -1;
    setStatus(`字幕完成：${cues.length} 条`);
    setPrimary(regionMode && region ? $("ocrBtn") : null);
  } catch (e) {
    setStatus("生成字幕失败：" + e.message, false, true);
  } finally {
    restore();
  }
};

function renderCues() {
  const ul = $("cueList");
  ul.innerHTML = "";
  if (!cues.length) { ul.innerHTML = '<li class="empty-hint">无字幕</li>'; return; }
  cues.forEach((c, i) => {
    const li = document.createElement("li");
    li.dataset.index = i;
    const t = document.createElement("span");
    t.className = "t";
    t.textContent = fmt(c.begin_time);
    const span = document.createElement("span");
    span.className = "cue-text";
    span.textContent = c.text;
    span.contentEditable = "true";
    span.spellcheck = false;
    li.append(t, span);

    // 单击跳转，双击进入编辑（用计时区分）
    let clickTimer = null;
    li.addEventListener("click", () => {
      if (document.activeElement === span) return; // 编辑中不跳转
      if (clickTimer) return;
      clickTimer = setTimeout(() => {
        clickTimer = null;
        seekTo(c.begin_time / 1000);
        video.play();
        flash(li);
      }, 220);
    });
    span.addEventListener("dblclick", (e) => {
      e.stopPropagation();
      if (clickTimer) { clearTimeout(clickTimer); clickTimer = null; }
      span.focus();
      document.getSelection().selectAllChildren(span);
    });
    const commit = () => {
      cues[i].text = span.textContent.replace(/\n/g, " ").trim();
      rebuildExports();
    };
    span.addEventListener("input", commit);
    span.addEventListener("blur", commit);
    span.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); span.blur(); }
    });
    ul.appendChild(li);
  });
}

// ---------- 前端现拼 SRT / VTT（复刻 backend/app/subtitle.py 的 _fmt） ----------
function pad(n, w) { return String(n).padStart(w, "0"); }
function tc(ms, sep) {
  ms = Math.max(0, Math.round(ms));
  const h = Math.floor(ms / 3600000); ms -= h * 3600000;
  const m = Math.floor(ms / 60000);   ms -= m * 60000;
  const s = Math.floor(ms / 1000);    ms -= s * 1000;
  return `${pad(h, 2)}:${pad(m, 2)}:${pad(s, 2)}${sep}${pad(ms, 3)}`;
}
function buildSrt() {
  return cues.map((c, i) =>
    `${i + 1}\n${tc(c.begin_time, ",")} --> ${tc(c.end_time, ",")}\n${c.text}\n`
  ).join("\n");
}
function buildVtt() {
  return "WEBVTT\n\n" + cues.map((c) =>
    `${tc(c.begin_time, ".")} --> ${tc(c.end_time, ".")}\n${c.text}\n`
  ).join("\n");
}
function revokeExportUrls() {
  exportUrls.forEach((u) => URL.revokeObjectURL(u));
  exportUrls = [];
}
function rebuildExports() {
  revokeExportUrls();
  const srtUrl = URL.createObjectURL(new Blob([buildSrt()], { type: "text/plain" }));
  const vttUrl = URL.createObjectURL(new Blob([buildVtt()], { type: "text/vtt" }));
  exportUrls = [srtUrl, vttUrl];
  $("srtLink").href = srtUrl;
  $("vttLink").href = vttUrl;
}

// ---------- 框选区域（状态机按钮）----------
function enterRegionMode() {
  regionMode = true;
  overlay.classList.add("active");
  $("regionModeBtn").classList.add("on");
  $("regionModeBtn").textContent = "退出框选";
  setStatus(region ? "拖动手柄可调整，或重新拖一个框" : "在画面上拖拽出一个矩形");
}
function exitRegionMode() {
  regionMode = false;
  overlay.classList.remove("active");
  $("regionModeBtn").classList.remove("on");
  $("regionModeBtn").textContent = "框选区域";
  $("ocrBtn").classList.add("hidden");
}
$("regionModeBtn").onclick = () => {
  if (regionMode) { exitRegionMode(); setStatus(""); }
  else { enterRegionMode(); }
  refreshOcrButton();
};

// 拖完框 / 已有框时，把 ocrBtn 显示为「开始分析」主按钮
function refreshOcrButton() {
  if (regionMode && region) {
    $("ocrBtn").classList.remove("hidden");
    setPrimary($("ocrBtn"));
  } else {
    $("ocrBtn").classList.add("hidden");
    setPrimary(regionMode ? null : (hasVideo() && !cues.length ? $("transcribeBtn") : null));
  }
}

// 原始像素 <-> 显示像素
function scaleToOrig() {
  const rect = video.getBoundingClientRect();
  // object-fit:contain，画面真实显示区可能有 letterbox，按比例换算
  const vw = video.videoWidth, vh = video.videoHeight;
  if (!vw || !vh) return { sx: 1, sy: 1, ox: 0, oy: 0, dispW: rect.width, dispH: rect.height };
  const scale = Math.min(rect.width / vw, rect.height / vh);
  const dispW = vw * scale, dispH = vh * scale;
  const ox = (rect.width - dispW) / 2, oy = (rect.height - dispH) / 2;
  return { sx: vw / dispW, sy: vh / dispH, ox, oy, dispW, dispH };
}

// region(原始px) -> 重算 regionBox 的显示位置（resize/loadedmetadata 后贴回画面）
function syncRegionBox() {
  if (!region) return;
  const { sx, sy, ox, oy } = scaleToOrig();
  regionBox.style.left = (ox + region[0] / sx) + "px";
  regionBox.style.top = (oy + region[1] / sy) + "px";
  regionBox.style.width = (region[2] / sx) + "px";
  regionBox.style.height = (region[3] / sy) + "px";
  regionBox.classList.remove("hidden");
}
window.addEventListener("resize", syncRegionBox);

// 把显示像素的框写回 region（原始px）
function commitRegionFromBox() {
  const rect = video.getBoundingClientRect();
  const { sx, sy, ox, oy } = scaleToOrig();
  const left = parseFloat(regionBox.style.left) - ox;
  const top = parseFloat(regionBox.style.top) - oy;
  region = [
    Math.round(left * sx), Math.round(top * sy),
    Math.round(parseFloat(regionBox.style.width) * sx),
    Math.round(parseFloat(regionBox.style.height) * sy),
  ];
  $("regionInfo").textContent = "可拖动调整，或重新框选";
  refreshOcrButton();
}

// --- 在 overlay 上拖一个新框 ---
overlay.addEventListener("mousedown", (e) => {
  if (!regionMode) return;
  const rect = video.getBoundingClientRect();
  drag = { x0: e.clientX - rect.left, y0: e.clientY - rect.top };
});
window.addEventListener("mousemove", (e) => {
  if (!drag) return;
  const rect = video.getBoundingClientRect();
  const x1 = e.clientX - rect.left, y1 = e.clientY - rect.top;
  drawBox(Math.min(drag.x0, x1), Math.min(drag.y0, y1), Math.abs(x1 - drag.x0), Math.abs(y1 - drag.y0));
});
window.addEventListener("mouseup", () => {
  if (!drag) return;
  drag = null;
  const w = parseFloat(regionBox.style.width), h = parseFloat(regionBox.style.height);
  if (w < 6 || h < 6) { if (!region) regionBox.classList.add("hidden"); else syncRegionBox(); return; }
  commitRegionFromBox();
});
function drawBox(x, y, w, h) {
  regionBox.classList.remove("hidden");
  regionBox.style.left = x + "px";
  regionBox.style.top = y + "px";
  regionBox.style.width = w + "px";
  regionBox.style.height = h + "px";
}

// --- 已有框：8 手柄缩放 + 框体平移 ---
regionBox.addEventListener("mousedown", (e) => {
  e.stopPropagation();   // 不要触发 overlay 画新框
  const rect = video.getBoundingClientRect();
  const handle = e.target.classList.contains("handle") ? [...e.target.classList].find((c) => c !== "handle") : null;
  edit = {
    handle,
    mx: e.clientX, my: e.clientY,
    left: parseFloat(regionBox.style.left), top: parseFloat(regionBox.style.top),
    w: parseFloat(regionBox.style.width), h: parseFloat(regionBox.style.height),
    rect,
  };
  regionBox.classList.add("dragging");
});
window.addEventListener("mousemove", (e) => {
  if (!edit) return;
  const dx = e.clientX - edit.mx, dy = e.clientY - edit.my;
  let { left, top, w, h } = edit;
  const H = edit.handle;
  if (!H) { left += dx; top += dy; }     // 平移
  else {
    if (H.includes("w")) { left += dx; w -= dx; }
    if (H.includes("e")) { w += dx; }
    if (H.includes("n")) { top += dy; h -= dy; }
    if (H.includes("s")) { h += dy; }
  }
  // 防翻转
  if (w < 12) { if (H && H.includes("w")) left = edit.left + edit.w - 12; w = 12; }
  if (h < 12) { if (H && H.includes("n")) top = edit.top + edit.h - 12; h = 12; }
  // 限制在视频显示区内
  left = Math.max(0, Math.min(left, edit.rect.width - w));
  top = Math.max(0, Math.min(top, edit.rect.height - h));
  regionBox.style.left = left + "px"; regionBox.style.top = top + "px";
  regionBox.style.width = w + "px"; regionBox.style.height = h + "px";
});
window.addEventListener("mouseup", () => {
  if (!edit) return;
  edit = null;
  regionBox.classList.remove("dragging");
  commitRegionFromBox();
});

// ---------- 功能二：区域 OCR ----------
$("ocrBtn").onclick = async () => {
  if (!region) return;
  const restore = beginBtn($("ocrBtn"), "识别中…");
  setStatus("正在识别区域…", true);
  try {
    const r = await fetch("/ocr_region", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...(currentVideoId ? { id: currentVideoId } : { video: currentVideoPath }),
        region, fps: 2.0, min_score: 0.5,
      }),
    });
    if (!r.ok) throw new Error(await r.text());
    const data = await r.json();
    renderOcr(data);
    setStatus(`识别完成：${data.frames} 帧，${data.events.length} 条事件`);
  } catch (e) {
    setStatus("识别失败：" + e.message, false, true);
  } finally {
    restore();
  }
};

function renderOcr(data) {
  const el = $("ocrResult");
  el.className = "ocr-result";
  el.innerHTML = "";
  lastEvtIndex = -1;

  // 文本事件
  const evs = document.createElement("div");
  const h = document.createElement("h3");
  h.textContent = `文本事件（去重，${data.events.length} 条）`;
  evs.appendChild(h);
  if (!data.events.length) {
    const m = document.createElement("div");
    m.className = "empty-hint"; m.textContent = "未识别到文本";
    evs.appendChild(m);
  }
  data.events.forEach((e) => {
    const d = document.createElement("div");
    d.className = "evt";
    d.dataset.first = e.first_seen;
    d.dataset.last = e.last_seen;
    const t = document.createElement("span");
    t.className = "t";
    t.textContent = `${fmt(e.first_seen * 1000)}~${fmt(e.last_seen * 1000)}`;
    d.append(t, document.createTextNode(e.text));
    d.onclick = () => { seekTo(e.first_seen); flash(d); };
    evs.appendChild(d);
  });
  el.appendChild(evs);

  // 数字时间序列 -> 折线图
  if (data.numbers && data.numbers.length) {
    const h3 = document.createElement("h3");
    h3.textContent = "数字时间序列";
    el.appendChild(h3);
    el.appendChild(buildChart(data.numbers));

    // 可折叠明细表
    const det = document.createElement("details");
    det.className = "detail";
    const sum = document.createElement("summary");
    sum.textContent = "明细";
    det.appendChild(sum);
    data.numbers.forEach((p) => {
      const d = document.createElement("div");
      d.className = "evt";
      const t = document.createElement("span");
      t.className = "t"; t.textContent = fmt(p.time * 1000);
      d.append(t, document.createTextNode(p.value));
      d.onclick = () => { seekTo(p.time); };
      det.appendChild(d);
    });
    el.appendChild(det);
  }
}

// ---------- inline SVG 折线图 ----------
function buildChart(numbers) {
  const W = 320, Hh = 120, padL = 6, padR = 6, padT = 12, padB = 14;
  const wrap = document.createElement("div");
  wrap.className = "chart";
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${Hh}`);
  svg.setAttribute("preserveAspectRatio", "none");

  const times = numbers.map((p) => p.time);
  const vals = numbers.map((p) => Number(p.value));
  const tMin = Math.min(...times), tMax = Math.max(...times);
  const vMin = Math.min(...vals), vMax = Math.max(...vals);
  const tSpan = tMax - tMin || 1, vSpan = vMax - vMin || 1;
  const X = (t) => padL + ((t - tMin) / tSpan) * (W - padL - padR);
  const Y = (v) => padT + (1 - (v - vMin) / vSpan) * (Hh - padT - padB);

  // 基线
  const base = document.createElementNS(NS, "line");
  base.setAttribute("class", "axis");
  base.setAttribute("x1", padL); base.setAttribute("x2", W - padR);
  base.setAttribute("y1", Hh - padB); base.setAttribute("y2", Hh - padB);
  svg.appendChild(base);

  const pts = numbers.map((p) => `${X(p.time).toFixed(1)},${Y(Number(p.value)).toFixed(1)}`);
  // 面积
  const area = document.createElementNS(NS, "path");
  area.setAttribute("class", "area");
  area.setAttribute("d", `M${pts[0]} L${pts.join(" L")} L${X(tMax).toFixed(1)},${Hh - padB} L${X(tMin).toFixed(1)},${Hh - padB} Z`);
  svg.appendChild(area);
  // 折线
  const line = document.createElementNS(NS, "path");
  line.setAttribute("class", "line");
  line.setAttribute("d", `M${pts.join(" L")}`);
  svg.appendChild(line);

  const tip = document.createElement("div");
  tip.className = "chart-tip";

  numbers.forEach((p) => {
    const cx = X(p.time), cy = Y(Number(p.value));
    const dot = document.createElementNS(NS, "circle");
    dot.setAttribute("class", "dot");
    dot.setAttribute("cx", cx); dot.setAttribute("cy", cy); dot.setAttribute("r", "3");
    dot.addEventListener("mouseenter", () => {
      tip.textContent = `${fmt(p.time * 1000)} · ${p.value}`;
      tip.style.left = (cx / W * 100) + "%";
      tip.style.top = (cy / Hh * 100) + "%";
      tip.classList.add("show");
    });
    dot.addEventListener("mouseleave", () => tip.classList.remove("show"));
    dot.addEventListener("click", () => seekTo(p.time));
    svg.appendChild(dot);
  });

  wrap.append(svg, tip);
  return wrap;
}

// ---------- 键盘快捷键 ----------
function isTyping() {
  const a = document.activeElement;
  return a && (a.tagName === "INPUT" || a.tagName === "TEXTAREA" || a.isContentEditable);
}
document.addEventListener("keydown", (e) => {
  if (isTyping()) return;
  if (libraryView && !libraryView.classList.contains("hidden")) return; // 库视图不接管播放快捷键
  if (e.code === "Space" && hasVideo()) { e.preventDefault(); togglePlay(); return; }
  if (e.key === "r" || e.key === "R") { e.preventDefault(); $("regionModeBtn").onclick(); return; }
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    const lis = [...$("cueList").querySelectorAll("li[data-index]")];
    if (!lis.length) return;
    if (document.activeElement !== $("cueList") && !$("cueList").contains(document.activeElement) && lastActiveIndex < 0) return;
    e.preventDefault();
    let i = lastActiveIndex;
    i = e.key === "ArrowDown" ? Math.min(lis.length - 1, i + 1) : Math.max(0, i - 1);
    const c = cues[i];
    if (c) { seekTo(c.begin_time / 1000); flash(lis[i]); }
  }
});
$("cueList").tabIndex = 0;

// ---------- 设置面板：DashScope API Key ----------
const settingsModal = $("settingsModal");

function setSettingsMsg(msg, kind) {
  const el = $("settingsMsg");
  el.textContent = msg || "";
  el.className = "settings-msg" + (kind ? " " + kind : "");
}

async function refreshApiKeyState() {
  const el = $("apiKeyState");
  try {
    const r = await fetch("/config");
    const d = await r.json();
    if (d.has_api_key) {
      el.textContent = `已配置（${d.api_key_masked || "已保存"}）`;
      el.className = "field-hint ok";
    } else {
      el.textContent = "尚未配置";
      el.className = "field-hint warn";
    }
  } catch {
    el.textContent = "无法读取配置";
    el.className = "field-hint warn";
  }
}

function openSettings() {
  settingsModal.classList.remove("hidden");
  setSettingsMsg("");
  $("apiKeyInput").value = "";            // 不回填明文 key
  $("apiKeyInput").type = "password";
  refreshApiKeyState();
  setTimeout(() => $("apiKeyInput").focus(), 30);
}
function closeSettings() {
  settingsModal.classList.add("hidden");
}
$("settingsBtn").onclick = openSettings;
$("settingsClose").onclick = closeSettings;
$("settingsBackdrop").onclick = closeSettings;
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !settingsModal.classList.contains("hidden")) closeSettings();
});

$("apiKeyReveal").onclick = () => {
  const inp = $("apiKeyInput");
  inp.type = inp.type === "password" ? "text" : "password";
};

async function saveApiKey() {
  const key = $("apiKeyInput").value.trim();
  if (!key) { setSettingsMsg("请输入 API Key 再保存", "err"); return false; }
  const restore = beginBtn($("apiKeySave"), "保存中…");
  try {
    const r = await fetch("/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dashscope_api_key: key }),
    });
    if (!r.ok) throw new Error(await r.text());
    setSettingsMsg("已保存", "ok");
    $("apiKeyInput").value = "";
    await refreshApiKeyState();
    return true;
  } catch (e) {
    setSettingsMsg("保存失败：" + e.message, "err");
    return false;
  } finally {
    restore();
  }
}
$("apiKeySave").onclick = saveApiKey;

$("apiKeyTest").onclick = async () => {
  // 优先用输入框里的（可能未保存）key 测试；为空则测已保存的
  const typed = $("apiKeyInput").value.trim();
  const restore = beginBtn($("apiKeyTest"), "测试中…");
  setSettingsMsg("正在测试连接…", "");
  try {
    const r = await fetch("/config/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(typed ? { dashscope_api_key: typed } : {}),
    });
    const d = await r.json();
    setSettingsMsg(d.message || (d.ok ? "连接成功" : "连接失败"), d.ok ? "ok" : "err");
  } catch (e) {
    setSettingsMsg("测试失败：" + e.message, "err");
  } finally {
    restore();
  }
};

// ---------- 启动：默认进视频库首页 ----------
loadLibrary();
