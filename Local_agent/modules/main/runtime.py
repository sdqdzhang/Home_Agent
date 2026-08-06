"""工具执行：local_bus 调用各模块，统一成 ToolResultForModel。"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

from modules.executor.schemas import ExecuteRequest, ExecuteResult
from modules.main.schemas import ToolResultForModel
from modules.rag.schemas import RagQueryRequest
from shared.local_bus import LocalBusError, call

logger = logging.getLogger(__name__)

# push(msg_type, message, msg_id=None) -> message_id
PushFn = Callable[..., Awaitable[Any]]
UpdateFn = Callable[[str, dict[str, Any]], Awaitable[None]]
PlanningRunner = Callable[[str, str], Awaitable[ToolResultForModel]]

# 批量爬取：未显式传 return_content 且 URL 数达到该值时，只回 md 路径
_AUTO_PATH_ONLY_MIN_URLS = 3


def _truncate(text: str, limit: int = 4000) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit] + f"…(+{len(text) - limit})"


def _guess_url(text: str) -> str:
    text = (text or "").strip()
    if re.match(r"^https?://", text, re.I):
        return text.split()[0]
    m = re.search(r"https?://[^\s]+", text, re.I)
    return m.group(0) if m else ""


def _tool_msg_id(tool: str, request_id: str) -> str:
    rid = (request_id or "").strip() or uuid.uuid4().hex[:10]
    return f"main_tool_{tool}_{rid}"


def _parse_bool_arg(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("1", "true", "yes", "on"):
            return True
        if s in ("0", "false", "no", "off"):
            return False
    return None


def _resolve_return_content(args: dict[str, Any], *, url_count: int) -> bool:
    explicit = _parse_bool_arg(args.get("return_content"))
    if explicit is not None:
        return explicit
    return url_count < _AUTO_PATH_ONLY_MIN_URLS


def _normalize_url_list(raw: Any) -> list[str]:
    urls: list[str] = []
    if isinstance(raw, str):
        text = raw.strip()
        if text.startswith("["):
            try:
                raw = json.loads(text)
            except json.JSONDecodeError:
                urls = [u.strip() for u in re.split(r"[\s,]+", text) if u.strip()]
                raw = None
        else:
            urls = [u.strip() for u in re.split(r"[\s,]+", text) if u.strip()]
            raw = None
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                u = item.strip()
                if u:
                    urls.append(u)
            elif isinstance(item, dict):
                u = str(item.get("url") or "").strip()
                if u:
                    urls.append(u)
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def _valid_http_url(url: str) -> bool:
    try:
        return urlparse(url).scheme in ("http", "https")
    except Exception:
        return False


def _item_from_outcome(
    outcome: dict[str, Any] | None,
    *,
    url: str,
    return_content: bool,
) -> dict[str, Any]:
    outcome = outcome if isinstance(outcome, dict) else {}
    ok = bool(outcome.get("success"))
    result = outcome.get("result") if isinstance(outcome.get("result"), dict) else {}
    title = str(result.get("title") or url)
    item: dict[str, Any] = {
        "url": url,
        "ok": ok,
        "title": title,
        "job_id": str(outcome.get("job_id") or ""),
        "text_path": str(result.get("text_path") or ""),
        "text_file": str(result.get("text_file") or ""),
        "error": "" if ok else str(outcome.get("error") or result.get("error") or "crawl failed"),
    }
    if return_content:
        content = str(result.get("content") or result.get("text") or result.get("markdown") or "")
        item["content"] = _truncate(content, 6000)
    return item


class ToolRuntime:
    def __init__(
        self,
        *,
        push: PushFn | None = None,
        update: UpdateFn | None = None,
        run_planning: PlanningRunner | None = None,
        session_id: str = "default",
    ) -> None:
        self.push = push
        self.update = update
        self.run_planning = run_planning
        self.session_id = session_id

    async def _push_card(self, msg_type: str, message: dict[str, Any], *, msg_id: str) -> str:
        if not self.push:
            return msg_id
        try:
            result = await self.push(msg_type, message, msg_id=msg_id)
            return str(result or msg_id)
        except TypeError:
            # 兼容旧 push(signature) 不接受 msg_id
            await self.push(msg_type, message)
            return msg_id
        except Exception:
            logger.exception("tool card push failed")
            return msg_id

    async def _update_card(self, msg_id: str, message: dict[str, Any]) -> None:
        if not self.update or not msg_id:
            return
        try:
            await self.update(msg_id, message)
        except Exception:
            logger.exception("tool card update failed: %s", msg_id)

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
                return await self._env_collect(request_id=request_id)
            if name == "env_summary":
                return await self._env_summary(request_id=request_id)
            if name == "env_screenshot":
                return await self._env_capture("screenshot", request_id=request_id)
            if name == "env_camera":
                return await self._env_capture("camera", request_id=request_id)
            if name == "crawler_fetch":
                return await self._crawler(arguments, request_id=request_id)
            if name == "crawler_fetch_batch":
                return await self._crawler_batch(arguments, request_id=request_id)
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

        msg_id = _tool_msg_id("executor", request_id)
        preview = instruction if len(instruction) <= 80 else instruction[:80] + "…"
        await self._push_card(
            "execution_log",
            {
                "summary": f"执行中: {preview}",
                "text": f"执行中: {preview}",
                "status": "running",
                "log": [f"指令: {instruction}", "等待执行模块…"],
                "tool": "executor_run",
                "ok": True,
                "payload": {"tool": "executor_run", "instruction": instruction},
                "request_id": request_id,
            },
            msg_id=msg_id,
        )

        req = ExecuteRequest(
            action_text=instruction,
            caller_module="main",
            caller_request_id=request_id,
            purpose="main dialogue tool",
            ui_msg_id=msg_id,
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
        log_lines: list[str] = [f"指令: {instruction}"]
        if result.job_id:
            try:
                job_lines = await call("executor", "read_log", result.job_id, tail=200)
                if isinstance(job_lines, list) and job_lines:
                    log_lines.extend(str(x) for x in job_lines)
            except Exception:
                logger.debug("read executor log failed", exc_info=True)
        if result.action_type and not any("action_type" in ln for ln in log_lines):
            log_lines.append(f"action_type: {result.action_type}")
        if result.stdout and not any(str(result.stdout).rstrip()[:40] in ln for ln in log_lines if ln):
            log_lines.append(str(result.stdout).rstrip())
        if result.stderr:
            log_lines.append(f"[stderr]\n{str(result.stderr).rstrip()}")
        if result.files_touched:
            log_lines.append("files: " + ", ".join(str(p) for p in result.files_touched))
        if result.error and not result.ok:
            log_lines.append(f"[error] {result.error}")
        if result.reason and not result.ok:
            log_lines.append(f"[reason] {result.reason}")
        if len(log_lines) <= 1:
            log_lines.append("(无额外输出)")

        await self._update_card(
            msg_id,
            {
                "summary": summary,
                "text": summary,
                "status": "completed" if result.ok else "failed",
                "log": log_lines,
                "tool": "executor_run",
                "ok": result.ok,
                "payload": {"job_id": result.job_id, "result": data, "tool": "executor_run"},
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

    async def _env_collect(self, *, request_id: str = "") -> ToolResultForModel:
        msg_id = _tool_msg_id("env_collect", request_id)
        await self._push_card(
            "system_status",
            {
                "text": "正在采集环境快照…",
                "report_type": "snapshot",
                "tool": "env_collect",
                "alert": False,
                "alert_reason": "",
                "status": "running",
                "snapshot": {},
            },
            msg_id=msg_id,
        )
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
        snap_dict = snap if isinstance(snap, dict) else {}
        await self._update_card(
            msg_id,
            {
                "text": summary,
                "report_type": "snapshot",
                "tool": "env_collect",
                "alert": False,
                "alert_reason": "",
                "snapshot": {
                    "cpu_percent": snap_dict.get("cpu_percent"),
                    "memory_percent": snap_dict.get("memory_percent"),
                    "memory_used_gb": snap_dict.get("memory_used_gb"),
                    "memory_total_gb": snap_dict.get("memory_total_gb"),
                    "disks": snap_dict.get("disks"),
                    "network": snap_dict.get("network"),
                    "top_processes": snap_dict.get("top_processes"),
                    "timestamp_iso": snap_dict.get("timestamp_iso"),
                },
            },
        )
        return ToolResultForModel(ok=True, tool="env_collect", summary=summary, data=data)

    async def _env_summary(self, *, request_id: str = "") -> ToolResultForModel:
        msg_id = _tool_msg_id("env_summary", request_id)
        await self._push_card(
            "system_status",
            {
                "text": "正在生成环境摘要…",
                "report_type": "summary",
                "tool": "env_summary",
                "alert": False,
                "alert_reason": "",
                "status": "running",
                "snapshot": {},
            },
            msg_id=msg_id,
        )
        out = await call("env", "run_summary", push=False)
        llm_summary = out.get("llm_summary") if isinstance(out, dict) else {}
        text = ""
        if isinstance(llm_summary, dict):
            text = str(llm_summary.get("text") or llm_summary.get("summary") or "")
        summary = _truncate(text or "环境摘要已生成", 1200)
        out_dict = out if isinstance(out, dict) else {}
        snap_dict = out_dict.get("snapshot") if isinstance(out_dict.get("snapshot"), dict) else {}
        agg = out_dict.get("aggregated") if isinstance(out_dict.get("aggregated"), dict) else {}
        if not snap_dict and agg:
            def _avg(val: Any) -> Any:
                if isinstance(val, dict):
                    return val.get("avg")
                return val

            snap_dict = {
                "cpu_percent": _avg(agg.get("cpu_percent")),
                "memory_percent": _avg(agg.get("memory_percent")),
                "memory_used_gb": agg.get("memory_used_gb"),
                "memory_total_gb": agg.get("memory_total_gb"),
                "disks": agg.get("disks"),
                "network": None,
                "top_processes": [
                    {
                        "name": p.get("name"),
                        "pid": p.get("pid"),
                        "cpu_percent": p.get("cpu_percent_avg"),
                        "memory_percent": p.get("memory_percent_avg"),
                    }
                    for p in (agg.get("top_processes") or [])[:8]
                    if isinstance(p, dict)
                ],
            }
        await self._update_card(
            msg_id,
            {
                "text": summary,
                "report_type": "summary",
                "tool": "env_summary",
                "alert": bool(out_dict.get("alert_active")),
                "alert_reason": "",
                "snapshot": {
                    "cpu_percent": snap_dict.get("cpu_percent"),
                    "memory_percent": snap_dict.get("memory_percent"),
                    "memory_used_gb": snap_dict.get("memory_used_gb"),
                    "memory_total_gb": snap_dict.get("memory_total_gb"),
                    "disks": snap_dict.get("disks"),
                    "network": snap_dict.get("network"),
                    "top_processes": snap_dict.get("top_processes"),
                    "timestamp_iso": snap_dict.get("timestamp_iso"),
                },
                "aggregated": agg or None,
                "llm_summary": llm_summary if isinstance(llm_summary, dict) else {"text": summary},
            },
        )
        return ToolResultForModel(
            ok=True,
            tool="env_summary",
            summary=summary,
            data=out if isinstance(out, dict) else {"raw": out},
        )

    async def _env_capture(self, kind: str, *, request_id: str = "") -> ToolResultForModel:
        method = "take_screenshot" if kind == "screenshot" else "take_camera_photo"
        tool = "env_screenshot" if kind == "screenshot" else "env_camera"
        msg_type = "desktop_screenshot" if kind == "screenshot" else "camera_capture"
        label = "截图" if kind == "screenshot" else "拍照"
        msg_id = _tool_msg_id(tool, request_id)
        await self._push_card(
            msg_type,
            {
                "text": f"正在{label}…",
                "capture_type": "desktop" if kind == "screenshot" else "camera",
                "status": "running",
            },
            msg_id=msg_id,
        )
        out = await call("env", method, push=False)
        path = ""
        if isinstance(out, dict):
            path = str(out.get("saved_path") or "")
        summary = f"{label}完成" + (f"：{path}" if path else "")
        final_msg = {
            "text": summary,
            "capture_type": "desktop" if kind == "screenshot" else "camera",
            "saved_path": path,
        }
        if isinstance(out, dict):
            final_msg.update({k: v for k, v in out.items() if k not in ("text",)})
        await self._update_card(msg_id, final_msg)
        return ToolResultForModel(ok=True, tool=tool, summary=summary, data=out if isinstance(out, dict) else {})

    async def _push_crawl_running_card(self, *, url: str, task: str, request_id: str, msg_id: str) -> None:
        await self._push_card(
            "execution_log",
            {
                "summary": f"爬取中: {url}",
                "text": f"爬取中: {url}",
                "status": "running",
                "log": [f"url: {url}"] + ([f"task: {task}"] if task else []) + ["已提交爬取模块…"],
                "tool": "crawler_fetch",
                "ok": True,
                "payload": {"tool": "crawler_fetch", "url": url},
                "request_id": request_id,
            },
            msg_id=msg_id,
        )

    async def _finalize_crawl_card(
        self,
        msg_id: str,
        *,
        item: dict[str, Any],
        crawl_log: list[Any],
        request_id: str,
        return_content: bool,
    ) -> None:
        ok = bool(item.get("ok"))
        url = str(item.get("url") or "")
        title = str(item.get("title") or url)
        summary = f"爬取{'成功' if ok else '失败'}: {title}"
        content = str(item.get("content") or "") if return_content else ""
        log_lines = [str(x) for x in crawl_log] if crawl_log else [f"url: {url}", summary]
        if item.get("text_file"):
            log_lines = list(log_lines) + [f"正文 Markdown: {item.get('text_file')}"]
        await self._update_card(
            msg_id,
            {
                "summary": summary,
                "text": summary,
                "status": "completed" if ok else "failed",
                "log": log_lines,
                "tool": "crawler_fetch",
                "ok": ok,
                "payload": {
                    "job_id": item.get("job_id"),
                    "result": {
                        "url": url,
                        "title": title,
                        "content": content,
                        "text_path": item.get("text_path") or "",
                        "text_file": item.get("text_file") or "",
                        "error": item.get("error") or "",
                    },
                    "tool": "crawler_fetch",
                },
                "request_id": request_id,
            },
        )

    async def _crawler(self, args: dict[str, Any], *, request_id: str) -> ToolResultForModel:
        url = str(args.get("url") or "").strip()
        task = str(args.get("task") or "").strip()
        if not url:
            raw = str(args.get("url_or_instruction") or "").strip()
            url = _guess_url(raw)
            if not task and raw and raw != url:
                task = raw
        if not url or not _valid_http_url(url):
            return ToolResultForModel(ok=False, tool="crawler_fetch", error="需要有效的 http(s) URL")

        return_content = _resolve_return_content(args, url_count=1)
        msg_id = _tool_msg_id("crawler", request_id)
        await self._push_crawl_running_card(url=url, task=task, request_id=request_id, msg_id=msg_id)

        outcome = await call(
            "crawler",
            "submit_crawl",
            url,
            task=task,
            notify=True,
            request_id=request_id,
            use_model=True,
            ui_msg_id=msg_id,
        )
        item = _item_from_outcome(
            outcome if isinstance(outcome, dict) else {},
            url=url,
            return_content=return_content,
        )
        crawl_log = outcome.get("log", []) if isinstance(outcome, dict) else []
        if not isinstance(crawl_log, list):
            crawl_log = [str(crawl_log)]
        await self._finalize_crawl_card(
            msg_id,
            item=item,
            crawl_log=crawl_log,
            request_id=request_id,
            return_content=return_content,
        )
        mode = "content" if return_content else "path_only"
        summary = f"爬取{'成功' if item['ok'] else '失败'}: {item['title']}"
        if not return_content and item.get("text_file"):
            summary = f"{summary} → {item['text_file']}"
        return ToolResultForModel(
            ok=bool(item["ok"]),
            tool="crawler_fetch",
            summary=summary,
            data={**item, "mode": mode},
            error="" if item["ok"] else str(item.get("error") or "crawl failed"),
        )

    async def _crawler_batch(self, args: dict[str, Any], *, request_id: str) -> ToolResultForModel:
        urls = _normalize_url_list(args.get("urls") if "urls" in args else args.get("url"))
        task = str(args.get("task") or "").strip()
        if not urls:
            return ToolResultForModel(ok=False, tool="crawler_fetch_batch", error="urls 不能为空")

        valid: list[str] = []
        invalid: list[str] = []
        for u in urls:
            if _valid_http_url(u):
                valid.append(u)
            else:
                invalid.append(u)
        if not valid:
            return ToolResultForModel(ok=False, tool="crawler_fetch_batch", error="没有有效的 http(s) URL")

        return_content = _resolve_return_content(args, url_count=len(valid))
        base = (request_id or "").strip() or uuid.uuid4().hex[:10]

        # 先全部建卡并入队，不展示「共 N 条」
        prepared: list[dict[str, Any]] = []
        for idx, url in enumerate(valid):
            rid = f"{base}_{idx}"
            msg_id = _tool_msg_id("crawler", rid)
            await self._push_crawl_running_card(url=url, task=task, request_id=rid, msg_id=msg_id)
            prepared.append({"url": url, "task": task, "request_id": rid, "ui_msg_id": msg_id})

        outcomes = await call(
            "crawler",
            "submit_crawl_batch",
            prepared,
            default_task=task,
            notify=True,
            use_model=True,
        )
        if not isinstance(outcomes, list):
            outcomes = []

        items: list[dict[str, Any]] = []
        for prep, outcome in zip(prepared, outcomes):
            if isinstance(outcome, BaseException):
                outcome = {"success": False, "error": str(outcome), "url": prep["url"]}
            item = _item_from_outcome(
                outcome if isinstance(outcome, dict) else {},
                url=prep["url"],
                return_content=return_content,
            )
            crawl_log = outcome.get("log", []) if isinstance(outcome, dict) else []
            if not isinstance(crawl_log, list):
                crawl_log = [str(crawl_log)]
            await self._finalize_crawl_card(
                prep["ui_msg_id"],
                item=item,
                crawl_log=crawl_log,
                request_id=prep["request_id"],
                return_content=return_content,
            )
            items.append(item)

        for u in invalid:
            items.append(
                {
                    "url": u,
                    "ok": False,
                    "title": u,
                    "job_id": "",
                    "text_path": "",
                    "text_file": "",
                    "error": "无效 URL",
                    **({"content": ""} if return_content else {}),
                }
            )

        ok_n = sum(1 for it in items if it.get("ok"))
        fail_n = len(items) - ok_n
        mode = "content" if return_content else "path_only"
        summary = f"批量爬取完成：成功 {ok_n}，失败 {fail_n}"
        if mode == "path_only":
            files = [str(it.get("text_file") or "") for it in items if it.get("ok") and it.get("text_file")]
            if files:
                summary = f"{summary}；正文已保存为 Markdown（见 text_file）"

        return ToolResultForModel(
            ok=ok_n > 0 and fail_n == 0,
            tool="crawler_fetch_batch",
            summary=summary,
            data={"mode": mode, "items": items, "ok_count": ok_n, "fail_count": fail_n},
            error="" if fail_n == 0 else f"{fail_n} 个失败",
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
