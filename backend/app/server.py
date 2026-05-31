"""本地 FastAPI 服务：把功能一/功能二包成 HTTP 接口，并托管前端静态页面。

- GET  /health                  健康检查
- GET  /media?path=...          流式播放本地视频（支持 range/拖动）
- POST /transcribe              功能一：视频 → 字幕 cue（兼容 {id} / 旧 {video}）
- POST /ocr_region              功能二：区域定时 OCR → 去重事件 + 数字时序（兼容 {id} / 旧 {video}）
- GET  /library                 视频库列表
- POST /library/import          导入本地视频进库
- PATCH/DELETE /library/{id}    改名 / 删除
- GET  /library/{id}/thumb      缩略图
- GET  /library/{id}/media      流式返回库内视频（支持 range）
- GET  /library/{id}/result     读取缓存结果（kind=subtitles|heat）
- GET  /                        前端页面（frontend/）
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
from app import config as cfg                                 # noqa: E402
from app import library as lib                                # noqa: E402

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
    id: str | None = None      # 库内视频 id（新）；结果会缓存到 results/subtitles.json
    video: str | None = None   # 本地视频绝对路径（旧）；保持原行为
    burn: bool = False


def _resolve_video(vid: str | None, video: str | None) -> str:
    """统一解析视频路径：优先库内 id，其次旧的本地路径。返回绝对路径。"""
    if vid:
        path = lib.video_path(vid)
        if not path:
            raise HTTPException(404, f"库内视频不存在: {vid}")
        return path
    if video:
        if not os.path.isfile(video):
            raise HTTPException(404, f"视频不存在: {video}")
        return video
    raise HTTPException(400, "需要提供 id 或 video")


@app.post("/transcribe")
def do_transcribe(req: TranscribeReq):
    video = _resolve_video(req.id, req.video)
    base = _base(video)
    wav = os.path.join(WORK, base + ".wav")
    extract_audio(video, wav)
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
        burn_subtitles(video, srt_path, subbed)

    result = {"cues": cues, "srt_path": srt_path, "vtt_path": vtt_path, "subbed_path": subbed}
    if req.id:
        lib.save_result(req.id, "subtitles", result)  # 缓存供再次进入分析视图直接展示
    return result


class OcrReq(BaseModel):
    id: str | None = None      # 库内视频 id（新）；结果会缓存到 results/heat.json
    video: str | None = None   # 本地视频绝对路径（旧）；保持原行为
    region: list[int]          # [x, y, w, h]，原始视频像素坐标
    fps: float = 2.0
    min_score: float = 0.5    # Vision 置信度偏粗，0.5 是有效文本/噪声的甜区


@app.post("/ocr_region")
def do_ocr(req: OcrReq):
    video = _resolve_video(req.id, req.video)
    if len(req.region) != 4:
        raise HTTPException(400, "region 需为 [x, y, w, h]")
    base = _base(video)
    frames_dir = os.path.join(WORK, base + "_frames")
    timeline = ocr_region_over_time(
        video, tuple(req.region), frames_dir, fps=req.fps, min_score=req.min_score,
    )
    events = dedupe_lines(timeline)
    numbers = [{"time": t, "value": v, "raw": r} for t, v, r in track_numbers(timeline)]
    result = {"frames": len(timeline), "events": events, "numbers": numbers}
    if req.id:
        lib.save_result(req.id, "heat", result)  # 缓存供再次进入分析视图直接展示
    return result


# ---------- 视频库：导入拷贝 / 列表 / 改名 / 删除 / 缩略图 / 流式播放 / 结果缓存 ----------


@app.get("/library")
def library_list():
    """返回库内全部视频（按 importedAt 倒序）。"""
    return {"videos": lib.list_videos()}


class ImportReq(BaseModel):
    path: str
    displayName: str | None = None


@app.post("/library/import")
def library_import(req: ImportReq):
    """把本地视频拷贝进库、抽缩略图、探测时长/宽高、写 meta，返回 meta。"""
    try:
        return lib.import_video(req.path, display_name=req.displayName)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


class RenameReq(BaseModel):
    displayName: str


@app.patch("/library/{vid}")
def library_rename(vid: str, req: RenameReq):
    """改 displayName，返回 {ok, ...meta}。"""
    meta = lib.rename(vid, req.displayName)
    if meta is None:
        raise HTTPException(404, f"库内视频不存在: {vid}")
    return {"ok": True, **meta}


@app.delete("/library/{vid}")
def library_delete(vid: str):
    """删整个 <id> 目录。"""
    if not lib.delete(vid):
        raise HTTPException(404, f"库内视频不存在: {vid}")
    return {"ok": True}


@app.get("/library/{vid}/thumb")
def library_thumb(vid: str):
    """返回缩略图 thumb.jpg。"""
    p = lib.thumb_path(vid)
    if not p:
        raise HTTPException(404, f"缩略图不存在: {vid}")
    return FileResponse(p, media_type="image/jpeg")


@app.get("/library/{vid}/media")
def library_media(vid: str):
    """流式返回库内视频原文件（FileResponse 支持 Range，可拖动）。"""
    p = lib.video_path(vid)
    if not p:
        raise HTTPException(404, f"库内视频不存在: {vid}")
    return FileResponse(p)


@app.get("/library/{vid}/result")
def library_result(vid: str, kind: str):
    """返回缓存结果（kind=subtitles|heat），无则返回 {}。"""
    if kind not in ("subtitles", "heat"):
        raise HTTPException(400, "kind 需为 subtitles 或 heat")
    if lib.get(vid) is None:
        raise HTTPException(404, f"库内视频不存在: {vid}")
    return lib.load_result(vid, kind)


# ---------- 设置：API key 存用户目录、界面可配置与测试连接 ----------
# 非密字段白名单：GET /config 时会原样回传这些键（密钥字段永不明文回传）
_PUBLIC_CONFIG_KEYS = ()


def _public_config() -> dict:
    """组装可安全回传的配置：has_api_key + key 尾4位掩码 + 白名单非密字段。"""
    c = cfg.get_config()
    key = cfg.get_api_key()
    out = {"has_api_key": bool(key)}
    if key:
        tail = key[-4:] if len(key) >= 4 else key
        out["api_key_masked"] = "••••" + tail
    for k in _PUBLIC_CONFIG_KEYS:
        if k in c:
            out[k] = c[k]
    return out


class ConfigReq(BaseModel):
    dashscope_api_key: str | None = None


@app.get("/config")
def get_config_route():
    """返回是否已配置 key 及尾4位掩码；绝不明文回传完整 key。"""
    return _public_config()


@app.post("/config")
def post_config_route(req: ConfigReq):
    """合并保存配置并持久化；返回 has_api_key 等非密信息。"""
    patch = {}
    if req.dashscope_api_key is not None:
        # 允许传空串清除已配置的 key
        patch["dashscope_api_key"] = req.dashscope_api_key.strip()
    if patch:
        cfg.save_config(patch)
    return {"ok": True, **_public_config()}


class ConfigTestReq(BaseModel):
    dashscope_api_key: str | None = None  # 可选：用 body 传入的 key 测试（未保存时）


@app.post("/config/test")
def test_config_route(req: ConfigTestReq | None = None):
    """用当前（或 body 传入）的 key 调一次极小的 DashScope 请求验证连通。

    能区分鉴权成功/失败即可：成功（200）或服务可达但鉴权失败（401/InvalidApiKey）。
    """
    body_key = (req.dashscope_api_key or "").strip() if req else ""
    key = body_key or cfg.get_api_key() or os.getenv("DASHSCOPE_API_KEY")
    if not key:
        return {"ok": False, "message": "尚未配置 API Key"}

    try:
        from http import HTTPStatus

        import dashscope
        from dashscope import Generation

        # 极小请求：1 token 输出，仅用于探测鉴权连通
        resp = Generation.call(
            api_key=key,
            model="qwen-turbo",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=1,
            result_format="message",
        )
        if resp.status_code == HTTPStatus.OK:
            return {"ok": True, "message": "连接成功，API Key 有效"}
        # 鉴权类错误：401 或包含 InvalidApiKey 的错误码
        code = getattr(resp, "code", "") or ""
        msg = getattr(resp, "message", "") or ""
        if resp.status_code in (401, 403) or "InvalidApiKey" in str(code) or "Unauthorized" in str(code):
            return {"ok": False, "message": f"API Key 无效或无权限（{code or resp.status_code}）"}
        return {"ok": False, "message": f"连接失败：{code or resp.status_code} {msg}".strip()}
    except Exception as e:  # 网络不通等
        return {"ok": False, "message": f"连接异常：{e}"}


# 前端静态页面（放最后，避免覆盖上面的 API 路由）
if os.path.isdir(FRONTEND):
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
