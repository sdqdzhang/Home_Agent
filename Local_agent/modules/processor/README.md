# 处理模块（processor）

要求 + DataBlock 上下文 → 产出**恰好一个** DataBlock。供规划图 `process` 节点使用，**不对 main Function Calling 开放**。

- **模块 ID**：`processor`
- **发送名**：`处理`
- **消息类型**：`datablock`

## 定位

| 负责 | 不负责 |
|------|--------|
| 按 requirement 把输入块变换成一块输出 | 规划、执行命令、写文件 |
| 系统分配输出 `id`（`proN`） | 让 LLM 生成 id |

输入块带 `metadata.input_role`（规划侧写入 `requirement` / `material` / `context`）。

## 入口

```python
from shared.local_bus import call
from modules.processor.schemas import ProcessRequest, DataBlock

result = await call(
    "processor",
    "process",
    ProcessRequest(
        requirement="根据上下文写出完整代码",
        blocks=[
            DataBlock(type="text", content="打印 hello", producer="planning", metadata={"input_role": "requirement"}),
        ],
    ),
)
```

## 本地 API（调试）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/processor/process` | `requirement` + `blocks` → `ProcessResult` |
| GET | `/processor/health` | 模块状态 |

Web UI「处理」频道可发 `text` / `process_request` / `datablock`；结果回推 `datablock`。

## LLM 槽位

| slot | 用途 |
|------|------|
| `processor.process` | 要求 + DataBlock 上下文 → 一个 DataBlock |

## 测试

```bash
python test/test_processor_gui.py
```
