"""视频库：把本地视频导入到用户目录下的 library/，统一管理与分析缓存。

目录结构（复用 config 的用户配置目录，VA_CONFIG_DIR 或默认）：
    <config_dir>/library/<id>/
        source.<ext>      导入时拷贝进来的视频原文件
        thumb.jpg         ffmpeg 抽的一帧缩略图（宽约 320）
        meta.json         元数据（见下）
        results/
            subtitles.json  /transcribe 的结果缓存
            heat.json       /ocr_region 的结果缓存

meta.json 字段：
    id            库内唯一 id（时间戳 + 随机后缀，不含路径分隔符）
    displayName   展示名（默认取原文件名去扩展名，可改名）
    originalName  导入时的原始文件名（含扩展名）
    importedAt    导入时间（毫秒时间戳）
    durationMs    时长（毫秒；探测失败为 None）
    width/height  视频宽高（探测失败为 None）

对外提供：
    import_video(src, *, display_name=None) -> dict   导入并返回 meta
    list_videos() -> list[dict]                       全部 meta（importedAt 倒序）
    get(id) -> dict | None                            单个 meta
    rename(id, name) -> dict | None                   改 displayName，返回新 meta
    delete(id) -> bool                                删整个 <id> 目录
    video_path(id) -> str | None                      source.<ext> 绝对路径
    thumb_path(id) -> str | None                      thumb.jpg 绝对路径（不存在返回 None）
    save_result(id, kind, data) -> None               写 results/<kind>.json
    load_result(id, kind) -> dict                     读 results/<kind>.json（无则 {}）
"""
import glob
import json
import os
import secrets
import shutil
import subprocess
import time

from . import config as cfg
from .media import _probe, ffmpeg_bin

# 允许导入的视频扩展名（小写，含点）
_VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".flv", ".ts", ".wmv"}
# 结果缓存的合法 kind -> 文件名
_RESULT_FILES = {"subtitles": "subtitles.json", "heat": "heat.json"}
_THUMB_WIDTH = 320


def library_dir() -> str:
    """返回库根目录 <config_dir>/library（必要时创建）。"""
    d = os.path.join(cfg.config_dir(), "library")
    os.makedirs(d, exist_ok=True)
    return d


def _entry_dir(vid: str) -> str:
    return os.path.join(library_dir(), vid)


def _meta_path(vid: str) -> str:
    return os.path.join(_entry_dir(vid), "meta.json")


def _results_dir(vid: str) -> str:
    d = os.path.join(_entry_dir(vid), "results")
    os.makedirs(d, exist_ok=True)
    return d


def _gen_id() -> str:
    """生成库内 id：毫秒时间戳 + 随机后缀，保证唯一且不含路径分隔符。"""
    return f"{int(time.time() * 1000)}_{secrets.token_hex(4)}"


def _read_meta(vid: str) -> dict | None:
    path = _meta_path(vid)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _write_json(path: str, data) -> None:
    """原子写 JSON，避免并发/崩溃留下半截文件。"""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _source_path(vid: str) -> str | None:
    """库内视频原文件路径（按 source.* 匹配，取第一个）。"""
    hits = sorted(glob.glob(os.path.join(_entry_dir(vid), "source.*")))
    return hits[0] if hits else None


def _make_thumb(src: str, out_jpg: str, width: int = _THUMB_WIDTH) -> bool:
    """抽一帧缩略图（缩到指定宽、高自适应保持比例）；成功返回 True。"""
    try:
        cmd = [
            ffmpeg_bin(), "-y", "-loglevel", "error",
            "-i", str(src),
            "-vf", f"scale={int(width)}:-2",
            "-frames:v", "1",
            str(out_jpg),
        ]
        subprocess.run(cmd, check=True)
        return os.path.isfile(out_jpg)
    except (OSError, subprocess.CalledProcessError):
        return False


def import_video(src: str, *, display_name: str | None = None) -> dict:
    """把本地视频 src 拷贝进库，抽缩略图、探测时长/宽高、写 meta，返回 meta。"""
    if not os.path.isfile(src):
        raise FileNotFoundError(f"视频不存在: {src}")
    ext = os.path.splitext(src)[1].lower()
    if ext not in _VIDEO_EXTS:
        raise ValueError(f"不支持的视频格式: {ext or '(无扩展名)'}")

    vid = _gen_id()
    entry = _entry_dir(vid)
    os.makedirs(entry, exist_ok=True)
    try:
        dst = os.path.join(entry, "source" + ext)
        shutil.copy2(src, dst)

        _make_thumb(dst, os.path.join(entry, "thumb.jpg"))
        duration_ms, width, height = _probe(dst)  # 一趟 ffmpeg 取时长+宽高，不依赖 ffprobe

        original_name = os.path.basename(src)
        name = (display_name or "").strip() or os.path.splitext(original_name)[0]
        meta = {
            "id": vid,
            "displayName": name,
            "originalName": original_name,
            "importedAt": int(time.time() * 1000),
            "durationMs": duration_ms,
            "width": width,
            "height": height,
        }
        _write_json(_meta_path(vid), meta)
        return meta
    except Exception:
        # 导入中途失败：清掉半截目录，避免库里留下脏条目
        shutil.rmtree(entry, ignore_errors=True)
        raise


def list_videos() -> list[dict]:
    """返回库内全部视频的 meta，按 importedAt 倒序（新导入在前）。"""
    root = library_dir()
    out = []
    for name in os.listdir(root):
        if not os.path.isdir(os.path.join(root, name)):
            continue
        meta = _read_meta(name)
        if meta:
            out.append(meta)
    out.sort(key=lambda m: m.get("importedAt", 0), reverse=True)
    return out


def get(vid: str) -> dict | None:
    """返回单个视频的 meta；不存在返回 None。"""
    return _read_meta(vid)


def rename(vid: str, name: str) -> dict | None:
    """改 displayName 并写回，返回新 meta；视频不存在返回 None。"""
    meta = _read_meta(vid)
    if meta is None:
        return None
    meta["displayName"] = (name or "").strip() or meta.get("displayName", "")
    _write_json(_meta_path(vid), meta)
    return meta


def delete(vid: str) -> bool:
    """删除整个 <id> 目录；存在并删除成功返回 True，否则 False。"""
    entry = _entry_dir(vid)
    if not os.path.isdir(entry):
        return False
    shutil.rmtree(entry, ignore_errors=True)
    return not os.path.isdir(entry)


def video_path(vid: str) -> str | None:
    """返回库内视频原文件的绝对路径；不存在返回 None。"""
    if _read_meta(vid) is None:
        return None
    p = _source_path(vid)
    return os.path.abspath(p) if p else None


def thumb_path(vid: str) -> str | None:
    """返回缩略图绝对路径；不存在返回 None。"""
    p = os.path.join(_entry_dir(vid), "thumb.jpg")
    return os.path.abspath(p) if os.path.isfile(p) else None


def save_result(vid: str, kind: str, data) -> None:
    """把分析结果写到 results/<kind>.json（kind 限 subtitles/heat）。"""
    if kind not in _RESULT_FILES:
        raise ValueError(f"未知的结果类型: {kind}")
    _write_json(os.path.join(_results_dir(vid), _RESULT_FILES[kind]), data)


def load_result(vid: str, kind: str) -> dict:
    """读 results/<kind>.json；无文件或损坏返回 {}。"""
    if kind not in _RESULT_FILES:
        raise ValueError(f"未知的结果类型: {kind}")
    path = os.path.join(_entry_dir(vid), "results", _RESULT_FILES[kind])
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}
