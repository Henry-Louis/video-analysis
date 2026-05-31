"""功能二：区域 OCR（本地 PaddleOCR 中文）。

- get_ocr / ocr_image：单图识别（按置信度过滤）
- ocr_region_over_time：对视频某区域按固定间隔逐帧识别
- dedupe_lines：跨帧重复文本合并成事件（弹幕去重）
- track_numbers：从识别文本抽数字，构造时间序列（在线人数等）
"""
import re

from .media import extract_region_frames

_ocr = None


def get_ocr(lang: str = "ch"):
    """PaddleOCR 单例（首次创建会加载模型）。"""
    global _ocr
    if _ocr is None:
        from paddleocr import PaddleOCR
        _ocr = PaddleOCR(
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            lang=lang,
        )
    return _ocr


def ocr_image(image_path: str, min_score: float = 0.6) -> list:
    """OCR 单张图片，返回 [(text, score), ...]，按置信度过滤。"""
    out = []
    for res in get_ocr().predict(image_path):
        texts = res["rec_texts"] if "rec_texts" in res else []
        scores = res["rec_scores"] if "rec_scores" in res else []
        for t, s in zip(texts, scores):
            t = (t or "").strip()
            if t and s >= min_score:
                out.append((t, float(s)))
    return out


def ocr_region_over_time(video_path, region, out_dir, fps: float = 2.0,
                         min_score: float = 0.6) -> list:
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
