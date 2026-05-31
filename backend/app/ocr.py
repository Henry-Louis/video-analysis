"""功能二：区域 OCR（本机 macOS Vision，零依赖、离线）。

- ocr_image：单图识别（调用 native/vision-ocr 二进制，按置信度过滤）
- ocr_region_over_time：对视频某区域按固定间隔逐帧识别
- dedupe_lines：跨帧重复文本合并成事件（弹幕去重）
- track_numbers：从识别文本抽数字，构造时间序列（在线人数等）

OCR 引擎说明：改用系统 Vision 框架（见 native/vision-ocr/main.swift），
通过 swiftc 编译出的 vision-ocr 二进制识别单图，stdout 输出
JSON 数组 [{text, confidence, x, y, w, h}]（confidence 0~1，bbox 归一化）。
"""
import json
import os
import re
import shutil
import subprocess
import threading

from .media import extract_region_frames

# repo 根：backend/app/ocr.py -> 上两级
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.normpath(os.path.join(_HERE, "..", ".."))
_VISION_DIR = os.path.join(_ROOT, "native", "vision-ocr")
_VISION_BIN_DEFAULT = os.path.join(_VISION_DIR, "vision-ocr")
_VISION_SRC = os.path.join(_VISION_DIR, "main.swift")

_bin_lock = threading.Lock()
_resolved_bin = None


def _vision_ocr_bin() -> str:
    """定位 vision-ocr 二进制。

    1) 环境变量 VA_VISION_OCR；
    2) repo 根的 native/vision-ocr/vision-ocr；
    3) 若二进制不存在但 main.swift 在且系统有 swiftc，则自动编译一次再用。
    """
    global _resolved_bin
    if _resolved_bin and os.path.exists(_resolved_bin):
        return _resolved_bin

    with _bin_lock:
        if _resolved_bin and os.path.exists(_resolved_bin):
            return _resolved_bin

        env_bin = os.environ.get("VA_VISION_OCR")
        if env_bin:
            if not os.path.exists(env_bin):
                raise FileNotFoundError(
                    f"VA_VISION_OCR 指向的二进制不存在: {env_bin}"
                )
            _resolved_bin = env_bin
            return _resolved_bin

        if os.path.exists(_VISION_BIN_DEFAULT):
            _resolved_bin = _VISION_BIN_DEFAULT
            return _resolved_bin

        # 自动编译一次
        if not os.path.exists(_VISION_SRC):
            raise FileNotFoundError(
                f"找不到 vision-ocr 二进制，且源码缺失: {_VISION_SRC}"
            )
        swiftc = shutil.which("swiftc")
        if not swiftc:
            raise FileNotFoundError(
                "找不到 vision-ocr 二进制，且系统无 swiftc 无法自动编译。"
                f"请先编译: swiftc -O -o {_VISION_BIN_DEFAULT} {_VISION_SRC}"
            )
        subprocess.run(
            [swiftc, "-O", "-o", _VISION_BIN_DEFAULT, _VISION_SRC],
            check=True,
        )
        if not os.path.exists(_VISION_BIN_DEFAULT):
            raise RuntimeError("vision-ocr 自动编译后仍未生成二进制")
        _resolved_bin = _VISION_BIN_DEFAULT
        return _resolved_bin


def ocr_image(image_path: str, min_score: float = 0.5) -> list:
    """OCR 单张图片，返回 [(text, score), ...]，按置信度过滤。

    底层调用本机 Vision（native/vision-ocr 二进制）：subprocess 运行 → 解析
    JSON → 过滤空文本与低于 min_score 的结果 → 返回 [(text, float(score))]。
    """
    proc = subprocess.run(
        [_vision_ocr_bin(), str(image_path)],
        check=True, capture_output=True,
    )
    raw = proc.stdout.decode("utf-8").strip()
    if not raw:
        return []
    items = json.loads(raw)
    out = []
    for it in items:
        text = (it.get("text") or "").strip()
        score = float(it.get("confidence", 0.0))
        if text and score >= min_score:
            out.append((text, score))
    return out


def ocr_region_over_time(video_path, region, out_dir, fps: float = 2.0,
                         min_score: float = 0.5) -> list:
    """对视频某区域每 1/fps 秒 OCR 一次，返回 [{time, lines:[(text, score)]}]。"""
    frames = extract_region_frames(video_path, out_dir, region=region, fps=fps)
    timeline = []
    for _idx, t, path in frames:
        timeline.append({"time": round(t, 3), "lines": ocr_image(path, min_score)})
    return timeline


# 全角标点 → 半角，用于"同一条文本"的归一化判断（不影响展示文字）
_PUNC_MAP = str.maketrans("，。！？；：、（）”“’‘", ",.!?;:,()\"\"''")


def _norm_key(text: str) -> str:
    """归一化文本作为去重键：统一标点、去空格、去首尾标点、英文小写。"""
    t = text.translate(_PUNC_MAP)
    t = re.sub(r"\s+", "", t)
    return t.strip(" ,.!?;:…\"'").lower()


def dedupe_lines(timeline, max_gap_s: float = 1.5, drop_noise: bool = True) -> list:
    """把跨帧重复出现的同一文本合并成事件。

    弹幕滚动时同一条会连续出现在多帧里 —— 用归一化键合并为一个事件并记录首末时间，
    展示时保留置信度最高的那次文字。返回 [{text, first_seen, last_seen, frames, score}]。
    """
    events = []
    active = {}  # norm_key -> 当前事件
    for frame in timeline:
        t = frame["time"]
        seen_now = set()
        for text, score in frame["lines"]:
            key = _norm_key(text)
            if not key:
                continue
            if drop_noise and len(key) < 2 and score < 0.85:
                continue  # 丢弃单字符低置信噪声
            seen_now.add(key)
            ev = active.get(key)
            if ev and (t - ev["last_seen"]) <= max_gap_s:
                ev["last_seen"] = t
                ev["frames"] += 1
                if score > ev["score"]:
                    ev["score"], ev["text"] = score, text  # 保留最高置信版本
            else:
                ev = {"text": text, "first_seen": t, "last_seen": t,
                      "frames": 1, "score": score, "_key": key}
                active[key] = ev
                events.append(ev)
        for k in [x for x, e in active.items()
                  if x not in seen_now and (t - e["last_seen"]) > max_gap_s]:
            del active[k]
    for e in events:
        e.pop("_key", None)
    return events


def track_numbers(timeline) -> list:
    """从每帧文本抽数字，构造时间序列 [(time, value, raw)]。

    默认取画面里最大的数字（在线人数常是最显眼/最大的数）；真实素材到手后可调策略。
    """
    series = []
    for frame in timeline:
        cands = []
        for text, _s in frame["lines"]:
            for m in re.findall(r"\d[\d,]*", text):
                cands.append((int(m.replace(",", "")), text))
        if cands:
            v, raw = max(cands, key=lambda x: x[0])
            series.append((frame["time"], v, raw))
    return series
