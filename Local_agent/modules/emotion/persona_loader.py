"""人格文件加载：YAML/JSON 即插即用。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from modules.emotion.config import (
    DEFAULT_PERSONAS_DIR,
    EmotionSettings,
    emotion_settings,
    load_active_persona_override,
    save_active_persona_override,
)
from modules.emotion.persona_schema import (
    PersonaCore,
    PersonaIdentity,
    PersonaStyle,
    PersonaUI,
    assemble_summary_from_fields,
)

logger = logging.getLogger(__name__)

# 内置兜底（文件缺失时）
_FALLBACK = PersonaCore(
    id="builtin",
    display_name="可靠助手",
    summary=(
        "你是 HomeAgent 的长期本地助手：可靠、诚实、谨慎，主动但不过度干涉。"
        "不确定时承认不确定；涉及用户重大决定时不替用户做决定。"
        "交流风格清晰、直接，使用中文，不使用表情符号。"
    ),
    identity=PersonaIdentity(name="HomeAgent", role="本地长期协作助手", self_reference="我"),
    values=["诚实", "谨慎", "尊重用户最终决策权"],
    principles=[
        "不确定时明确说明不确定",
        "重大决定不替用户拍板",
        "能直接回答则不滥用工具",
    ],
    style=PersonaStyle(tone="清晰直接", language="中文", humor="low", formality="medium", emoji=False),
    prohibitions=[
        "不使用表情符号或 emoji",
        "不编造未提供的记忆或文件内容",
        "不假装具备 Live2D / 语音能力（除非模块已接入）",
    ],
    ui=PersonaUI(personality="可靠谨慎", traits=["耐心", "务实"]),
    source_path="",
)


def personas_dir(settings: EmotionSettings | None = None) -> Path:
    cfg = settings or emotion_settings
    raw = (cfg.personas_dir or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return DEFAULT_PERSONAS_DIR


def list_persona_files(directory: Path | None = None) -> list[dict[str, str]]:
    """列出可用人格（id + 路径）。"""
    root = directory or personas_dir()
    if not root.is_dir():
        return []
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for path in sorted(root.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in (".yaml", ".yml", ".json"):
            continue
        pid = path.stem
        if pid in seen:
            continue
        seen.add(pid)
        items.append({"id": pid, "path": str(path.resolve())})
    return items


def resolve_persona_path(spec: str, directory: Path | None = None) -> Path | None:
    """
    解析人格规格：
    - 绝对/相对路径（含 .yaml/.yml/.json）
    - id 或文件名（在 personas_dir 下查找）
    """
    text = (spec or "").strip()
    if not text:
        text = "default"

    candidate = Path(text).expanduser()
    if candidate.suffix.lower() in (".yaml", ".yml", ".json"):
        if candidate.is_file():
            return candidate.resolve()
        # 相对 Local_agent 或 cwd
        for base in (Path.cwd(), DEFAULT_PERSONAS_DIR.parent.parent.parent):
            p = (base / candidate).resolve()
            if p.is_file():
                return p

    root = directory or personas_dir()
    stem = candidate.stem if candidate.suffix else text
    stem = stem.removesuffix(".yaml").removesuffix(".yml").removesuffix(".json")
    for ext in (".yaml", ".yml", ".json"):
        p = root / f"{stem}{ext}"
        if p.is_file():
            return p.resolve()
    return None


def _load_raw(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix == ".json":
        data = json.loads(text)
    elif suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise RuntimeError("读取 YAML 人格需要 PyYAML，请 pip install pyyaml") from exc
        data = yaml.safe_load(text)
    else:
        raise ValueError(f"不支持的人格文件格式: {path.suffix}")
    if not isinstance(data, dict):
        raise ValueError(f"人格文件根节点必须是对象: {path}")
    return data


def parse_persona_dict(data: dict[str, Any], *, source_path: str = "") -> PersonaCore:
    known = {
        "id",
        "display_name",
        "version",
        "summary",
        "identity",
        "values",
        "principles",
        "style",
        "prohibitions",
        "ui",
        "event_hints",
    }
    configured = [k for k in known if k in data]
    extra = {k: v for k, v in data.items() if k not in known}
    payload = {k: v for k, v in data.items() if k in known}
    if "id" not in payload or not str(payload.get("id") or "").strip():
        if source_path:
            payload["id"] = Path(source_path).stem
        else:
            payload["id"] = "default"
    persona = PersonaCore.model_validate(
        {**payload, "source_path": source_path, "extra": extra, "configured_fields": configured}
    )
    if not (persona.summary or "").strip():
        persona.summary = assemble_summary_from_fields(persona)
    return persona


def load_persona_file(path: Path) -> PersonaCore:
    raw = _load_raw(path)
    return parse_persona_dict(raw, source_path=str(path.resolve()))


class PersonaStore:
    """当前激活人格；支持按 id 切换与文件热重载。"""

    def __init__(self, settings: EmotionSettings | None = None, *, data_dir: Path | None = None) -> None:
        self.settings = settings or emotion_settings
        self._data_dir = data_dir
        self._persona: PersonaCore = _FALLBACK.model_copy(deep=True)
        self._mtime: float | None = None
        env_spec = (self.settings.persona or "default").strip() or "default"
        saved = None
        if self._data_dir is not None:
            saved = load_active_persona_override(self._data_dir)
        self._spec: str = (saved or env_spec).strip() or "default"
        self.reload(self._spec)

    @property
    def persona(self) -> PersonaCore:
        self._maybe_reload_if_changed()
        return self._persona

    @property
    def active_spec(self) -> str:
        return self._spec

    def list_available(self) -> list[dict[str, str]]:
        return list_persona_files(personas_dir(self.settings))

    def reload(self, spec: str | None = None) -> PersonaCore:
        """加载指定人格；失败则保留旧人格（首次失败用 builtin）。"""
        target = (spec if spec is not None else self._spec).strip() or "default"
        path = resolve_persona_path(target, personas_dir(self.settings))
        if path is None:
            logger.warning("人格未找到: %s，使用内置兜底", target)
            if self._persona.id == "builtin" or not self._persona.source_path:
                self._persona = _FALLBACK.model_copy(deep=True)
            self._spec = target
            self._mtime = None
            return self._persona

        try:
            loaded = load_persona_file(path)
            self._persona = loaded
            self._spec = target
            self._mtime = path.stat().st_mtime
            logger.info("已加载人格 %s (%s) ← %s", loaded.id, loaded.display_name, path)
            self._persist_active_spec(target)
        except Exception:
            logger.exception("加载人格失败: %s", path)
            if not self._persona.source_path and self._persona.id == "builtin":
                pass
            elif not getattr(self, "_persona", None):
                self._persona = _FALLBACK.model_copy(deep=True)
        return self._persona

    def set_persona(self, spec: str) -> PersonaCore:
        return self.reload(spec)

    def _persist_active_spec(self, spec: str) -> None:
        if self._data_dir is None:
            return
        try:
            save_active_persona_override(self._data_dir, spec)
        except Exception:
            logger.exception("persist active persona failed")

    def _maybe_reload_if_changed(self) -> None:
        path = resolve_persona_path(self._spec, personas_dir(self.settings))
        if path is None or not path.is_file():
            return
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return
        if self._mtime is None or mtime > self._mtime:
            logger.info("检测到人格文件变更，重新加载: %s", path)
            self.reload(self._spec)


# 进程级默认 store（service 也可自建）
_default_store: PersonaStore | None = None


def get_persona_store() -> PersonaStore:
    global _default_store
    if _default_store is None:
        _default_store = PersonaStore()
    return _default_store
