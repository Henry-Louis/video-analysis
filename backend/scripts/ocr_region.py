"""功能二 端到端：对视频框选区域定时 OCR，输出去重事件 + 数字时间序列。

用法:
    python backend/scripts/ocr_region.py <video> --region X Y W H [--fps 2] [--min-score 0.6]
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..")
sys.path.insert(0, BACKEND)

from app.ocr import ocr_region_over_time, dedupe_lines, track_numbers  # noqa: E402


def fmt(t: float) -> str:
    m, s = divmod(t, 60)
    return f"{int(m):02d}:{s:05.2f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--region", nargs=4, type=int, metavar=("X", "Y", "W", "H"),
                    required=True, help="框选区域：左上角 X Y 与宽高 W H")
    ap.add_argument("--fps", type=float, default=2.0, help="每秒抽帧数，默认 2（每 0.5s）")
    ap.add_argument("--min-score", type=float, default=0.6, help="置信度阈值")
    args = ap.parse_args()

    base = os.path.splitext(os.path.basename(args.video))[0]
    frames_dir = os.path.join(BACKEND, "..", "work", base + "_frames")

    print(f"[*] 区域 {tuple(args.region)}，每 {1 / args.fps:.2f}s 一帧 OCR ...")
    timeline = ocr_region_over_time(args.video, tuple(args.region), frames_dir,
                                    fps=args.fps, min_score=args.min_score)
    print(f"[*] 共 {len(timeline)} 帧\n")

    events = dedupe_lines(timeline)
    print(f"=== 去重后文本事件（{len(events)} 条）===")
    for e in events:
        print(f"  [{fmt(e['first_seen'])}~{fmt(e['last_seen'])}] "
              f"({e['frames']}帧 {e['score']:.2f})  {e['text']}")

    nums = track_numbers(timeline)
    if nums:
        print(f"\n=== 数字时间序列（{len(nums)} 点）===")
        for t, v, raw in nums:
            print(f"  {fmt(t)}  -> {v}   (原文: {raw})")


if __name__ == "__main__":
    main()
