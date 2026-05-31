"""视频/音频处理：基于可移植的 ffmpeg 二进制（自带，无需 Homebrew/系统装）。

ffmpeg 定位优先级（见 ffmpeg_bin）：
    1) 环境变量 VA_FFMPEG（打包态由 run_server.py 据 sys._MEIPASS 注入）
    2) imageio-ffmpeg 自带的 ffmpeg（macOS arm64，含 libass，可烧字幕）
    3) Homebrew 的 ffmpeg-full（开发机兜底）
    4) PATH 里的 ffmpeg

时长/宽高探测不再依赖外部 ffprobe：用 `ffmpeg -i` 读 stderr 解析 Duration
与首个视频流的 WxH（见 _probe）。ffprobe_bin 仅留作兜底，核心路径不再用它。
"""
import glob
import os
import re
import shutil
import subprocess

# 带 libass 的 ffmpeg（烧录字幕需要）。Homebrew 的 ffmpeg-full 为 keg-only，
# 装在此固定路径；常规 ffmpeg 精简版不含 libass，烧不了字幕。
_FFMPEG_FULL = "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"


def ffmpeg_bin() -> str:
    """定位 ffmpeg：VA_FFMPEG → imageio-ffmpeg 自带 → ffmpeg-full → PATH。

    imageio-ffmpeg 自带的 macOS arm64 ffmpeg 已 --enable-libass，可烧字幕，
    且随 pip 安装/PyInstaller 收集，因此能让打包后的 .app 脱离 Homebrew 运行。
    """
    env = os.environ.get("VA_FFMPEG")
    if env and os.path.exists(env):
        return env
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.exists(exe):
            return exe
    except Exception:
        pass  # 未装 imageio-ffmpeg 时静默回退到下面的兜底
    if os.path.exists(_FFMPEG_FULL):
        return _FFMPEG_FULL
    return shutil.which("ffmpeg") or "ffmpeg"


def ffprobe_bin() -> str:
    """仅作兜底：核心时长/宽高探测已改用 ffmpeg(-i 读 stderr)，见 _probe。"""
    return shutil.which("ffprobe") or "ffprobe"


_DUR_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
# 匹配视频流分辨率：取 "Video:" 行里第一个 WxH（排除如 SAR/DAR 的 a:b）
_DIM_RE = re.compile(r"\b(\d{2,5})x(\d{2,5})\b")


def _probe(path: str) -> tuple[int | None, int | None, int | None]:
    """用 `ffmpeg -i` 读 stderr 解析媒体信息，零外部 ffprobe 依赖。

    返回 (durationMs, width, height)，任一探测失败对应项为 None。
    ffmpeg 仅给 -i 而无输出文件时会以非零码退出并把媒体信息打到 stderr，
    这是预期行为，故不 check=True。
    """
    try:
        proc = subprocess.run(
            [ffmpeg_bin(), "-hide_banner", "-i", str(path)],
            capture_output=True, text=True,
        )
    except OSError:
        return (None, None, None)
    err = proc.stderr or ""

    duration_ms = None
    m = _DUR_RE.search(err)
    if m:
        h, mnt, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
        sec = h * 3600 + mnt * 60 + s
        if sec > 0:
            duration_ms = int(round(sec * 1000))

    width = height = None
    # 只在 "Video:" 流描述行里找分辨率，避免误取其它数字
    for line in err.splitlines():
        if "Video:" in line:
            dm = _DIM_RE.search(line)
            if dm:
                width, height = int(dm.group(1)), int(dm.group(2))
                break

    return (duration_ms, width, height)


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
    """返回媒体时长（秒）；探测失败返回 0.0。用 ffmpeg 解析，不依赖 ffprobe。"""
    duration_ms, _w, _h = _probe(path)
    return (duration_ms / 1000.0) if duration_ms else 0.0


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
