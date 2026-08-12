# emotion_test（临时联调工具）

独立 tk 小窗：向主对话逐条发问，并把 `mind_advisor_turns.jsonl` 里对应回合复制到本目录 `runs/`。

- 仅标准库（`tkinter` / `urllib` / `json`）
- **不依赖、不修改**仓库其他代码；用完可整夹删除
- 不挂进 `联调启动.bat`，联调服务起来后手动启动本工具

## 用法

1. 先运行仓库根目录的 `联调启动.bat`（Server Center `:8765` + Local Agent `:8770`）
2. 双击本目录 `启动.bat`，或：

```bat
cd emotion_test
python app.py
```

3. 在窗口里维护问题列表（导入 / 增删改 / 保存）
4. 「开始逐条询问」或「只问选中」
5. 结果在 `runs/<时间戳>/`；**整场汇总**看同目录 `all.txt`（问答 + advisor/resolver/mind_context，方便一次复制）

## 默认路径

| 项 | 默认 |
|----|------|
| API | `http://127.0.0.1:8765` |
| 题库 | `questions.txt`（一行一题，`#` 注释） |
| emotion 日志源 | `../Local_agent/data/debug/mind_advisor_turns.jsonl` |
| 输出 | `runs/` |
| 超时 | 60s |
| session | **每题新 session**（`emotion_test_<id>`） |

## 落盘

每次 run 根目录：

- **`all.txt`** — 本场全部回合汇总（优先复制这个）

每回合子目录 `001/`、`002/`…：

- `qa.md` — 问答
- `summary.json` — 摘要
- `mind_advisor_turn.json` — 从 jsonl 复制的整行
- `advisor_debug.json` / `resolver_debug.json` / `mind_context.md`
