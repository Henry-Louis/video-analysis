"""视频/音频处理：基于系统已安装的 ffmpeg 二进制。"""
import glob
import os
import shutil
import subprocess

# 带 libass 的 ffmpeg（烧录字幕需要）。Homebrew 的 ffmpeg-full 为 keg-only，
# 装在此固定路径；常规 ffmpeg 精简版不含 libass，烧不了字幕。
_FFMPEG_FULL = "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"


def ffmpeg_bin() -> str:
    """优先 FFMPEG_BIN 环境变量，其次 ffmpeg-full（功能全、含 libass），最后 PATH。"""
    env = os.environ.get("FFMPEG_BIN")
    if env:
        return env
    if os.path.exists(_FFMPEG_FULL):
        return _FFMPEG_FULL
    return shutil.which("ffmpeg") or "ffmpeg"


def ffprobe_bin() -> str:
    return shutil.which("ffprobe") or "ffprobe"


def extract_audio(video_path: str, out_wav: str, sample_rate: int = 16000) -> str:
    """从视频抽取单声道 16k WAV，供 Paraformer 识别使用。"""
    cmd = [
        ffmpeg_bin(), "-y", "-loglevel", "error",
        "-i", str(video_path),
        "-vn",                      # 不要视频
        "-ar", str(sample_rate),    # 采样率
        "-ac", "1",                 # 单声道
        str(out_wav),
    ]
    subprocess.run(cmd, check=True)
    return out_wav


def probe_duration(path: str) -> float:
    """返回媒体时长（秒）。"""
    out = subprocess.run(
        [ffprobe_bin(), "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(out.stdout.strip() or 0.0)


def burn_subtitles(
    video_path: str,
    subtitle_path: str,
    out_path: str,
    font: str = "PingFang SC",
    fontsize: int = 16,
    margin_v: int = 45,
) -> str:
    """把字幕烧进视频（需要带 libass 的 ffmpeg，如 ffmpeg-full）。

    技巧：cwd 切到字幕所在目录、只用文件名引用，规避 subtitles 滤镜对
    绝对路径中特殊字符的转义问题。force_style 用单引号包裹，避免其中的
    逗号被当成 filtergraph 的滤镜分隔符。
    """
    sub_dir = os.path.dirname(os.path.abspath(subtitle_path)) or "."
    sub_name = os.path.basename(subtitle_path)
    style = f"FontName={font},Fontsize={fontsize},Outline=2,Shadow=0,MarginV={margin_v}"
    vf = f"subtitles=filename='{sub_name}':force_style='{style}'"
    cmd = [
        ffmpeg_bin(), "-y", "-loglevel", "error",
        "-i", os.path.abspath(video_path),
        "-vf", vf,
        "-c:a", "copy",
        os.path.abspath(out_path),
    ]
    subprocess.run(cmd, check=True, cwd=sub_dir)
    return out_path


def extract_region_frames(
    video_path: str,
    out_dir: str,
    region=None,
    fps: float = 2.0,
) -> list:
    """按 fps 抽帧（默认 2，即每 0.5s 一帧），可选裁剪到 region=(x, y, w, h)。

    用一趟 ffmpeg 完成抽帧+裁剪，返回 [(index, time_sec, image_path), ...]。
    """
    os.makedirs(out_dir, exist_ok=True)
    filters = [f"fps={fps}"]
    if region:
        x, y, w, h = region
        filters.append(f"crop={int(w)}:{int(h)}:{int(x)}:{int(y)}")
    pattern = os.path.join(out_dir, "f_%05d.png")
    cmd = [
        ffmpeg_bin(), "-y", "-loglevel", "error",
        "-i", os.path.abspath(video_path),
        "-vf", ",".join(filters),
        pattern,
    ]
    subprocess.run(cmd, check=True)
    frames = sorted(glob.glob(os.path.join(out_dir, "f_*.png")))
    return [(i, i / fps, p) for i, p in enumerate(frames)]
