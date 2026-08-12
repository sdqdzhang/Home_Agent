"""emotion_test 核心：发主对话、等回合、从 mind_advisor_turns.jsonl 复制日志。仅标准库。"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent
DEFAULT_QUESTIONS = ROOT / "questions.txt"
DEFAULT_RUNS = ROOT / "runs"
DEFAULT_JSONL = ROOT.parent / "Local_agent" / "data" / "debug" / "mind_advisor_turns.jsonl"
DEFAULT_API = "http://127.0.0.1:8765"
DEFAULT_TIMEOUT = 60.0


@dataclass
class TurnResult:
    ok: bool
    question: str
    session_id: str
    assistant_text: str = ""
    mind_record: dict[str, Any] | None = None
    error: str = ""
    elapsed_s: float = 0.0
    saved_paths: list[str] = field(default_factory=list)


def load_questions(path: Path | str) -> list[str]:
    p = Path(path)
    if not p.is_file():
        return []
    out: list[str] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        out.append(s)
    return out


def save_questions(path: Path | str, questions: list[str]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(q.strip() for q in questions if q.strip()) + ("\n" if questions else "")
    p.write_text(body, encoding="utf-8")


def _http_json(method: str, url: str, body: dict[str, Any] | None = None, timeout: float = 30.0) -> Any:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"连接失败: {exc.reason}") from exc


def send_main_chat(
    text: str,
    *,
    session_id: str,
    api_base: str = DEFAULT_API,
) -> dict[str, Any]:
    """经 Server Center 明文接口发往 main，与前端 buildUserTextMessage 对齐。"""
    payload = {
        "id": f"emotion_test_{uuid.uuid4().hex[:12]}",
        "name": "user_ui",
        "target": "main",
        "msg_type": "text",
        "message": {
            "text": text,
            "role": "user",
            "session_id": session_id,
        },
        "timestamp": int(time.time()),
    }
    url = api_base.rstrip("/") + "/api/v1/messages/local"
    return _http_json("POST", url, payload)


def fetch_main_replies(*, api_base: str = DEFAULT_API, limit: int = 80) -> list[dict[str, Any]]:
    q = urllib.parse.urlencode({"name": "main", "target": "user_ui", "limit": str(limit)})
    url = api_base.rstrip("/") + f"/api/v1/messages?{q}"
    data = _http_json("GET", url)
    return list(data.get("messages") or [])


def jsonl_byte_size(path: Path) -> int:
    if not path.is_file():
        return 0
    return path.stat().st_size


def iter_new_jsonl_records(path: Path, start_offset: int) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    with path.open("rb") as f:
        f.seek(max(0, start_offset))
        chunk = f.read().decode("utf-8", errors="replace")
    records: list[dict[str, Any]] = []
    for line in chunk.splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            records.append(json.loads(s))
        except json.JSONDecodeError:
            continue
    return records


def find_turn_record(
    path: Path,
    *,
    session_id: str,
    start_offset: int,
    question: str = "",
) -> dict[str, Any] | None:
    for rec in iter_new_jsonl_records(path, start_offset):
        if str(rec.get("session_id") or "") != session_id:
            continue
        # 同 session 取最新匹配；每题新 session，通常只有一条
        return rec
    # 兜底：按原文出现在 user_text 里（含时间戳前缀）
    if question:
        for rec in iter_new_jsonl_records(path, start_offset):
            ut = str(rec.get("user_text") or "")
            if question in ut:
                return rec
    return None


def _format_turn_for_all(index: int, question: str, result: TurnResult) -> str:
    """纯文本块，追加进 all.txt，方便整份复制。"""
    lines: list[str] = [
        "=" * 72,
        f"[{index}] ok={result.ok}  elapsed={result.elapsed_s:.1f}s  session={result.session_id}",
        "-" * 72,
        "【问题】",
        question or "(空)",
        "",
        "【回答】",
        (result.assistant_text or "(无)").rstrip(),
        "",
    ]
    if result.error:
        lines.extend(["【错误】", result.error, ""])

    mind = (result.mind_record or {}).get("mind") or {}
    adv = mind.get("advisor_debug") or {}
    if adv:
        lines.append("【advisor_debug】")
        lines.append(json.dumps(adv, ensure_ascii=False, indent=2))
        lines.append("")
    resolver = mind.get("resolver_debug") or []
    if resolver:
        lines.append("【resolver_debug】")
        lines.append(json.dumps(resolver, ensure_ascii=False, indent=2))
        lines.append("")
    ctx = str(mind.get("mind_context") or "").strip()
    if ctx:
        lines.append("【mind_context】")
        lines.append(ctx)
        lines.append("")
    if result.mind_record is not None:
        # 工具/用量等摘要，完整原始行仍在分目录 json 里
        extra = {
            "persona_id": mind.get("persona_id"),
            "persona_display_name": mind.get("persona_display_name"),
            "available_tools": (result.mind_record or {}).get("available_tools"),
            "tool_trace": (result.mind_record or {}).get("tool_trace"),
            "usage": (result.mind_record or {}).get("usage"),
        }
        lines.append("【其它】")
        lines.append(json.dumps(extra, ensure_ascii=False, indent=2))
        lines.append("")
    lines.append("")
    return "\n".join(lines)


def append_all_txt(
    *,
    runs_dir: Path,
    run_id: str,
    index: int,
    question: str,
    result: TurnResult,
) -> Path:
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "all.txt"
    if not path.exists():
        header = (
            f"emotion_test run={run_id}\n"
            f"started_at={datetime.now().astimezone().isoformat()}\n"
            f"{'=' * 72}\n\n"
        )
        path.write_text(header, encoding="utf-8")
    with path.open("a", encoding="utf-8") as f:
        f.write(_format_turn_for_all(index, question, result))
    return path


def save_turn_artifacts(
    *,
    runs_dir: Path,
    run_id: str,
    index: int,
    question: str,
    result: TurnResult,
) -> list[str]:
    runs_dir.mkdir(parents=True, exist_ok=True)
    turn_dir = runs_dir / run_id / f"{index:03d}"
    turn_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []

    summary = {
        "index": index,
        "ok": result.ok,
        "question": question,
        "session_id": result.session_id,
        "assistant_text": result.assistant_text,
        "error": result.error,
        "elapsed_s": result.elapsed_s,
        "saved_at": datetime.now().astimezone().isoformat(),
    }
    p_summary = turn_dir / "summary.json"
    p_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    paths.append(str(p_summary))

    p_qa = turn_dir / "qa.md"
    p_qa.write_text(
        f"# Q{index}\n\n## 问题\n\n{question}\n\n## 回答\n\n{result.assistant_text or '(无)'}\n",
        encoding="utf-8",
    )
    paths.append(str(p_qa))

    if result.mind_record is not None:
        p_raw = turn_dir / "mind_advisor_turn.json"
        p_raw.write_text(json.dumps(result.mind_record, ensure_ascii=False, indent=2), encoding="utf-8")
        paths.append(str(p_raw))

        mind = result.mind_record.get("mind") or {}
        p_adv = turn_dir / "advisor_debug.json"
        p_adv.write_text(
            json.dumps(mind.get("advisor_debug") or {}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        paths.append(str(p_adv))

        p_res = turn_dir / "resolver_debug.json"
        p_res.write_text(
            json.dumps(mind.get("resolver_debug") or [], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        paths.append(str(p_res))

        p_ctx = turn_dir / "mind_context.md"
        p_ctx.write_text(str(mind.get("mind_context") or ""), encoding="utf-8")
        paths.append(str(p_ctx))

    p_all = append_all_txt(
        runs_dir=runs_dir,
        run_id=run_id,
        index=index,
        question=question,
        result=result,
    )
    paths.append(str(p_all))

    return paths


def ask_one(
    question: str,
    *,
    index: int = 1,
    run_id: str = "",
    api_base: str = DEFAULT_API,
    jsonl_path: Path = DEFAULT_JSONL,
    runs_dir: Path = DEFAULT_RUNS,
    timeout_s: float = DEFAULT_TIMEOUT,
    poll_s: float = 0.8,
    stop_flag: Callable[[], bool] | None = None,
) -> TurnResult:
    q = (question or "").strip()
    session_id = f"emotion_test_{uuid.uuid4().hex[:10]}"
    run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    t0 = time.time()
    if not q:
        return TurnResult(ok=False, question=q, session_id=session_id, error="空问题")

    offset = jsonl_byte_size(jsonl_path)
    try:
        send_main_chat(q, session_id=session_id, api_base=api_base)
    except Exception as exc:
        return TurnResult(
            ok=False,
            question=q,
            session_id=session_id,
            error=str(exc),
            elapsed_s=time.time() - t0,
        )

    deadline = t0 + max(5.0, float(timeout_s))
    record: dict[str, Any] | None = None
    while time.time() < deadline:
        if stop_flag and stop_flag():
            return TurnResult(
                ok=False,
                question=q,
                session_id=session_id,
                error="用户停止",
                elapsed_s=time.time() - t0,
            )
        record = find_turn_record(jsonl_path, session_id=session_id, start_offset=offset, question=q)
        if record and str(record.get("assistant_text") or "").strip():
            break
        time.sleep(poll_s)
    else:
        # 超时后再扫一次
        record = find_turn_record(jsonl_path, session_id=session_id, start_offset=offset, question=q)

    elapsed = time.time() - t0
    if not record:
        result = TurnResult(
            ok=False,
            question=q,
            session_id=session_id,
            error=f"超时 {timeout_s:.0f}s 未在 jsonl 中看到本轮记录（session={session_id}）",
            elapsed_s=elapsed,
        )
    else:
        result = TurnResult(
            ok=True,
            question=q,
            session_id=session_id,
            assistant_text=str(record.get("assistant_text") or ""),
            mind_record=record,
            elapsed_s=elapsed,
        )

    result.saved_paths = save_turn_artifacts(
        runs_dir=runs_dir,
        run_id=run_id,
        index=index,
        question=q,
        result=result,
    )
    return result


def new_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")
