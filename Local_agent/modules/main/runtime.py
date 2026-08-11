"""工具执行：local_bus 调用各模块，统一成 ToolResultForModel。"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Awaitable, Callable

from modules.executor.schemas import ExecuteRequest, ExecuteResult
from modules.main.schemas import ToolResultForModel
from modules.rag.schemas import RagQueryRequest
from shared.local_bus import LocalBusError, call

logger = logging.getLogger(__name__)

# push(msg_type, message, msg_id=None) -> message_id
PushFn = Callable[..., Awaitable[Any]]
UpdateFn = Callable[[str, dict[str, Any]], Awaitable[None]]
PlanningRunner = Callable[[str, str], Awaitable[ToolResultForModel]]


def _truncate(text: str, limit: int = 4000) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit] + f"…(+{len(text) - limit})"


def _tool_msg_id(tool: str, request_id: str) -> str:
    rid = (request_id or "").strip() or uuid.uuid4().hex[:10]
    return f"main_tool_{tool}_{rid}"


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

            # 扩展工具：优先 capability.invoke_tool（美化输出在包内）
            ext_result = await self._invoke_extension_tool(name, arguments, request_id=request_id)
            if ext_result is not None:
                return ext_result

            return ToolResultForModel(ok=False, tool=name, error=f"未知工具: {name}")
        except LocalBusError as exc:
            return ToolResultForModel(ok=False, tool=name, error=str(exc))
        except Exception as exc:
            logger.exception("tool %s failed", name)
            return ToolResultForModel(ok=False, tool=name, error=f"工具异常: {exc}")

    async def _invoke_extension_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        request_id: str,
    ) -> ToolResultForModel | None:
        from shared.extensions.invoke_ctx import ToolInvokeContext
        from shared.extensions.registry import find_tool_spec, get_loaded

        spec = find_tool_spec(name)
        if spec is None:
            return None
        loaded = get_loaded(spec.module_id)
        if loaded is None:
            return ToolResultForModel(ok=False, tool=name, error=f"扩展未加载: {spec.module_id}")

        invoke = getattr(loaded.capability, "invoke_tool", None)
        if callable(invoke):
            ctx = ToolInvokeContext(push_card=self._push_card, update_card=self._update_card)
            result = await invoke(
                loaded.service,
                name,
                arguments,
                request_id=request_id,
                ctx=ctx,
            )
            if isinstance(result, ToolResultForModel):
                return result
            if isinstance(result, dict):
                return ToolResultForModel(
                    ok=bool(result.get("ok", True)),
                    tool=name,
                    summary=str(result.get("summary") or ""),
                    data=result.get("data") if isinstance(result.get("data"), dict) else {},
                    error=str(result.get("error") or ""),
                )
            return ToolResultForModel(ok=True, tool=name, summary=str(result), data={})

        # 无 invoke_tool：通用 kwargs 调用
        try:
            out = await call(spec.module_id, spec.method, **arguments)
        except TypeError:
            out = await call(spec.module_id, spec.method, arguments)
        if isinstance(out, dict):
            return ToolResultForModel(
                ok=bool(out.get("ok", out.get("success", True))),
                tool=name,
                summary=str(out.get("summary") or out.get("title") or name),
                data=out,
                error=str(out.get("error") or ""),
            )
        return ToolResultForModel(ok=True, tool=name, summary=str(out), data={})

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
        if isinstance(out, dict) and out.get("ok") is False:
            err = str(out.get("error") or f"{label}失败")
            summary = str(out.get("text") or f"{label}失败：{err}")
            await self._update_card(
                msg_id,
                {
                    "text": summary,
                    "capture_type": "desktop" if kind == "screenshot" else "camera",
                    "status": "error",
                    "error": err,
                    "ok": False,
                },
            )
            return ToolResultForModel(ok=False, tool=tool, summary=summary, data=out)
        path = ""
        if isinstance(out, dict):
            path = str(out.get("saved_path") or "")
        summary = f"{label}完成" + (f"：{path}" if path else "")
        final_msg = {
            "text": summary,
            "capture_type": "desktop" if kind == "screenshot" else "camera",
            "saved_path": path,
            "status": "done",
            "ok": True,
        }
        if isinstance(out, dict):
            final_msg.update({k: v for k, v in out.items() if k not in ("text",)})
        await self._update_card(msg_id, final_msg)
        return ToolResultForModel(ok=True, tool=tool, summary=summary, data=out if isinstance(out, dict) else {})


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
