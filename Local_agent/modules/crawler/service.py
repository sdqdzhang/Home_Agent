from __future__ import annotations

import json
import logging
from typing import Any

from app.server_client.message_client import ServerCenterClient
from modules.crawler import DEFAULT_MSG_TYPE, MODULE_NAME
from modules.crawler.chat import ConversationMemory
from modules.crawler.config import crawler_settings
from modules.crawler.logging import JobLogger
from modules.crawler.model import CrawlerAssistant
from modules.crawler.pipeline import CrawlOrchestrator
from modules.crawler.storage import JobStore

logger = logging.getLogger(__name__)


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
        self._running_jobs: set[str] = set()

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

        if msg_type == "text":
            text = message.get("text", "").strip()
            session_id = message.get("session_id") or "default"
            await self.chat(text, session_id=session_id, reply_to_id=msg_id)
            return

        payload = message.get("payload") or message
        url = payload.get("url") or message.get("url")
        if url:
            task = payload.get("task") or message.get("text", "")
            await self.submit_crawl(url, task=task, config=payload.get("config"), notify=True)

    async def submit_crawl(
        self,
        url: str,
        *,
        task: str = "",
        config: dict | None = None,
        notify: bool = True,
    ) -> dict[str, Any]:
        await self._push_log(f"收到爬取任务: {url}", status="running", summary=f"爬取 {url} 进行中")

        try:
            outcome = await self.orchestrator.run(url, task=task, config=config)
        except Exception as exc:
            logger.exception("Crawl failed")
            outcome = {"success": False, "error": str(exc), "log": [str(exc)]}
            await self._push_log(f"爬取失败: {exc}", status="failed", summary=str(exc), log=outcome.get("log", []))
            return outcome

        status = "completed" if outcome.get("success") else "failed"
        summary = outcome.get("result", {}).get("title") or url
        await self._push_log(
            f"爬取{'成功' if outcome.get('success') else '失败'}: {summary}",
            status=status,
            summary=summary,
            log=outcome.get("log", []),
            payload={"job_id": outcome.get("job_id"), "result": outcome.get("result")},
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
        await self.server.send_message(msg_type=DEFAULT_MSG_TYPE, message=message)
