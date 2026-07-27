"""工具执行：local_bus 调用各模块，统一成 ToolResultForModel。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

from modules.executor.schemas import ExecuteRequest, ExecuteResult
from modules.main.schemas import ToolResultForModel
from modules.rag.schemas import RagQueryRequest
from shared.local_bus import LocalBusError, call

logger = logging.getLogger(__name__)

PushFn = Callable[[str, dict[str, Any]], Awaitable[None]]
PlanningRunner = Callable[[str, str], Awaitable[ToolResultForModel]]


def _truncate(text: str, limit: int = 4000) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit] + f"…(+{len(text) - limit})"


def _guess_url(text: str) -> str:
    text = (text or "").strip()
    if re.match(r"^https?://", text, re.I):
        return text.split()[0]
    m = re.search(r"https?://[^\s]+", text, re.I)
    return m.group(0) if m else ""


class ToolRuntime:
    def __init__(
        self,
        *,
        push: PushFn | None = None,
        run_planning: PlanningRunner | None = None,
        session_id: str = "default",
    ) -> None:
        self.push = push
        self.run_planning = run_planning
        self.session_id = session_id

    async def invoke(self, name: str, arguments: dict[str, Any], *, request_id: str = "") -> ToolResultForModel:
        try:
            if name == "planning_run":
                return await self._planning(arguments, request_id=request_id)
            if name == "executor_run":
                return await self._executor(arguments, request_id=request_id)
            if name == "rag_query":
                return await self._rag_query(arguments)
            if name == "rag_chat":
                return await self._rag_chat(arguments)
            if name == "env_collect":
                return await self._env_collect()
            if name == "env_summary":
                return await self._env_summary()
            if name == "env_screenshot":
                return await self._env_capture("screenshot")
            if name == "env_camera":
                return await self._env_capture("camera")
            if name == "crawler_fetch":
                return await self._crawler(arguments, request_id=request_id)
            return ToolResultForModel(ok=False, tool=name, error=f"未知工具: {name}")
        except LocalBusError as exc:
            return ToolResultForModel(ok=False, tool=name, error=str(exc))
        except Exception as exc:
            logger.exception("tool %s failed", name)
            return ToolResultForModel(ok=False, tool=name, error=f"工具异常: {exc}")

    async def _planning(self, args: dict[str, Any], *, request_id: str) -> ToolResultForModel:
        task = str(args.get("task") or args.get("instruction") or "").strip()
        if not task:
            return ToolResultForModel(ok=False, tool="planning_run", error="task 不能为空")
        if not self.run_planning:
            return ToolResultForModel(ok=False, tool="planning_run", error="规划桥接未配置")
        return await self.run_planning(task, request_id)

    async def _executor(self, args: dict[str, Any], *, request_id: str) -> ToolResultForModel:
        instruction = str(args.get("instruction") or args.get("task") or "").strip()
        if not instruction:
            return ToolResultForModel(ok=False, tool="executor_run", error="instruction 不能为空")
        req = ExecuteRequest(
            action_text=instruction,
            caller_module="main",
            caller_request_id=request_id,
            purpose="main dialogue tool",
        )
        result: ExecuteResult = await call("executor", "execute", req)
        data = {
            "ok": result.ok,
            "job_id": result.job_id,
            "action_type": result.action_type,
            "exit_code": result.exit_code,
            "files_touched": list(result.files_touched or []),
            "stdout": _truncate(result.stdout, 2000),
            "stderr": _truncate(result.stderr, 800),
            "error": result.error,
            "reason": result.reason,
        }
        if result.security:
            data["security"] = {
                "allowed": result.security.allowed,
                "risk_level": result.security.risk_level,
                "reason": result.security.reason,
            }
        summary = (
            f"执行成功 action={result.action_type or '?'}"
            if result.ok
            else f"执行失败: {result.reason or result.error or 'unknown'}"
        )
        if self.push:
            await self.push(
                "tool_result",
                {
                    "text": summary,
                    "tool": "executor_run",
                    "ok": result.ok,
                    "data": data,
                    "request_id": request_id,
                },
            )
        return ToolResultForModel(
            ok=bool(result.ok),
            tool="executor_run",
            summary=summary,
            data=data,
            error="" if result.ok else (result.reason or result.error or "failed"),
        )

    async def _rag_query(self, args: dict[str, Any]) -> ToolResultForModel:
        query = str(args.get("query") or "").strip()
        if not query:
            return ToolResultForModel(ok=False, tool="rag_query", error="query 不能为空")
        top_k = args.get("top_k")
        req = RagQueryRequest(
            query=query,
            top_k=int(top_k) if top_k is not None else None,
            summarize=False,
            include_sources=True,
        )
        resp = await call("rag", "query", req)
        sources = [
            {
                "title": s.title,
                "score": s.score,
                "snippet": _truncate(s.snippet, 500),
                "doc_id": s.doc_id,
            }
            for s in (resp.sources or [])
        ]
        summary = f"检索到 {len(sources)} 条片段"
        data = {"query": query, "sources": sources, "answer_preview": _truncate(resp.answer, 800)}
        if self.push:
            await self.push(
                "tool_result",
                {"text": summary, "tool": "rag_query", "ok": True, "data": data},
            )
        return ToolResultForModel(ok=True, tool="rag_query", summary=summary, data=data)

    async def _rag_chat(self, args: dict[str, Any]) -> ToolResultForModel:
        message = str(args.get("message") or args.get("query") or "").strip()
        if not message:
            return ToolResultForModel(ok=False, tool="rag_chat", error="message 不能为空")
        session_id = str(args.get("session_id") or self.session_id or "default")
        resp = await call(
            "rag",
            "chat",
            message,
            session_id=session_id,
            push=False,
        )
        reply = getattr(resp, "reply", None) or getattr(getattr(resp, "rag", None), "answer", "") or ""
        sources = []
        rag = getattr(resp, "rag", None)
        if rag is not None:
            sources = [
                {"title": s.title, "score": s.score, "snippet": _truncate(s.snippet, 300)}
                for s in (rag.sources or [])
            ]
        summary = _truncate(str(reply), 1200)
        data = {"reply": reply, "sources": sources, "session_id": session_id}
        if self.push:
            await self.push(
                "tool_result",
                {"text": summary or "RAG 回答为空", "tool": "rag_chat", "ok": True, "data": data},
            )
        return ToolResultForModel(ok=True, tool="rag_chat", summary=summary or "(空回答)", data=data)

    async def _env_collect(self) -> ToolResultForModel:
        out = await call("env", "collect_once", push=False)
        snap = out.get("snapshot") if isinstance(out, dict) else out
        summary = "已采集环境快照"
        if isinstance(snap, dict):
            summary = (
                f"CPU {snap.get('cpu_percent')}% / "
                f"内存 {snap.get('memory_percent')}% / "
                f"进程数 top={len(snap.get('top_processes') or [])}"
            )
        data = {"snapshot": snap}
        if self.push:
            await self.push(
                "tool_result",
                {"text": summary, "tool": "env_collect", "ok": True, "data": {"summary": summary}},
            )
        return ToolResultForModel(ok=True, tool="env_collect", summary=summary, data=data)

    async def _env_summary(self) -> ToolResultForModel:
        out = await call("env", "run_summary", push=False)
        llm_summary = out.get("llm_summary") if isinstance(out, dict) else {}
        text = ""
        if isinstance(llm_summary, dict):
            text = str(llm_summary.get("text") or llm_summary.get("summary") or "")
        summary = _truncate(text or "环境摘要已生成", 1200)
        if self.push:
            await self.push(
                "tool_result",
                {"text": summary, "tool": "env_summary", "ok": True, "data": out if isinstance(out, dict) else {}},
            )
        return ToolResultForModel(
            ok=True,
            tool="env_summary",
            summary=summary,
            data=out if isinstance(out, dict) else {"raw": out},
        )

    async def _env_capture(self, kind: str) -> ToolResultForModel:
        method = "take_screenshot" if kind == "screenshot" else "take_camera_photo"
        tool = "env_screenshot" if kind == "screenshot" else "env_camera"
        out = await call("env", method, push=False)
        path = ""
        if isinstance(out, dict):
            path = str(out.get("saved_path") or "")
        summary = f"{'截图' if kind == 'screenshot' else '拍照'}完成" + (f"：{path}" if path else "")
        msg_type = "desktop_screenshot" if kind == "screenshot" else "camera_capture"
        if self.push and isinstance(out, dict):
            await self.push(
                msg_type,
                {
                    "text": summary,
                    "capture_type": "desktop" if kind == "screenshot" else "camera",
                    "saved_path": path,
                    **{k: v for k, v in out.items() if k not in ("text",)},
                },
            )
        return ToolResultForModel(ok=True, tool=tool, summary=summary, data=out if isinstance(out, dict) else {})

    async def _crawler(self, args: dict[str, Any], *, request_id: str) -> ToolResultForModel:
        url = str(args.get("url") or "").strip()
        task = str(args.get("task") or "").strip()
        if not url:
            raw = str(args.get("url_or_instruction") or "").strip()
            url = _guess_url(raw)
            if not task and raw and raw != url:
                task = raw
        if not url or urlparse(url).scheme not in ("http", "https"):
            return ToolResultForModel(ok=False, tool="crawler_fetch", error="需要有效的 http(s) URL")
        outcome = await call(
            "crawler",
            "submit_crawl",
            url,
            task=task,
            notify=False,
            request_id=request_id,
            use_model=True,
        )
        ok = bool(outcome.get("success")) if isinstance(outcome, dict) else False
        result = (outcome.get("result") if isinstance(outcome, dict) else None) or {}
        title = str(result.get("title") or url)
        content = str(result.get("content") or result.get("text") or result.get("markdown") or "")
        summary = f"爬取{'成功' if ok else '失败'}: {title}"
        data = {
            "url": url,
            "ok": ok,
            "title": title,
            "content": _truncate(content, 6000),
            "error": outcome.get("error") if isinstance(outcome, dict) else "",
            "job_id": outcome.get("job_id") if isinstance(outcome, dict) else "",
        }
        if self.push:
            await self.push(
                "tool_result",
                {"text": summary, "tool": "crawler_fetch", "ok": ok, "data": data, "request_id": request_id},
            )
        return ToolResultForModel(
            ok=ok,
            tool="crawler_fetch",
            summary=summary,
            data=data,
            error="" if ok else str(data.get("error") or "crawl failed"),
        )


def parse_tool_arguments(raw: str | dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {"_raw": str(raw)}
