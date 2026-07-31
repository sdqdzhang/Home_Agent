"""任务图运行时：按 DataBlock 生产关系拓扑排序，并发执行。"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable

from modules.executor.schemas import ExecuteRequest, ExecuteResult
from modules.planning import GOAL_BLOCK_ID, GOAL_BLOCK_TYPE, MAX_NODE_ATTEMPTS, MODULE_ID
from modules.planning.schemas import (
    ActionNode,
    GraphRunResult,
    NodeInput,
    NodeRunStatus,
    ProcessNode,
    TaskGraph,
)
from modules.processor.schemas import DataBlock, ProcessRequest
from shared.local_bus import call

logger = logging.getLogger(__name__)

LogFn = Callable[[str], None]
# node_id, status, attempts, error（可空）
ProgressFn = Callable[[str, str, int, str], None]

InputPair = tuple[NodeInput, DataBlock]


def _default_log(msg: str) -> None:
    logger.info(msg)


def _noop_progress(_node_id: str, _status: str, _attempts: int, _error: str) -> None:
    return


def wrap_action_result(
    *,
    node: ActionNode,
    result: ExecuteResult,
    block_id: str,
) -> DataBlock:
    """Action 一律产出 DataBlock：type 用规划声明；path 放 metadata.path；正文可空。"""
    action_type = (result.action_type or "").strip()
    stdout = (result.stdout or "").strip()
    planned = node.output.type

    if action_type in ("file.write", "file.delete") or planned in ("directory", "delete_result"):
        content = ""
    else:
        content = stdout

    touched = list(result.files_touched or [])
    path = str(touched[0]) if touched else ""

    return DataBlock(
        id=block_id,
        type=planned,
        content=content,
        producer=f"planning:{node.id}",
        metadata={
            "path": path,
            "action_type": action_type,
            "job_id": result.job_id,
            "exit_code": result.exit_code,
            "files_touched": touched,
            "planned_type": planned,
        },
    )


def _is_security_denied(result: ExecuteResult) -> bool:
    return (result.error or "") == "security_denied"


def attachment_from_pairs(pairs: list[InputPair]) -> tuple[str | None, str]:
    """写入附件：仅 role=body；恰好 0 或 1 个。"""
    bodies = [(inp, blk) for inp, blk in pairs if inp.role == "body"]
    if len(bodies) > 1:
        return None, f"多个 role=body（{len(bodies)}），无法决定写入哪一份"
    if len(bodies) == 1:
        return bodies[0][1].content, ""
    return None, ""


def tag_blocks_with_roles(pairs: list[InputPair]) -> list[DataBlock]:
    """复制块并写入 metadata.input_role，供 Processor 区分规格/材料。"""
    out: list[DataBlock] = []
    for inp, blk in pairs:
        meta = dict(blk.metadata or {})
        meta["input_role"] = inp.role
        out.append(
            DataBlock(
                id=blk.id,
                type=blk.type,
                content=blk.content,
                producer=blk.producer,
                metadata=meta,
            )
        )
    return out


class GraphRuntime:
    """解释执行静态任务图。"""

    def __init__(
        self,
        log: LogFn | None = None,
        on_progress: ProgressFn | None = None,
    ) -> None:
        self.log = log or _default_log
        self.on_progress = on_progress or _noop_progress
        self._block_seq = 0

    def _next_block_id(self, prefix: str = "blk") -> str:
        self._block_seq += 1
        return f"{prefix}{self._block_seq}"

    def _emit(self, st: NodeRunStatus) -> None:
        try:
            self.on_progress(st.node_id, st.status, st.attempts, st.error or "")
        except Exception:
            logger.exception("on_progress callback failed for %s", st.node_id)

    async def run(
        self,
        goal: str,
        graph: TaskGraph,
        initial_blocks: list[DataBlock] | None = None,
        *,
        cancel_check: Callable[[], bool] | None = None,
    ) -> GraphRunResult:
        nodes = list(graph.nodes)
        node_map: dict[str, ActionNode | ProcessNode] = {n.id: n for n in nodes}

        # 初始块：goal + 规划期环境块，均视为运行开始即就绪的数据源
        init_blocks = list(initial_blocks or [])
        initial_ready_ids: list[str] = [GOAL_BLOCK_ID] + [b.id for b in init_blocks]

        successors: dict[str, list[str]] = {n.id: [] for n in nodes}
        for src_id in initial_ready_ids:
            successors[src_id] = []
        indegree: dict[str, int] = {n.id: 0 for n in nodes}
        preds: dict[str, set[str]] = {n.id: set() for n in nodes}

        for node in nodes:
            for inp in node.inputs:
                src = inp.from_node
                if src in preds[node.id]:
                    continue
                preds[node.id].add(src)
                indegree[node.id] += 1
                successors.setdefault(src, []).append(node.id)

        blocks: dict[str, DataBlock] = {
            GOAL_BLOCK_ID: DataBlock(
                id=GOAL_BLOCK_ID,
                type=GOAL_BLOCK_TYPE,
                content=goal.strip(),
                producer="user",
                metadata={"path": ""},
            )
        }
        node_output: dict[str, str] = {GOAL_BLOCK_ID: GOAL_BLOCK_ID}
        for b in init_blocks:
            blocks[b.id] = b
            node_output[b.id] = b.id

        status: dict[str, NodeRunStatus] = {
            n.id: NodeRunStatus(node_id=n.id, status="pending") for n in nodes
        }
        for st in status.values():
            self._emit(st)
        failed_or_skipped: set[str] = set()
        lock = asyncio.Lock()
        task_failed = False
        fail_reason = ""

        def _transitive_skip(start_ids: list[str]) -> list[str]:
            skipped: list[str] = []
            stack = list(start_ids)
            seen: set[str] = set()
            while stack:
                cur = stack.pop()
                for nxt in successors.get(cur, []):
                    if nxt in seen or nxt in failed_or_skipped:
                        continue
                    seen.add(nxt)
                    if status[nxt].status in ("pending", "running"):
                        status[nxt].status = "skipped"
                        status[nxt].error = f"因前置 {cur!r} 失败/跳过而跳过"
                        failed_or_skipped.add(nxt)
                        skipped.append(nxt)
                        self._emit(status[nxt])
                        stack.append(nxt)
            return skipped

        async def _mark_success(node_id: str, out_block: DataBlock, action_type: str | None) -> list[str]:
            status[node_id].status = "succeeded"
            status[node_id].action_type = action_type
            blocks[out_block.id] = out_block
            node_output[node_id] = out_block.id
            status[node_id].output_block_id = out_block.id
            self._emit(status[node_id])

            ready: list[str] = []
            for nxt in successors.get(node_id, []):
                if nxt in failed_or_skipped:
                    continue
                indegree[nxt] -= 1
                if indegree[nxt] == 0 and status[nxt].status == "pending":
                    ready.append(nxt)
            return ready

        def _collect_pairs(node: ActionNode | ProcessNode) -> tuple[list[InputPair] | None, str]:
            out: list[InputPair] = []
            for inp in node.inputs:
                bid = node_output.get(inp.from_node)
                if not bid or bid not in blocks:
                    return None, f"缺少输入 DataBlock（来自 {inp.from_node}）"
                out.append((inp, blocks[bid]))
            return out, ""

        async def _run_action(node: ActionNode) -> tuple[bool, DataBlock | None, str, str]:
            pairs, err = _collect_pairs(node)
            if err:
                return False, None, err, ""
            assert pairs is not None

            file_content, att_err = attachment_from_pairs(pairs)
            if att_err:
                return False, None, att_err, ""

            req = ExecuteRequest(
                action_text=node.instruction,
                mode=None,
                caller_module=MODULE_ID,
                caller_request_id=node.id,
                purpose=f"planning node {node.id}",
                file_content=file_content,
            )
            result: ExecuteResult = await call("executor", "execute", req)
            action_type = result.action_type or ""
            if not result.ok:
                err_msg = result.reason or result.error or "执行失败"
                if _is_security_denied(result):
                    return False, None, f"security_denied: {err_msg}", action_type
                return False, None, err_msg, action_type

            block = wrap_action_result(
                node=node,
                result=result,
                block_id=self._next_block_id("act"),
            )
            return True, block, "", action_type

        async def _run_process(node: ProcessNode) -> tuple[bool, DataBlock | None, str, str]:
            pairs, err = _collect_pairs(node)
            if err:
                return False, None, err, "process"
            assert pairs is not None
            if not pairs:
                return False, None, "ProcessNode 没有输入 DataBlock", "process"

            # context 仍传入（供模型看见依赖上下文）；role 写入 metadata
            tagged = tag_blocks_with_roles(pairs)
            req = ProcessRequest(
                requirement=node.requirement,
                blocks=tagged,
                request_id=node.id,
            )
            result = await call("processor", "process", req)
            if not result.ok or result.output is None:
                return False, None, result.error or "处理失败", "process"
            out = result.output
            if not out.id:
                out.id = self._next_block_id("pro")
            out.metadata = dict(out.metadata or {})
            out.metadata.setdefault("path", "")
            out.metadata["planning_node"] = node.id
            out.metadata["planned_type"] = node.output.type
            return True, out, "", "process"

        async def _execute_node(node_id: str) -> list[str]:
            nonlocal task_failed, fail_reason
            node = node_map[node_id]
            status[node_id].status = "running"
            self._emit(status[node_id])
            self.log(f"[run] {node.kind}:{node_id}")

            last_error = ""
            last_action_type = ""
            security_block = False

            for attempt in range(1, MAX_NODE_ATTEMPTS + 1):
                if node_id in failed_or_skipped:
                    return []
                status[node_id].attempts = attempt
                self._emit(status[node_id])
                try:
                    if isinstance(node, ActionNode):
                        ok, block, err, action_type = await _run_action(node)
                    else:
                        ok, block, err, action_type = await _run_process(node)
                except Exception as exc:
                    logger.exception("Node %s crashed", node_id)
                    ok, block, err, action_type = False, None, str(exc), ""

                last_action_type = action_type or last_action_type
                if ok and block is not None:
                    self.log(f"[ok] {node_id} (attempt {attempt}) → {block.id} type={block.type}")
                    async with lock:
                        return await _mark_success(node_id, block, action_type or None)

                last_error = err or "未产出 DataBlock"
                self.log(f"[fail] {node_id} attempt {attempt}/{MAX_NODE_ATTEMPTS}: {last_error}")
                if last_error.startswith("security_denied"):
                    security_block = True
                    break

            status[node_id].status = "failed"
            status[node_id].error = last_error
            status[node_id].action_type = last_action_type or None
            failed_or_skipped.add(node_id)
            task_failed = True
            if not fail_reason:
                fail_reason = f"节点 {node_id} 失败: {last_error}"
            self._emit(status[node_id])
            if security_block:
                self.log(f"[abort-retry] {node_id} 安全检查未通过，不再重试")

            async with lock:
                skipped = _transitive_skip([node_id])
                if skipped:
                    self.log(f"[skip] 因 {node_id} 失败跳过: {', '.join(skipped)}")
            return []

        ready_before_goal = [nid for nid, d in indegree.items() if d == 0]
        boot_ready: list[str] = []
        for src_id in initial_ready_ids:
            for nxt in list(successors.get(src_id, [])):
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    boot_ready.append(nxt)
        pending_ready = sorted(set(ready_before_goal + boot_ready))
        in_flight: dict[str, asyncio.Task[list[str]]] = {}

        # 真正的 DAG 并发：任一节点完成就立刻调度其后继
        while pending_ready or in_flight:
            if cancel_check and cancel_check():
                for t in list(in_flight.values()):
                    t.cancel()
                for nid in list(in_flight.keys()):
                    if status[nid].status == "running":
                        status[nid].status = "skipped"
                        status[nid].error = "cancelled"
                        failed_or_skipped.add(nid)
                        self._emit(status[nid])
                in_flight.clear()
                task_failed = True
                if not fail_reason:
                    fail_reason = "用户取消规划"
                self.log("[cancel] 用户取消，停止调度新节点")
                break

            for nid in pending_ready:
                if nid in failed_or_skipped or nid in in_flight:
                    continue
                in_flight[nid] = asyncio.create_task(_execute_node(nid))
            pending_ready.clear()

            if not in_flight:
                break

            done, _ = await asyncio.wait(
                in_flight.values(),
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in done:
                nid = next(k for k, v in in_flight.items() if v is task)
                del in_flight[nid]
                try:
                    res = task.result()
                except Exception as res:
                    self.log(f"[error] {nid}: {res}")
                    async with lock:
                        status[nid].status = "failed"
                        status[nid].error = str(res)
                        failed_or_skipped.add(nid)
                        task_failed = True
                        if not fail_reason:
                            fail_reason = f"节点 {nid} 异常: {res}"
                        self._emit(status[nid])
                        _transitive_skip([nid])
                    continue

                for nxt in res:
                    if (
                        nxt not in failed_or_skipped
                        and nxt not in in_flight
                        and status[nxt].status == "pending"
                        and nxt not in pending_ready
                    ):
                        pending_ready.append(nxt)

        for nid, st in status.items():
            if st.status == "pending":
                st.status = "skipped"
                st.error = "未执行（依赖未满足或任务已失败）"
                failed_or_skipped.add(nid)
                self._emit(st)

        all_ok = (not task_failed) and all(status[n.id].status == "succeeded" for n in nodes)
        skipped_ids = [n.id for n in nodes if status[n.id].status == "skipped"]

        return GraphRunResult(
            ok=all_ok,
            goal=goal,
            summary=graph.summary,
            nodes=[status[n.id] for n in nodes],
            blocks=[b.model_dump() for b in blocks.values()],
            error="" if all_ok else (fail_reason or "任务失败"),
            skipped_node_ids=skipped_ids,
        )
