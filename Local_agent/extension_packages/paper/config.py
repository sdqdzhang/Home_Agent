from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config import settings as app_settings

MODULE_ID = "paper"

FEATURES = (
    "search_papers",
    "get_paper",
    "find_paper",
    "download_paper",
    "get_citations",
)

DEFAULT_PROVIDER_CHAINS: dict[str, list[str]] = {
    "search_papers": ["semantic_scholar", "arxiv", "crossref", "europe_pmc", "pubmed"],
    "get_paper": ["semantic_scholar", "crossref", "arxiv", "europe_pmc", "pubmed"],
    "find_paper": ["unpaywall", "semantic_scholar", "arxiv", "europe_pmc"],
    "download_paper": ["unpaywall", "semantic_scholar", "arxiv", "europe_pmc"],
    "get_citations": ["semantic_scholar", "crossref", "europe_pmc", "pubmed"],
}

SUPPORTED_PROVIDERS: dict[str, set[str]] = {
    "search_papers": {"semantic_scholar", "arxiv", "crossref", "europe_pmc", "pubmed"},
    "get_paper": {"semantic_scholar", "crossref", "arxiv", "europe_pmc", "pubmed"},
    "find_paper": {"unpaywall", "semantic_scholar", "arxiv", "europe_pmc"},
    "download_paper": {"unpaywall", "semantic_scholar", "arxiv", "europe_pmc"},
    "get_citations": {"semantic_scholar", "crossref", "europe_pmc", "pubmed"},
}


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: Any, default: int, *, min_value: int | None = None, max_value: int | None = None) -> int:
    try:
        out = int(value)
    except (TypeError, ValueError):
        out = default
    if min_value is not None:
        out = max(min_value, out)
    if max_value is not None:
        out = min(max_value, out)
    return out


def _as_float(value: Any, default: float, *, min_value: float | None = None, max_value: float | None = None) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        out = default
    if min_value is not None:
        out = max(min_value, out)
    if max_value is not None:
        out = min(max_value, out)
    return out


def _parse_provider_chain(feature: str, raw: Any) -> list[str]:
    if isinstance(raw, str):
        items = [p.strip().lower() for p in raw.split(",")]
    elif isinstance(raw, (list, tuple)):
        items = [str(p).strip().lower() for p in raw]
    else:
        items = []
    allowed = SUPPORTED_PROVIDERS.get(feature, set())
    out: list[str] = []
    for item in items:
        if not item or item in out or item not in allowed:
            continue
        out.append(item)
    return out or list(DEFAULT_PROVIDER_CHAINS[feature])


@dataclass
class PaperSettings:
    data_dir: Path = app_settings.data_dir / MODULE_ID
    papers_dir: Path = app_settings.data_dir / MODULE_ID / "papers"

    contact_email: str = ""
    request_timeout: float = 20.0
    max_retries: int = 2
    cache_ttl_hours: float = 24.0
    max_results_default: int = 10
    max_results_hard_limit: int = 25
    user_agent: str = "HomeAgentPaper/0.1"

    feature_enabled: dict[str, bool] = field(
        default_factory=lambda: {feature: True for feature in FEATURES}
    )
    expose_to_main: dict[str, bool] = field(
        default_factory=lambda: {feature: True for feature in FEATURES}
    )
    provider_chains: dict[str, list[str]] = field(
        default_factory=lambda: {k: list(v) for k, v in DEFAULT_PROVIDER_CHAINS.items()}
    )

    def headers(self) -> dict[str, str]:
        user_agent = self.user_agent.strip() or "HomeAgentPaper/0.1"
        if self.contact_email and "mailto:" not in user_agent:
            user_agent = f"{user_agent} (mailto:{self.contact_email})"
        return {"User-Agent": user_agent}

    def limit(self, requested: Any = None) -> int:
        default = _as_int(self.max_results_default, 10, min_value=1, max_value=100)
        hard = _as_int(self.max_results_hard_limit, 25, min_value=1, max_value=100)
        if requested is None:
            return min(default, hard)
        return _as_int(requested, default, min_value=1, max_value=hard)

    def feature_is_enabled(self, feature: str) -> bool:
        return self.feature_enabled.get(feature, False)

    def feature_is_exposed(self, feature: str) -> bool:
        return self.feature_is_enabled(feature) and self.expose_to_main.get(feature, False)


paper_settings = PaperSettings()


def _resolve_download_dir(value: Any) -> Path:
    raw = str(value or "data/paper/papers").strip() or "data/paper/papers"
    path = Path(raw)
    if not path.is_absolute():
        path = app_settings.base_dir / path
    return path


def apply_extension_settings(values: dict[str, Any] | None = None) -> None:
    if values is None:
        try:
            from shared.extensions.settings_store import get_merged_values

            values = get_merged_values(MODULE_ID)
        except Exception:
            values = {}

    paper_settings.contact_email = str(values.get("contact_email") or "").strip()
    paper_settings.request_timeout = _as_float(
        values.get("request_timeout"), 20.0, min_value=3.0, max_value=120.0
    )
    paper_settings.max_retries = _as_int(values.get("max_retries"), 2, min_value=0, max_value=6)
    paper_settings.cache_ttl_hours = _as_float(
        values.get("cache_ttl_hours"), 24.0, min_value=0.0, max_value=720.0
    )
    paper_settings.max_results_default = _as_int(
        values.get("max_results_default"), 10, min_value=1, max_value=100
    )
    paper_settings.max_results_hard_limit = _as_int(
        values.get("max_results_hard_limit"), 25, min_value=1, max_value=100
    )
    paper_settings.user_agent = str(values.get("user_agent") or "HomeAgentPaper/0.1").strip()
    paper_settings.papers_dir = _resolve_download_dir(values.get("download_dir"))
    paper_settings.data_dir = paper_settings.papers_dir.parent

    for feature in FEATURES:
        paper_settings.feature_enabled[feature] = _as_bool(values.get(f"{feature}_enabled"), True)
        paper_settings.expose_to_main[feature] = _as_bool(
            values.get(f"{feature}_expose_to_main"), True
        )
        paper_settings.provider_chains[feature] = _parse_provider_chain(
            feature, values.get(f"{feature}_providers")
        )

    paper_settings.data_dir.mkdir(parents=True, exist_ok=True)
    paper_settings.papers_dir.mkdir(parents=True, exist_ok=True)


def reload_extension_settings() -> None:
    apply_extension_settings(None)
