"""功能一 端到端：视频 → 字幕 (SRT / VTT)。

用法:
    python backend/scripts/transcribe.py <video> [-o 输出名]
"""
import argparse
import os
import sys

from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..")
sys.path.insert(0, BACKEND)
load_dotenv(os.path.join(BACKEND, ".env"))

from app.media import extract_audio, burn_subtitles  # noqa: E402
from app.asr import transcribe               # noqa: E402
from app.subtitle import sentences_to_cues, to_srt, to_vtt  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("-o", "--out", help="输出文件名（不含扩展名），默认与视频同名")
    ap.add_argument("-b", "--burn", action="store_true", help="同时把字幕烧进视频，输出 *_subbed.mp4")
    args = ap.parse_args()

    base = args.out or os.path.splitext(os.path.basename(args.video))[0]
    out_dir = os.path.join(BACKEND, "..", "work")
    os.makedirs(out_dir, exist_ok=True)
    wav = os.path.join(out_dir, base + ".wav")

    print(f"[1/3] 抽音轨 → {wav}")
    extract_audio(args.video, wav)

    print("[2/3] 语音识别（Paraformer）...")
    sentences = transcribe(wav)

    print("[3/3] 切分字幕...")
    cues = sentences_to_cues(sentences)
    srt_path = os.path.join(out_dir, base + ".srt")
    vtt_path = os.path.join(out_dir, base + ".vtt")
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(to_srt(cues))
    with open(vtt_path, "w", encoding="utf-8") as f:
        f.write(to_vtt(cues))

    subbed_path = None
    if args.burn:
        print("[+] 烧录字幕到视频...")
        subbed_path = os.path.join(out_dir, base + "_subbed.mp4")
        burn_subtitles(args.video, srt_path, subbed_path)

    print(f"\n完成！共 {len(cues)} 条字幕")
    print(f"  SRT: {srt_path}")
    print(f"  VTT: {vtt_path}")
    if subbed_path:
        print(f"  烧录视频: {subbed_path}")
    print()
    print("-" * 40)
    print(to_srt(cues))


if __name__ == "__main__":
    main()
