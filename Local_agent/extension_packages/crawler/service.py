from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any

from shared.server_center.client import ServerCenterClient
from . import DEFAULT_MSG_TYPE, MODULE_NAME
from .chat import ConversationMemory
from .config import crawler_settings
from .crawl_logging import JobLogger
from .model import CrawlerAssistant
from .pipeline import CrawlOrchestrator
from .storage import JobStore

logger = logging.getLogger(__name__)

# 同时进行的爬取上限（超出的排队等待）
MAX_CONCURRENT_CRAWLS = 5


class CrawlerService:
    """网页爬取模块服务：任务执行、对话、日志与 Server Center 上报。"""

    def __init__(self, server_client: ServerCenterClient | None = None) -> None:
        crawler_settings.data_dir.mkdir(parents=True, exist_ok=True)
        crawler_settings.logs_dir.mkdir(parents=True, exist_ok=True)
        crawler_settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
        crawler_settings.texts_dir.mkdir(parents=True, exist_ok=True)

        self.store = JobStore(
            crawler_settings.db_path,
            crawler_settings.artifacts_dir,
            crawler_settings.texts_dir,
        )
        self.memory = ConversationMemory(crawler_settings.db_path)
        self.assistant = CrawlerAssistant()
        self.orchestrator = CrawlOrchestrator(self.store, self.assistant)
        self.server = server_client
        self._crawl_sem = asyncio.Semaphore(MAX_CONCURRENT_CRAWLS)
        self._bg_tasks: set[asyncio.Task[Any]] = set()
        # request_id / job key → 已创建的 execution_log 消息 id（同任务原地更新）
        self._log_msg_ids: dict[str, str] = {}
        # 正在处理 / 已接受的 request_id，避免 WS 补拉与实时推送重复执行
        self._inflight_requests: set[str] = set()

    async def catch_up_pending_crawls(self, *, limit: int = 40) -> int:
        """WS 连通后补拉未执行的用户爬取请求（解决首次广播无人订阅而丢失）。"""
        if not self.server:
            return 0
        recovered = 0
        seen_ids: set[str] = set()
        for target in (MODULE_NAME, "crawler"):
            try:
                messages = await self.server.fetch_messages(
                    target=target,
                    name="user_ui",
                    limit=limit,
                )
            except Exception:
                logger.exception("crawler catch-up fetch failed target=%s", target)
                continue
            # 服务端按时间倒序；从旧到新处理，保持自然顺序
            for data in reversed(messages):
                mid = str(data.get("id") or "")
                if not mid or mid in seen_ids:
                    continue
                seen_ids.add(mid)
                if await self._try_accept_crawl_message(data, source="catch_up"):
                    recovered += 1
        if recovered:
            logger.info("crawler catch-up spawned %d pending crawl(s)", recovered)
        return recovered

    async def _crawl_already_handled(self, request_id: str) -> bool:
        rid = (request_id or "").strip()
        if not rid:
            return False
        if rid in self._inflight_requests or rid in self._log_msg_ids:
            return True
        if not self.server:
            return False
        try:
            existing = await self.server.get_message(f"crawl_log_{rid}")
        except Exception:
            return False
        if not existing:
            return False
        # 已有 crawl_log_* 即视为已接手（含 running/完成）
        return True

    async def _try_accept_crawl_message(self, data: dict[str, Any], *, source: str) -> bool:
        """若消息含 url 且尚未处理，则后台启动爬取。返回是否新启动。"""
        if data.get("name") != "user_ui":
            return False
        target = data.get("target", "")
        if target not in (MODULE_NAME, "crawler", "网页爬取模块"):
            return False

        message = data.get("message") or {}
        if isinstance(message, str):
            try:
                message = json.loads(message)
            except Exception:
                message = {}
        payload = message.get("payload") or message
        if not isinstance(payload, dict):
            payload = {}
        url = str(payload.get("url") or message.get("url") or "").strip()
        if not url:
            return False

        request_id = str(payload.get("request_id") or message.get("request_id") or "").strip()
        if request_id and await self._crawl_already_handled(request_id):
            logger.debug("crawler skip duplicate request_id=%s source=%s", request_id, source)
            return False

        task = str(payload.get("task") or message.get("text") or "").strip()
        config = payload.get("config") if isinstance(payload.get("config"), dict) else None
        use_model = payload.get("use_model")
        if use_model is None and isinstance(config, dict) and "use_model" in config:
            use_model = config.get("use_model")
        if request_id:
            self._inflight_requests.add(request_id)
        self._spawn_crawl(
            url,
            task=task,
            config=config,
            request_id=request_id,
            use_model=True if use_model is None else bool(use_model),
        )
        logger.info("crawler accepted url=%s request_id=%s source=%s", url, request_id or "-", source)
        return True

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
        if isinstance(message, str):
            try:
                message = json.loads(message)
            except Exception:
                message = {}
        payload = message.get("payload") or message if isinstance(message, dict) else {}
        url = str((payload or {}).get("url") or (message or {}).get("url") or "").strip()

        # 带 url 的请求一律走爬取（含 msg_type=text，避免被对话抢走）
        if url:
            await self._try_accept_crawl_message(data, source="ws")
            return

        if msg_type == "text":
            text = (message or {}).get("text", "").strip()
            session_id = (message or {}).get("session_id") or "default"
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
        rid = (request_id or "").strip()

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
            finally:
                if rid:
                    self._inflight_requests.discard(rid)

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
        ui_msg_id: str = "",
    ) -> dict[str, Any]:
        rid = (request_id or "").strip() or f"crawl_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        uid = (ui_msg_id or "").strip()
        cfg = dict(config or {})
        cfg.pop("use_model", None)
        if notify:
            await self._push_log(
                f"爬取 {url} 进行中",
                status="running",
                request_id=rid,
                ui_msg_id=uid,
            )

        async with self._crawl_sem:
            try:
                outcome = await self.orchestrator.run(
                    url, task=task, config=cfg, use_model=use_model
                )
            except Exception as exc:
                logger.exception("Crawl failed")
                outcome = {"success": False, "error": str(exc), "log": [str(exc)]}
                if notify:
                    await self._push_log(
                        str(exc),
                        status="failed",
                        log=outcome.get("log", []),
                        request_id=rid,
                        ui_msg_id=uid,
                    )
                elif uid:
                    await self._mirror_ui(
                        uid,
                        summary=str(exc),
                        status="failed",
                        log=outcome.get("log", []),
                        request_id=rid,
                    )
                return outcome

        status = "completed" if outcome.get("success") else "failed"
        result = outcome.get("result") or {}
        summary = result.get("title") or url
        final_summary = f"爬取{'成功' if outcome.get('success') else '失败'}: {summary}"
        log_lines = outcome.get("log", [])
        payload = {"job_id": outcome.get("job_id"), "result": outcome.get("result")}
        if notify:
            await self._push_log(
                final_summary,
                status=status,
                log=log_lines,
                payload=payload,
                request_id=rid,
                ui_msg_id=uid,
            )
        elif uid:
            await self._mirror_ui(
                uid,
                summary=final_summary,
                status=status,
                log=log_lines if isinstance(log_lines, list) else [str(log_lines)],
                payload=payload,
                request_id=rid,
            )
        return outcome

    async def submit_crawl_batch(
        self,
        items: list[dict[str, Any]],
        *,
        default_task: str = "",
        notify: bool = True,
        use_model: bool = True,
    ) -> list[dict[str, Any]]:
        """并行提交多条爬取；并发上限由 `_crawl_sem`（默认 5）控制，完成一条即补下一条。

        items 每项：`url`（必填），可选 `task` / `request_id` / `ui_msg_id` / `config`。
        """
        if not items:
            return []

        async def _one(item: dict[str, Any]) -> dict[str, Any]:
            url = str(item.get("url") or "").strip()
            if not url:
                return {"success": False, "error": "empty url", "url": url}
            try:
                outcome = await self.submit_crawl(
                    url,
                    task=str(item.get("task") or default_task or "").strip(),
                    config=item.get("config") if isinstance(item.get("config"), dict) else None,
                    notify=notify,
                    request_id=str(item.get("request_id") or "").strip(),
                    use_model=use_model,
                    ui_msg_id=str(item.get("ui_msg_id") or "").strip(),
                )
                if isinstance(outcome, dict):
                    return {**outcome, "url": outcome.get("url") or url}
                return {"success": False, "error": str(outcome), "url": url}
            except Exception as exc:
                logger.exception("batch crawl item failed: %s", url)
                return {"success": False, "error": str(exc), "url": url, "log": [str(exc)]}

        return list(await asyncio.gather(*[_one(it) for it in items]))

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
                "text_exports": self.store.list_text_exports()[-20:],
                "log_files": log_files,
                "logs_dir": str(crawler_settings.logs_dir),
                "artifacts_dir": str(crawler_settings.artifacts_dir),
                "texts_dir": str(crawler_settings.texts_dir),
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

    async def _mirror_ui(
        self,
        ui_msg_id: str,
        *,
        summary: str,
        status: str,
        log: list[str] | None = None,
        payload: dict | None = None,
        request_id: str = "",
    ) -> None:
        if not self.server or not ui_msg_id:
            return
        message: dict[str, Any] = {
            "summary": summary,
            "text": summary,
            "status": status,
            "log": log or [],
            "tool": "crawler_fetch",
        }
        if payload:
            message["payload"] = {**payload, "tool": "crawler_fetch"}
        if request_id:
            message["request_id"] = request_id
        try:
            await self.server.update_message(ui_msg_id, message=message)
        except Exception:
            logger.debug("crawler mirror ui_msg_id=%s failed", ui_msg_id, exc_info=True)

    async def _push_log(
        self,
        summary: str,
        *,
        status: str,
        log: list[str] | None = None,
        payload: dict | None = None,
        request_id: str = "",
        ui_msg_id: str = "",
    ) -> None:
        if not self.server:
            return
        payload = dict(payload or {})
        message: dict[str, Any] = {
            "summary": summary,
            "status": status,
            "log": log or [],
        }
        if payload:
            message["payload"] = payload
        if request_id:
            message["request_id"] = request_id

        job_id = str(payload.get("job_id") or "").strip()
        rid = (request_id or "").strip()
        # 优先用 request_id 作为稳定键（进行中时尚无 job_id）
        key = rid or job_id
        preferred_id = f"crawl_log_{key}" if key else None
        existing_id = self._log_msg_ids.get(key) if key else None
        candidates = [eid for eid in (existing_id, preferred_id) if eid]
        seen: set[str] = set()
        updated = False
        for mid in candidates:
            if mid in seen:
                continue
            seen.add(mid)
            try:
                await self.server.update_message(mid, message=message)
                if key:
                    self._log_msg_ids[key] = mid
                updated = True
                break
            except Exception:
                logger.debug("crawler update_log miss for %s", mid, exc_info=True)

        if not updated:
            try:
                result = await self.server.send_message(
                    msg_type=DEFAULT_MSG_TYPE,
                    message=message,
                    msg_id=preferred_id,
                )
                if key:
                    self._log_msg_ids[key] = self.server.message_id_from_response(
                        result, preferred_id or ""
                    )
            except Exception:
                logger.exception("crawler push_log failed")
                if preferred_id:
                    try:
                        await self.server.update_message(preferred_id, message=message)
                        if key:
                            self._log_msg_ids[key] = preferred_id
                    except Exception:
                        logger.exception("crawler push_log fallback update failed")

        if ui_msg_id:
            await self._mirror_ui(
                ui_msg_id,
                summary=summary,
                status=status,
                log=log,
                payload=payload,
                request_id=request_id,
            )
