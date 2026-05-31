"""验证阿里云百炼 Paraformer 语音识别 + 时间戳是否跑通。

用法:
    python backend/scripts/check_asr.py [音频文件路径]

默认识别 /tmp/asr_test.wav。会打印每句的时间戳和字级时间戳。
"""
import os
import sys
import json
from http import HTTPStatus

from dotenv import load_dotenv
import dashscope
from dashscope.audio.asr import Recognition

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, "..", ".env"))

api_key = os.getenv("DASHSCOPE_API_KEY")
if not api_key:
    print("[ERROR] 未找到 DASHSCOPE_API_KEY，请检查 backend/.env")
    sys.exit(1)
dashscope.api_key = api_key

audio = sys.argv[1] if len(sys.argv) > 1 else "/tmp/asr_test.wav"
if not os.path.exists(audio):
    print(f"[ERROR] 音频文件不存在: {audio}")
    sys.exit(1)

print(f"[INFO] 识别文件: {audio}")
print(f"[INFO] key: {api_key[:6]}...{api_key[-4:]}\n")


def fmt(ms):
    if ms is None:
        return "??:??.???"
    s, msec = divmod(int(ms), 1000)
    m, s = divmod(s, 60)
    return f"{m:02d}:{s:02d}.{msec:03d}"


recognition = Recognition(
    model="paraformer-realtime-v2",
    format="wav",
    sample_rate=16000,
    language_hints=["zh"],
    callback=None,
)

result = recognition.call(audio)

if result.status_code != HTTPStatus.OK:
    print(f"[FAIL] status_code={result.status_code} message={getattr(result, 'message', '')}")
    print(repr(result))
    sys.exit(2)

sentences = result.get_sentence()
if sentences is None:
    sentences = []
elif isinstance(sentences, dict):
    sentences = [sentences]

print(f"[OK] 识别成功，共 {len(sentences)} 句：\n")
for s in sentences:
    print(f"[{fmt(s.get('begin_time'))} -> {fmt(s.get('end_time'))}] {s.get('text', '')}")
    words = s.get("words") or []
    if words:
        wstr = " ".join(f"{w.get('text', '')}({w.get('begin_time')}~{w.get('end_time')})" for w in words)
        print(f"    字级: {wstr}")

print("\n[RAW] 第一句原始结构：")
if sentences:
    print(json.dumps(sentences[0], ensure_ascii=False, indent=2))
