from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from shared.server_center.client import ServerCenterClient
from modules.crawler import DEFAULT_MSG_TYPE, MODULE_NAME
from modules.crawler.chat import ConversationMemory
from modules.crawler.config import crawler_settings
from modules.crawler.logging import JobLogger
from modules.crawler.model import CrawlerAssistant
from modules.crawler.pipeline import CrawlOrchestrator
from modules.crawler.storage import JobStore

logger = logging.getLogger(__name__)

# 同时进行的爬取上限（超出的排队等待）
MAX_CONCURRENT_CRAWLS = 5


class CrawlerService:
    """网页爬取模块服务：任务执行、对话、日志与 Server Center 上报。"""

    def __init__(self, server_client: ServerCenterClient | None = None) -> None:
        crawler_settings.data_dir.mkdir(parents=True, exist_ok=True)
        crawler_settings.logs_dir.mkdir(parents=True, exist_ok=True)
        crawler_settings.artifacts_dir.mkdir(parents=True, exist_ok=True)

        self.store = JobStore(crawler_settings.db_path, crawler_settings.artifacts_dir)
        self.memory = ConversationMemory(crawler_settings.db_path)
        self.assistant = CrawlerAssistant()
        self.orchestrator = CrawlOrchestrator(self.store, self.assistant)
        self.server = server_client
        self._crawl_sem = asyncio.Semaphore(MAX_CONCURRENT_CRAWLS)
        self._bg_tasks: set[asyncio.Task[Any]] = set()

    async def handle_incoming_message(self, data: dict[str, Any]) -> None:
        """处理来自 Server Center WebSocket 的用户消息。"""
        if data.get("name") != "user_ui":
            return
        target = data.get("target", "")
        if target not in (MODULE_NAME, "crawler", "网页爬取模块"):
            return

        msg_type = data.get("msg_type", "text")
        message = data.get("message") or {}
        msg_id = data.get("id", "")
        payload = message.get("payload") or message
        url = str(payload.get("url") or message.get("url") or "").strip()
        request_id = str(payload.get("request_id") or message.get("request_id") or "")

        # 带 url 的请求一律走爬取（含 msg_type=text，避免被对话抢走）
        if url:
            task = str(payload.get("task") or message.get("text") or "").strip()
            config = payload.get("config") if isinstance(payload.get("config"), dict) else None
            use_model = payload.get("use_model")
            if use_model is None and isinstance(config, dict) and "use_model" in config:
                use_model = config.get("use_model")
            # 后台并行执行，不阻塞 WebSocket 后续消息
            self._spawn_crawl(
                url,
                task=task,
                config=config,
                request_id=request_id,
                use_model=True if use_model is None else bool(use_model),
            )
            return

        if msg_type == "text":
            text = message.get("text", "").strip()
            session_id = message.get("session_id") or "default"
            await self.chat(text, session_id=session_id, reply_to_id=msg_id)

    def _spawn_crawl(
        self,
        url: str,
        *,
        task: str = "",
        config: dict | None = None,
        request_id: str = "",
        use_model: bool = True,
    ) -> asyncio.Task[Any]:
        async def _job() -> None:
            try:
                await self.submit_crawl(
                    url,
                    task=task,
                    config=config,
                    notify=True,
                    request_id=request_id,
                    use_model=use_model,
                )
            except Exception:
                logger.exception("Background crawl failed: %s", url)

        bg = asyncio.create_task(_job())
        self._bg_tasks.add(bg)
        bg.add_done_callback(self._bg_tasks.discard)
        return bg

    async def submit_crawl(
        self,
        url: str,
        *,
        task: str = "",
        config: dict | None = None,
        notify: bool = True,
        request_id: str = "",
        use_model: bool = True,
    ) -> dict[str, Any]:
        rid = (request_id or "").strip()
        cfg = dict(config or {})
        cfg.pop("use_model", None)
        await self._push_log(
            f"爬取 {url} 进行中",
            status="running",
            request_id=rid,
        )

        async with self._crawl_sem:
            try:
                outcome = await self.orchestrator.run(
                    url, task=task, config=cfg, use_model=use_model
                )
            except Exception as exc:
                logger.exception("Crawl failed")
                outcome = {"success": False, "error": str(exc), "log": [str(exc)]}
                await self._push_log(
                    str(exc),
                    status="failed",
                    log=outcome.get("log", []),
                    request_id=rid,
                )
                return outcome

        status = "completed" if outcome.get("success") else "failed"
        result = outcome.get("result") or {}
        summary = result.get("title") or url
        await self._push_log(
            f"爬取{'成功' if outcome.get('success') else '失败'}: {summary}",
            status=status,
            log=outcome.get("log", []),
            payload={"job_id": outcome.get("job_id"), "result": outcome.get("result")},
            request_id=rid,
        )
        return outcome

    async def chat(
        self,
        user_message: str,
        *,
        session_id: str = "default",
        reply_to_id: str | None = None,
    ) -> str:
        self.memory.create_session(session_id, title=session_id)
        context = await self._build_chat_context()
        history = self.memory.get_messages(session_id)
        reply = await self.assistant.chat(user_message, history, context=context)

        self.memory.append(session_id, "user", user_message)
        self.memory.append(session_id, "assistant", reply)

        if self.server:
            await self.server.send_message(
                msg_type="text",
                message={"text": reply, "role": "agent"},
            )
        return reply

    async def _build_chat_context(self) -> str:
        jobs = self.store.list_jobs(limit=5)
        artifacts = self.store.list_artifacts()[-10:]
        log_files = []
        if crawler_settings.logs_dir.exists():
            log_files = sorted(p.name for p in crawler_settings.logs_dir.glob("*.log"))[-10:]

        return json.dumps(
            {
                "recent_jobs": jobs,
                "artifact_files": artifacts,
                "log_files": log_files,
                "logs_dir": str(crawler_settings.logs_dir),
                "artifacts_dir": str(crawler_settings.artifacts_dir),
            },
            ensure_ascii=False,
            indent=2,
        )

    def read_log(self, job_id: str, tail: int = 200) -> list[str]:
        jl = JobLogger(crawler_settings.logs_dir, job_id)
        return jl.read_tail(tail)

    def get_job(self, job_id: str) -> dict | None:
        return self.store.get_job(job_id)

    def list_jobs(self, limit: int = 50) -> list[dict]:
        return self.store.list_jobs(limit)

    async def _push_log(
        self,
        summary: str,
        *,
        status: str,
        log: list[str] | None = None,
        payload: dict | None = None,
        request_id: str = "",
    ) -> None:
        if not self.server:
            return
        message: dict[str, Any] = {
            "summary": summary,
            "status": status,
            "log": log or [],
        }
        if payload:
            message["payload"] = payload
        if request_id:
            message["request_id"] = request_id
        await self.server.send_message(msg_type=DEFAULT_MSG_TYPE, message=message)
