"""本地 FastAPI 服务：把功能一/功能二包成 HTTP 接口，并托管前端静态页面。

- GET  /health           健康检查
- GET  /media?path=...   流式播放本地视频（支持 range/拖动）
- POST /transcribe       功能一：视频 → 字幕 cue（可选烧录）
- POST /ocr_region       功能二：区域定时 OCR → 去重事件 + 数字时序
- GET  /                 前端页面（frontend/）
"""
import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..")
ROOT = os.path.join(BACKEND, "..")
WORK = os.path.join(ROOT, "work")
FRONTEND = os.path.join(ROOT, "frontend")
os.makedirs(WORK, exist_ok=True)
load_dotenv(os.path.join(BACKEND, ".env"))

from app.media import extract_audio, burn_subtitles          # noqa: E402
from app.asr import transcribe                                # noqa: E402
from app.subtitle import sentences_to_cues, to_srt, to_vtt    # noqa: E402
from app.ocr import ocr_region_over_time, dedupe_lines, track_numbers  # noqa: E402

app = FastAPI(title="video-analysis")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


def _base(video: str) -> str:
    return os.path.splitext(os.path.basename(video))[0]


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/media")
def media(path: str):
    """流式返回本地媒体文件（FileResponse 支持 Range，可拖动进度）。"""
    if not os.path.isfile(path):
        raise HTTPException(404, f"文件不存在: {path}")
    return FileResponse(path)


class TranscribeReq(BaseModel):
    video: str
    burn: bool = False


@app.post("/transcribe")
def do_transcribe(req: TranscribeReq):
    if not os.path.isfile(req.video):
        raise HTTPException(404, f"视频不存在: {req.video}")
    base = _base(req.video)
    wav = os.path.join(WORK, base + ".wav")
    extract_audio(req.video, wav)
    cues = sentences_to_cues(transcribe(wav))

    srt_path = os.path.join(WORK, base + ".srt")
    vtt_path = os.path.join(WORK, base + ".vtt")
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(to_srt(cues))
    with open(vtt_path, "w", encoding="utf-8") as f:
        f.write(to_vtt(cues))

    subbed = None
    if req.burn:
        subbed = os.path.join(WORK, base + "_subbed.mp4")
        burn_subtitles(req.video, srt_path, subbed)

    return {"cues": cues, "srt_path": srt_path, "vtt_path": vtt_path, "subbed_path": subbed}


class OcrReq(BaseModel):
    video: str
    region: list[int]          # [x, y, w, h]，原始视频像素坐标
    fps: float = 2.0
    min_score: float = 0.7


@app.post("/ocr_region")
def do_ocr(req: OcrReq):
    if not os.path.isfile(req.video):
        raise HTTPException(404, f"视频不存在: {req.video}")
    if len(req.region) != 4:
        raise HTTPException(400, "region 需为 [x, y, w, h]")
    base = _base(req.video)
    frames_dir = os.path.join(WORK, base + "_frames")
    timeline = ocr_region_over_time(
        req.video, tuple(req.region), frames_dir, fps=req.fps, min_score=req.min_score,
    )
    events = dedupe_lines(timeline)
    numbers = [{"time": t, "value": v, "raw": r} for t, v, r in track_numbers(timeline)]
    return {"frames": len(timeline), "events": events, "numbers": numbers}


# 前端静态页面（放最后，避免覆盖上面的 API 路由）
if os.path.isdir(FRONTEND):
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
