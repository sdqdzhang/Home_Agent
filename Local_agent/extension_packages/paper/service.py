from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import MODULE_ID, PaperSettings, apply_extension_settings, paper_settings
from .models import PaperAccess, ProviderAttempt, ProviderError
from .provider_router import ProviderRouter


class PaperService:
    """论文工具服务：高层能力稳定，Provider 差异封装在内部。"""

    def __init__(self, server_client: Any = None) -> None:
        self.server = server_client
        apply_extension_settings(None)
        self.settings: PaperSettings = paper_settings
        self.router = ProviderRouter(self.settings)

    def apply_settings(self, values: dict[str, Any]) -> None:
        apply_extension_settings(values)
        self.settings = paper_settings
        self.router.refresh_settings(self.settings)

    def _is_enabled(self, feature: str) -> bool:
        return self.settings.feature_is_enabled(feature)

    def _disabled_result(self, feature: str) -> dict[str, Any]:
        return {
            "ok": False,
            "summary": f"{feature} 已在扩展配置中关闭",
            "error": f"{feature} is disabled in extension settings",
        }

    def _attempts(self, attempts: list[ProviderAttempt]) -> list[dict[str, Any]]:
        return [attempt.to_dict() for attempt in attempts]

    def _limit(self, value: Any = None) -> int:
        return self.settings.limit(value)

    def _query_with_authors(self, query: str, authors: Any) -> str:
        if not authors:
            return query
        if isinstance(authors, str):
            author_text = authors.strip()
        elif isinstance(authors, (list, tuple)):
            author_text = " ".join(str(item).strip() for item in authors if str(item).strip())
        else:
            author_text = str(authors).strip()
        return f"{query} {author_text}".strip() if author_text else query

    def _domain_to_fields(self, domain: str) -> str:
        normalized = (domain or "").strip().lower()
        if normalized in {"ai", "ml", "cs", "computer_science", "computer science"}:
            return "Computer Science"
        if normalized in {"medicine", "medical", "biomed", "biology", "biomedical"}:
            return "Medicine"
        return ""

    async def search_papers(
        self,
        query: str,
        *,
        year_from: int | None = None,
        year_to: int | None = None,
        authors: str | list[str] | None = None,
        domain: str = "",
        limit: int | None = None,
        offset: int = 0,
    ) -> dict[str, Any]:
        if not self._is_enabled("search_papers"):
            return {**self._disabled_result("search_papers"), "papers": []}
        clean_query = str(query or "").strip()
        if not clean_query:
            return {"ok": False, "summary": "query 不能为空", "error": "query is required"}
        effective_limit = self._limit(limit)
        try:
            papers, attempts = await self.router.search(
                query=self._query_with_authors(clean_query, authors),
                limit=effective_limit,
                offset=max(0, int(offset or 0)),
                year_from=year_from,
                year_to=year_to,
                fields_of_study=self._domain_to_fields(domain),
            )
        except ProviderError as exc:
            return {"ok": False, "summary": "论文搜索失败", "error": exc.message, "papers": []}
        return {
            "ok": True,
            "summary": f"找到 {len(papers)} 篇论文",
            "papers": [paper.to_dict() for paper in papers],
            "count": len(papers),
            "provider_attempts": self._attempts(attempts),
            "warnings": [],
        }

    async def get_paper(self, identifier: str) -> dict[str, Any]:
        if not self._is_enabled("get_paper"):
            return self._disabled_result("get_paper")
        paper_id = str(identifier or "").strip()
        if not paper_id:
            return {"ok": False, "summary": "identifier 不能为空", "error": "identifier is required"}
        try:
            paper, attempts = await self.router.get_paper(paper_id)
        except ProviderError as exc:
            return {"ok": False, "summary": "未找到论文", "error": exc.message}
        return {
            "ok": True,
            "summary": paper.title or paper.id,
            "paper": paper.to_dict(),
            "source_provider": paper.source_provider,
            "provider_attempts": self._attempts(attempts),
            "warnings": [],
        }

    async def find_paper(self, identifier: str) -> dict[str, Any]:
        if not self._is_enabled("find_paper"):
            return {**self._disabled_result("find_paper"), "available": False}
        paper_id = str(identifier or "").strip()
        if not paper_id:
            return {"ok": False, "available": False, "summary": "identifier 不能为空", "error": "identifier is required"}
        try:
            access, attempts = await self.router.find_access(paper_id)
        except ProviderError as exc:
            access = PaperAccess(available=False, paper_id=paper_id, error=exc.message)
            return {
                "ok": False,
                "available": False,
                "summary": "未找到合法开放版本",
                "access": access.to_dict(),
                "error": exc.message,
            }
        return {
            "ok": True,
            "available": access.available,
            "summary": "找到合法开放版本" if access.available else "未找到合法开放版本",
            "access": access.to_dict(),
            "source_provider": access.source,
            "provider_attempts": self._attempts(attempts),
            "warnings": [],
        }

    async def download_paper(self, identifier: str, *, filename_hint: str = "") -> dict[str, Any]:
        if not self._is_enabled("download_paper"):
            return {**self._disabled_result("download_paper"), "success": False}
        paper_id = str(identifier or "").strip()
        if not paper_id:
            return {"ok": False, "success": False, "summary": "identifier 不能为空", "error": "identifier is required"}
        try:
            access, attempts = await self.router.find_access(paper_id, feature="download_paper")
            if not access.available or not access.pdf_url:
                return {
                    "ok": False,
                    "success": False,
                    "summary": "未找到可下载的合法 PDF",
                    "access": access.to_dict(),
                    "provider_attempts": self._attempts(attempts),
                }
            path = await self.router.downloader.download(access, filename_hint=filename_hint)
        except ProviderError as exc:
            return {"ok": False, "success": False, "summary": "论文下载失败", "error": exc.message}
        return {
            "ok": True,
            "success": True,
            "summary": f"论文已下载: {Path(path).name}",
            "path": str(path),
            "paper_id": paper_id,
            "source": access.source,
            "access": access.to_dict(),
            "provider_attempts": self._attempts(attempts),
        }

    async def get_citations(
        self,
        identifier: str,
        *,
        direction: str = "references",
        limit: int | None = None,
        offset: int = 0,
    ) -> dict[str, Any]:
        if not self._is_enabled("get_citations"):
            return {**self._disabled_result("get_citations"), "papers": []}
        paper_id = str(identifier or "").strip()
        if not paper_id:
            return {"ok": False, "summary": "identifier 不能为空", "error": "identifier is required"}
        normalized_direction = str(direction or "references").strip().lower()
        if normalized_direction not in {"references", "cited_by"}:
            return {
                "ok": False,
                "summary": "direction 必须是 references 或 cited_by",
                "error": "invalid direction",
            }
        effective_limit = self._limit(limit)
        try:
            papers, attempts = await self.router.citations(
                paper_id,
                direction=normalized_direction,
                limit=effective_limit,
                offset=max(0, int(offset or 0)),
            )
        except ProviderError as exc:
            return {"ok": False, "summary": "引用关系获取失败", "error": exc.message, "papers": []}
        return {
            "ok": True,
            "summary": f"获取到 {len(papers)} 条引用关系",
            "direction": normalized_direction,
            "papers": [paper.to_dict() for paper in papers],
            "count": len(papers),
            "provider_attempts": self._attempts(attempts),
            "warnings": [],
        }
