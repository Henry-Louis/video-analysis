"""用户级配置：API key 等存到用户目录，界面可改、可持久化。

配置目录优先取环境变量 VA_CONFIG_DIR（Electron 打包/开发都注入 app.getPath('userData')），
否则回退到 macOS 的 ~/Library/Application Support/视频分析/。目录不存在则创建。
配置文件固定为该目录下的 config.json。

对外提供：
    get_config() -> dict                读取完整配置（文件缺失/损坏时返回 {}）
    save_config(patch: dict) -> dict     浅合并 patch 后写回，返回合并后的完整配置
    get_api_key() -> str | None          读取 dashscope_api_key（空串视为 None）
"""
import json
import os

_APP_DIR_NAME = "视频分析"


def config_dir() -> str:
    """返回配置目录（必要时创建）。"""
    env = os.environ.get("VA_CONFIG_DIR")
    if env:
        d = env
    else:
        d = os.path.join(
            os.path.expanduser("~"), "Library", "Application Support", _APP_DIR_NAME
        )
    os.makedirs(d, exist_ok=True)
    return d


def config_path() -> str:
    return os.path.join(config_dir(), "config.json")


def get_config() -> dict:
    """读取完整配置；文件不存在或解析失败时返回空 dict。"""
    path = config_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_config(patch: dict) -> dict:
    """把 patch 浅合并进现有配置并持久化，返回合并后的完整配置。"""
    cfg = get_config()
    cfg.update(patch or {})
    path = config_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)  # 原子写入，避免并发/崩溃留下半截文件
    return cfg


def get_api_key() -> str | None:
    """读取 DashScope API key；缺失或为空串时返回 None。"""
    key = get_config().get("dashscope_api_key")
    if isinstance(key, str) and key.strip():
        return key.strip()
    return None
