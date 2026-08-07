"""任务图静态校验。"""

from __future__ import annotations

from pathlib import Path

from modules.planning import GOAL_BLOCK_ID
from modules.planning.schemas import (
    ACTION_INPUT_ROLES,
    PROCESS_INPUT_ROLES,
    ActionNode,
    ProcessNode,
    TaskGraph,
)


def workspace_abs() -> str:
    from modules.executor.config import executor_settings

    return str(Path(executor_settings.default_cwd).resolve())


def validate_task_graph(
    graph: TaskGraph,
    *,
    initial_block_ids: frozenset[str] | None = None,
) -> list[str]:
    """返回错误列表；空列表表示通过。

    只校验图结构与 DataBlock 约定；路径是否可访问由执行时安全模块判定。

    initial_block_ids：规划期提供的初始块 id（如环境块 env1），允许被 from 引用。
    """
    errors: list[str] = []
    if not graph.nodes:
        errors.append("任务图不能为空")
        return errors

    init_ids = initial_block_ids or frozenset()
    initial_ids = {GOAL_BLOCK_ID} | set(init_ids)

    node_map: dict[str, ActionNode | ProcessNode] = {}
    for node in graph.nodes:
        if node.id in initial_ids:
            errors.append(f"节点 id 不能使用保留/初始块名 {node.id!r}")
            continue
        if node.id in node_map:
            errors.append(f"重复节点 id: {node.id!r}")
            continue
        node_map[node.id] = node

    for node in graph.nodes:
        for inp in node.inputs:
            src = inp.from_node
            if src not in initial_ids and src not in node_map:
                errors.append(f"节点 {node.id!r} 的输入引用了不存在的前置 {src!r}")
                continue
            if src == node.id:
                errors.append(f"节点 {node.id!r} 不能依赖自身")

        if isinstance(node, ProcessNode):
            if not node.inputs:
                errors.append(f"ProcessNode {node.id!r} 至少需要一个输入")
            for inp in node.inputs:
                if inp.role not in PROCESS_INPUT_ROLES:
                    errors.append(
                        f"ProcessNode {node.id!r} 的输入 role={inp.role!r} 非法，"
                        f"允许: {sorted(PROCESS_INPUT_ROLES)}"
                    )
            req_n = sum(1 for i in node.inputs if i.role == "requirement")
            if req_n < 1:
                errors.append(
                    f"ProcessNode {node.id!r} 至少需要一个 role=requirement 的输入"
                    "（规格走 DataBlock；requirement 字段只写短操作句）"
                )

        if isinstance(node, ActionNode):
            for inp in node.inputs:
                if inp.role not in ACTION_INPUT_ROLES:
                    errors.append(
                        f"ActionNode {node.id!r} 的输入 role={inp.role!r} 非法，"
                        f"允许: {sorted(ACTION_INPUT_ROLES)}"
                    )
            body_n = sum(1 for i in node.inputs if i.role == "body")
            if body_n > 1:
                errors.append(f"ActionNode {node.id!r} 最多一个 role=body（写入正文）")
            # 写文件类产出通常需要正文
            if node.output.type in ("file",) and node.inputs and body_n == 0:
                errors.append(
                    f"ActionNode {node.id!r} 产出 type=file 且有输入时，"
                    "应声明恰好一个 role=body（代码/文本正文）"
                )

    adj: dict[str, list[str]] = {nid: [] for nid in node_map}
    indegree = {nid: 0 for nid in node_map}
    for node in graph.nodes:
        seen_src: set[str] = set()
        for inp in node.inputs:
            src = inp.from_node
            if src == GOAL_BLOCK_ID:
                continue
            if src not in node_map:
                continue
            if src in seen_src:
                continue
            seen_src.add(src)
            adj[src].append(node.id)
            indegree[node.id] += 1

    queue = [nid for nid, d in indegree.items() if d == 0]
    visited = 0
    while queue:
        cur = queue.pop()
        visited += 1
        for nxt in adj[cur]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)
    if visited != len(node_map):
        errors.append("任务图存在环（不是 DAG）")

    return errors
