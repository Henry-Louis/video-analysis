"""功能一：语音识别（阿里云百炼 Paraformer）。

返回结构（每个 sentence）：
    {begin_time, end_time, text, words: [{begin_time, end_time, text, punctuation}, ...]}
时间单位均为毫秒；字级时间戳默认开启。
"""
import os
from http import HTTPStatus

import dashscope
from dashscope.audio.asr import Recognition

from app.config import get_api_key


def _ensure_key() -> None:
    # 优先用界面配置（用户目录的 config.json），为空再回退环境变量（向后兼容）
    key = get_api_key() or os.getenv("DASHSCOPE_API_KEY")
    if not key:
        raise RuntimeError("缺少 DashScope API Key（请在设置中配置，或设环境变量 DASHSCOPE_API_KEY）")
    dashscope.api_key = key


def transcribe(
    audio_path: str,
    model: str = "paraformer-realtime-v2",
    sample_rate: int = 16000,
    language_hints=("zh", "en"),
) -> list:
    """识别本地 WAV，返回句子列表（含字级时间戳）。"""
    _ensure_key()
    recognition = Recognition(
        model=model,
        format="wav",
        sample_rate=sample_rate,
        language_hints=list(language_hints),
        callback=None,
    )
    result = recognition.call(str(audio_path))
    if result.status_code != HTTPStatus.OK:
        raise RuntimeError(
            f"ASR 失败: status={result.status_code} msg={getattr(result, 'message', '')}"
        )
    sentences = result.get_sentence() or []
    if isinstance(sentences, dict):
        sentences = [sentences]
    return sentences
