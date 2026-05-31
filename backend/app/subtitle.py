"""把字级时间戳的识别结果切成字幕 cue，并导出 SRT / VTT。

Paraformer 常把一长段返回成一两个「句子」，直接做字幕太长。这里用
字级时间戳 + 标点，把每个句子再切成长度合适、时间轴精确的字幕行。
"""

# 句末强标点：遇到就断行
_STRONG = "。！？!?…"
# 次级标点：行内过长时，在这些标点处断行
_SOFT = "，,、；;：:"


def _char_weight(text: str) -> float:
    """近似显示宽度：中文记 1，ASCII（英文/数字/空格）记 0.5。"""
    return sum(0.5 if ch.isascii() else 1.0 for ch in text)


def segment_words(
    words: list,
    soft_min_chars: float = 7,
    max_duration_ms: int = 6000,
    hard_max_chars: float = 32,
    hard_max_ms: int = 8000,
) -> list:
    """把一个句子的 words 切成多条字幕 cue。

    策略（优先级从高到低）：
      1. 句末强标点（。！？）→ 必断；
      2. 次级标点（，、；）且行长已过舒适下限 soft_min_chars（或时长过长）→ 断；
      3. 没有标点的超长串 → 到安全阈值 hard_max 才强制断（避免在烂位置切）。
    """
    cues: list = []
    cur: list = []
    cur_len = 0.0

    def flush():
        nonlocal cur, cur_len
        if cur:
            text = "".join(
                (w.get("text", "") + (w.get("punctuation", "") or "")) for w in cur
            ).strip()
            if text:
                cues.append({
                    "begin_time": cur[0].get("begin_time", 0),
                    "end_time": cur[-1].get("end_time", 0),
                    "text": text,
                })
        cur = []
        cur_len = 0.0

    for w in words:
        cur.append(w)
        cur_len += _char_weight(w.get("text", ""))
        punc = (w.get("punctuation", "") or "").strip()
        dur = cur[-1].get("end_time", 0) - cur[0].get("begin_time", 0)
        ends_strong = bool(punc) and punc[-1] in _STRONG
        has_soft = bool(punc) and punc[-1] in _SOFT

        if ends_strong:
            flush()                                              # 句末，必断
        elif has_soft and (cur_len >= soft_min_chars or dur >= max_duration_ms):
            flush()                                              # 标点处断（行已够长）
        elif cur_len >= hard_max_chars or dur >= hard_max_ms:
            flush()                                              # 无标点超长串，兜底
    flush()
    return cues


def sentences_to_cues(sentences: list, **kw) -> list:
    """把 ASR 的句子列表整体转成字幕 cue 列表（保留句子间的自然停顿为硬边界）。"""
    cues: list = []
    for s in sentences:
        words = s.get("words") or []
        if words:
            cues.extend(segment_words(words, **kw))
        elif s.get("text"):
            cues.append({
                "begin_time": s.get("begin_time", 0),
                "end_time": s.get("end_time", 0),
                "text": s["text"],
            })
    return cues


def _fmt(ms: int, sep: str) -> str:
    ms = max(0, int(ms))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def to_srt(cues: list) -> str:
    out = []
    for i, c in enumerate(cues, 1):
        out.append(str(i))
        out.append(f"{_fmt(c['begin_time'], ',')} --> {_fmt(c['end_time'], ',')}")
        out.append(c["text"])
        out.append("")
    return "\n".join(out)


def to_vtt(cues: list) -> str:
    out = ["WEBVTT", ""]
    for c in cues:
        out.append(f"{_fmt(c['begin_time'], '.')} --> {_fmt(c['end_time'], '.')}")
        out.append(c["text"])
        out.append("")
    return "\n".join(out)
