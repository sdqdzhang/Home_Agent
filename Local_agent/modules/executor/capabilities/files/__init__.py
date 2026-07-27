from __future__ import annotations

from typing import Any

from modules.executor.capabilities.common import finish_not_executable
from modules.executor.capabilities.files import prompts as P
from modules.executor.capabilities.parse_assistant import JsonParseAssistant
from modules.executor.capabilities.secured import SecuredCapability
from modules.executor.content_extract import (
    extract_fenced_blocks,
    extract_search_query_from_text,
    pick_file_body,
    strip_fenced_blocks,
)
from modules.executor.file_ops import run_content_search, run_dir_browse, run_file_delete, run_file_search
from modules.executor.llm_slots import EXECUTOR_PARSE_SLOT
from modules.executor.runner import run_file_read, run_file_write
from modules.executor.schemas import (
    ContentSearchAction,
    DirBrowseAction,
    ExecuteRequest,
    FileDeleteAction,
    FileReadAction,
    FileSearchAction,
    FileWriteAction,
)


def _inject_type(payload: dict[str, Any], action_type: str) -> dict[str, Any]:
    data = dict(payload)
    data["type"] = action_type
    return data


def _normalize_content_search(payload: dict[str, Any], *, action_text: str = "", **_kwargs: Any) -> dict[str, Any]:
    data = _inject_type(payload, "content.search")
    query = str(data.get("query") or "").strip()
    if not query and action_text:
        extracted = extract_search_query_from_text(action_text)
        if extracted:
            data["query"] = extracted
    return data


def _make_read() -> SecuredCapability:
    cap = SecuredCapability(
        JsonParseAssistant(
            EXECUTOR_PARSE_SLOT,
            action_type=FileReadAction,
            allowed_label="file.read",
            render_system=P.read_file_system,
            render_user=P.read_file_user,
            normalize=lambda p, **_kw: _inject_type(p, "file.read"),
        ),
        run_action=lambda action, **kw: run_file_read(action, on_line=kw.get("on_line")),
    )
    cap.mode = "read_file"
    return cap


def _make_delete() -> SecuredCapability:
    cap = SecuredCapability(
        JsonParseAssistant(
            EXECUTOR_PARSE_SLOT,
            action_type=FileDeleteAction,
            allowed_label="file.delete",
            render_system=P.delete_file_system,
            render_user=P.delete_file_user,
            normalize=lambda p, **_kw: _inject_type(p, "file.delete"),
        ),
        run_action=lambda action, **kw: run_file_delete(action.path, on_line=kw.get("on_line")),
    )
    cap.mode = "delete_file"
    return cap


def _make_browse() -> SecuredCapability:
    cap = SecuredCapability(
        JsonParseAssistant(
            EXECUTOR_PARSE_SLOT,
            action_type=DirBrowseAction,
            allowed_label="dir.browse",
            render_system=P.browse_dir_system,
            render_user=P.browse_dir_user,
            normalize=lambda p, **_kw: _inject_type(p, "dir.browse"),
        ),
        run_action=lambda action, **kw: run_dir_browse(
            action.path, max_depth=action.max_depth, on_line=kw.get("on_line")
        ),
    )
    cap.mode = "browse_dir"
    return cap


def _make_search_file() -> SecuredCapability:
    cap = SecuredCapability(
        JsonParseAssistant(
            EXECUTOR_PARSE_SLOT,
            action_type=FileSearchAction,
            allowed_label="file.search",
            render_system=P.search_file_system,
            render_user=P.search_file_user,
            normalize=lambda p, **_kw: _inject_type(p, "file.search"),
        ),
        run_action=lambda action, **kw: run_file_search(
            action.pattern, action.root, on_line=kw.get("on_line")
        ),
    )
    cap.mode = "search_file"
    return cap


def _make_search_content() -> SecuredCapability:
    cap = SecuredCapability(
        JsonParseAssistant(
            EXECUTOR_PARSE_SLOT,
            action_type=ContentSearchAction,
            allowed_label="content.search",
            render_system=P.search_content_system,
            render_user=P.search_content_user,
            normalize=_normalize_content_search,
        ),
        run_action=lambda action, **kw: run_content_search(
            action.path,
            action.query,
            context_lines=action.context_lines,
            on_line=kw.get("on_line"),
        ),
    )
    cap.mode = "search_content"
    return cap


class WriteFileCapability:
    mode = "write_file"

    def __init__(self) -> None:
        self._assistant = JsonParseAssistant(
            EXECUTOR_PARSE_SLOT,
            action_type=FileWriteAction,
            allowed_label="file.write",
            render_system=P.write_file_system,
            render_user=P.write_file_user,
            normalize=lambda p, **_kw: _inject_type(p, "file.write"),
        )
        self._secured = SecuredCapability(
            self._assistant,
            run_action=lambda action, **kw: run_file_write(action, on_line=kw.get("on_line")),
            prepare_action=self._prepare_write_action,
        )
        self._secured.mode = self.mode

    def _prepare_write_action(
        self,
        action: FileWriteAction,
        request: ExecuteRequest,
        ctx: dict[str, Any],
    ) -> tuple[FileWriteAction, str | None]:
        body, _source = pick_file_body(
            file_content=request.file_content,
            fenced_blocks=ctx.get("fenced_blocks") or [],
            llm_content=None if ctx.get("has_attached_body") else action.content,
        )
        if body is None:
            body = ""
        return action.model_copy(update={"content": body}), None

    async def run(self, request, job_id, run_ctx, job_log, *, store, push_log):
        fenced_blocks = extract_fenced_blocks(request.action_text)
        instruction = strip_fenced_blocks(request.action_text) or request.action_text
        has_attached_body = bool(fenced_blocks) or (
            request.file_content is not None and request.file_content != ""
        )
        parse_kwargs = {
            "has_attached_body": has_attached_body,
            "fenced_blocks": fenced_blocks,
        }
        job_log.info(
            f"write_file parse: has_attached_body={has_attached_body} "
            f"file_content_len={len(request.file_content or '')} "
            f"fenced_blocks={len(fenced_blocks)}"
        )

        action, parse_error = await self._assistant.parse_action(instruction, **parse_kwargs)
        if action is None:
            return await finish_not_executable(store, push_log, job_id, job_log, request, parse_error)
        if has_attached_body and not isinstance(action, FileWriteAction):
            reason = "已附带文件正文，请在指令中明确写入目标路径"
            return await finish_not_executable(store, push_log, job_id, job_log, request, reason)
        if has_attached_body:
            action = action.model_copy(update={"content": None})

        return await self._secured.run(
            request,
            job_id,
            run_ctx,
            job_log,
            store=store,
            push_log=push_log,
            parse_kwargs=parse_kwargs,
            _preparsed_action=action,
        )


FILE_CAPABILITIES = {
    "read_file": _make_read(),
    "write_file": WriteFileCapability(),
    "delete_file": _make_delete(),
    "browse_dir": _make_browse(),
    "search_file": _make_search_file(),
    "search_content": _make_search_content(),
}
