from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class EmotionSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LA_EMOTION_", env_file=".env", extra="ignore")

    # 总开关：关闭时主对话不注入 Mind、不跑状态更新（与接入前行为一致）
    # 运行时 UI 可覆盖，并写入 data/emotion/enabled.json
    enabled: bool = False
    # 人格 id（personas/{id}.yaml）、文件名，或绝对/相对路径
    persona: str = "default"
    # 可选：自定义人格目录；空则用模块内 personas/
    personas_dir: str = ""


emotion_settings = EmotionSettings()

MODULE_DIR = Path(__file__).resolve().parent
DEFAULT_PERSONAS_DIR = MODULE_DIR / "personas"


def enabled_state_path(data_dir: Path) -> Path:
    return Path(data_dir) / "emotion" / "enabled.json"


def active_persona_path(data_dir: Path) -> Path:
    return Path(data_dir) / "emotion" / "active_persona.json"


def load_enabled_override(data_dir: Path) -> bool | None:
    """读取运行时覆盖；文件不存在返回 None（用环境变量默认）。"""
    path = enabled_state_path(data_dir)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "enabled" in data:
            return bool(data["enabled"])
    except Exception:
        logger.exception("read emotion enabled.json failed")
    return None


def save_enabled_override(data_dir: Path, enabled: bool) -> None:
    path = enabled_state_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"enabled": bool(enabled)}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_active_persona_override(data_dir: Path) -> str | None:
    path = active_persona_path(data_dir)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            spec = str(data.get("persona") or data.get("spec") or "").strip()
            return spec or None
    except Exception:
        logger.exception("read emotion active_persona.json failed")
    return None


def save_active_persona_override(data_dir: Path, spec: str) -> None:
    path = active_persona_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"persona": str(spec).strip()}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
