"""emotion 联调测试窗（独立、临时、仅标准库）。联调 bat 启动后手动运行本程序。"""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk

from core import (
    DEFAULT_API,
    DEFAULT_JSONL,
    DEFAULT_QUESTIONS,
    DEFAULT_RUNS,
    DEFAULT_TIMEOUT,
    ROOT,
    ask_one,
    load_questions,
    new_run_id,
    save_questions,
)


class EmotionTestApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("emotion_test · 主对话逐条联调")
        self.geometry("1080x720")
        self.minsize(900, 600)

        self.questions: list[str] = []
        self._worker: threading.Thread | None = None
        self._stop = threading.Event()
        self._run_id = ""

        self._build()
        self._load_default_questions()

    def _build(self) -> None:
        top = ttk.Frame(self, padding=8)
        top.pack(fill=tk.X)

        ttk.Label(top, text="API").pack(side=tk.LEFT)
        self.api_var = tk.StringVar(value=DEFAULT_API)
        ttk.Entry(top, textvariable=self.api_var, width=28).pack(side=tk.LEFT, padx=(4, 12))

        ttk.Label(top, text="超时(s)").pack(side=tk.LEFT)
        self.timeout_var = tk.StringVar(value=str(int(DEFAULT_TIMEOUT)))
        ttk.Entry(top, textvariable=self.timeout_var, width=6).pack(side=tk.LEFT, padx=(4, 12))

        ttk.Label(top, text="jsonl").pack(side=tk.LEFT)
        self.jsonl_var = tk.StringVar(value=str(DEFAULT_JSONL))
        ttk.Entry(top, textvariable=self.jsonl_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Button(top, text="浏览", command=self._browse_jsonl).pack(side=tk.LEFT)

        body = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        left = ttk.Frame(body, padding=4)
        right = ttk.Frame(body, padding=4)
        body.add(left, weight=1)
        body.add(right, weight=2)

        ttk.Label(left, text="问题列表").pack(anchor=tk.W)
        list_frame = ttk.Frame(left)
        list_frame.pack(fill=tk.BOTH, expand=True)
        self.listbox = tk.Listbox(list_frame, selectmode=tk.EXTENDED, exportselection=False)
        sb = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=sb.set)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.bind("<Double-Button-1>", lambda _e: self._edit_selected())

        manual = ttk.Frame(left)
        manual.pack(fill=tk.X, pady=(6, 0))
        self.manual_var = tk.StringVar()
        ttk.Entry(manual, textvariable=self.manual_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(manual, text="添加", command=self._add_manual).pack(side=tk.LEFT, padx=(4, 0))

        btns = ttk.Frame(left)
        btns.pack(fill=tk.X, pady=6)
        for text, cmd in (
            ("编辑", self._edit_selected),
            ("删除", self._delete_selected),
            ("上移", self._move_up),
            ("下移", self._move_down),
            ("导入", self._import_questions),
            ("保存列表", self._save_questions),
        ):
            ttk.Button(btns, text=text, command=cmd).pack(side=tk.LEFT, padx=2, pady=2)

        run_btns = ttk.Frame(left)
        run_btns.pack(fill=tk.X, pady=(4, 0))
        self.start_btn = ttk.Button(run_btns, text="开始逐条询问", command=self._start_batch)
        self.start_btn.pack(side=tk.LEFT, padx=2)
        self.one_btn = ttk.Button(run_btns, text="只问选中", command=self._ask_selected)
        self.one_btn.pack(side=tk.LEFT, padx=2)
        self.stop_btn = ttk.Button(run_btns, text="停止", command=self._stop_run, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=2)
        ttk.Button(run_btns, text="打开 runs", command=self._open_runs).pack(side=tk.LEFT, padx=2)

        ttk.Label(right, text="当前回合 / 日志").pack(anchor=tk.W)
        self.log = scrolledtext.ScrolledText(right, wrap=tk.WORD, height=30)
        self.log.pack(fill=tk.BOTH, expand=True)
        self.log.configure(state=tk.DISABLED)

        self.status = tk.StringVar(value="就绪。先启动联调服务，再开始询问。")
        ttk.Label(self, textvariable=self.status, padding=(8, 0, 8, 8)).pack(fill=tk.X)

    def _load_default_questions(self) -> None:
        qs = load_questions(DEFAULT_QUESTIONS)
        if not qs:
            qs = ["你好", "介绍一下自己吧"]
        self.questions = qs
        self._refresh_list()
        self._append_log(f"已加载问题 {len(qs)} 条 ← {DEFAULT_QUESTIONS}")

    def _refresh_list(self) -> None:
        self.listbox.delete(0, tk.END)
        for i, q in enumerate(self.questions, 1):
            self.listbox.insert(tk.END, f"{i:02d}. {q}")

    def _selected_indices(self) -> list[int]:
        return [int(i) for i in self.listbox.curselection()]

    def _add_manual(self) -> None:
        text = self.manual_var.get().strip()
        if not text:
            return
        self.questions.append(text)
        self.manual_var.set("")
        self._refresh_list()
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(tk.END)
        self.listbox.see(tk.END)

    def _edit_selected(self) -> None:
        idxs = self._selected_indices()
        if len(idxs) != 1:
            messagebox.showinfo("编辑", "请先选中一条问题")
            return
        i = idxs[0]
        new = simpledialog.askstring("编辑问题", "修改内容：", initialvalue=self.questions[i], parent=self)
        if new is None:
            return
        new = new.strip()
        if not new:
            return
        self.questions[i] = new
        self._refresh_list()
        self.listbox.selection_set(i)

    def _delete_selected(self) -> None:
        idxs = self._selected_indices()
        if not idxs:
            return
        for i in reversed(idxs):
            del self.questions[i]
        self._refresh_list()

    def _move_up(self) -> None:
        idxs = self._selected_indices()
        if len(idxs) != 1 or idxs[0] == 0:
            return
        i = idxs[0]
        self.questions[i - 1], self.questions[i] = self.questions[i], self.questions[i - 1]
        self._refresh_list()
        self.listbox.selection_set(i - 1)

    def _move_down(self) -> None:
        idxs = self._selected_indices()
        if len(idxs) != 1 or idxs[0] >= len(self.questions) - 1:
            return
        i = idxs[0]
        self.questions[i + 1], self.questions[i] = self.questions[i], self.questions[i + 1]
        self._refresh_list()
        self.listbox.selection_set(i + 1)

    def _import_questions(self) -> None:
        path = filedialog.askopenfilename(
            title="导入问题文件",
            initialdir=str(ROOT),
            filetypes=[("Text", "*.txt"), ("All", "*.*")],
        )
        if not path:
            return
        qs = load_questions(path)
        if not qs:
            messagebox.showwarning("导入", "文件里没有有效问题")
            return
        if self.questions and not messagebox.askyesno("导入", f"用文件中的 {len(qs)} 条替换当前列表？"):
            # 追加
            self.questions.extend(qs)
        else:
            self.questions = qs
        self._refresh_list()
        self._append_log(f"导入 {len(qs)} 条 ← {path}")

    def _save_questions(self) -> None:
        path = filedialog.asksaveasfilename(
            title="保存问题列表",
            initialdir=str(ROOT),
            initialfile="questions.txt",
            defaultextension=".txt",
            filetypes=[("Text", "*.txt")],
        )
        if not path:
            return
        save_questions(path, self.questions)
        self._append_log(f"已保存列表 → {path}")

    def _browse_jsonl(self) -> None:
        path = filedialog.askopenfilename(
            title="选择 mind_advisor_turns.jsonl",
            initialdir=str(DEFAULT_JSONL.parent if DEFAULT_JSONL.parent.is_dir() else ROOT),
            filetypes=[("JSONL", "*.jsonl"), ("All", "*.*")],
        )
        if path:
            self.jsonl_var.set(path)

    def _open_runs(self) -> None:
        DEFAULT_RUNS.mkdir(parents=True, exist_ok=True)
        try:
            import os

            os.startfile(str(DEFAULT_RUNS))  # type: ignore[attr-defined]
        except Exception as exc:
            messagebox.showinfo("runs", f"{DEFAULT_RUNS}\n\n{exc}")

    def _append_log(self, text: str) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, text.rstrip() + "\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _set_running(self, running: bool) -> None:
        state = tk.DISABLED if running else tk.NORMAL
        self.start_btn.configure(state=state)
        self.one_btn.configure(state=state)
        self.stop_btn.configure(state=tk.NORMAL if running else tk.DISABLED)

    def _parse_timeout(self) -> float:
        try:
            return max(5.0, float(self.timeout_var.get().strip() or DEFAULT_TIMEOUT))
        except ValueError:
            return DEFAULT_TIMEOUT

    def _start_batch(self) -> None:
        if not self.questions:
            messagebox.showinfo("开始", "问题列表为空")
            return
        self._run_questions(list(self.questions), label="批量")

    def _ask_selected(self) -> None:
        idxs = self._selected_indices()
        if not idxs:
            # 若输入框有内容，直接问
            manual = self.manual_var.get().strip()
            if manual:
                self._run_questions([manual], label="手动")
                return
            messagebox.showinfo("询问", "请选中问题，或在输入框写一条后点「只问选中」")
            return
        qs = [self.questions[i] for i in idxs]
        self._run_questions(qs, label="选中")

    def _stop_run(self) -> None:
        self._stop.set()
        self.status.set("正在停止…")

    def _run_questions(self, questions: list[str], *, label: str) -> None:
        if self._worker and self._worker.is_alive():
            messagebox.showinfo("忙碌", "已有任务在跑，先停止或等它结束")
            return
        self._stop.clear()
        self._run_id = new_run_id()
        self._set_running(True)
        self.status.set(f"{label}开始 · run={self._run_id}")
        self._append_log(f"\n===== {label} run={self._run_id} · {len(questions)} 题 =====")

        api = self.api_var.get().strip() or DEFAULT_API
        jsonl = Path(self.jsonl_var.get().strip() or str(DEFAULT_JSONL))
        timeout = self._parse_timeout()
        run_id = self._run_id

        def work() -> None:
            ok_n = 0
            for i, q in enumerate(questions, 1):
                if self._stop.is_set():
                    self.after(0, lambda: self._append_log("已停止。"))
                    break
                self.after(0, lambda i=i, q=q: self._on_turn_start(i, len(questions), q))
                result = ask_one(
                    q,
                    index=i,
                    run_id=run_id,
                    api_base=api,
                    jsonl_path=jsonl,
                    runs_dir=DEFAULT_RUNS,
                    timeout_s=timeout,
                    stop_flag=self._stop.is_set,
                )
                if result.ok:
                    ok_n += 1
                self.after(0, lambda r=result, i=i: self._on_turn_done(i, r))
            self.after(0, lambda: self._on_batch_done(ok_n, len(questions), run_id))

        self._worker = threading.Thread(target=work, daemon=True)
        self._worker.start()

    def _on_turn_start(self, i: int, total: int, q: str) -> None:
        self.status.set(f"询问中 {i}/{total}")
        self._append_log(f"\n--- [{i}/{total}] 发送 ---\nQ: {q}")

    def _on_turn_done(self, i: int, result) -> None:
        if result.ok:
            self._append_log(f"A ({result.elapsed_s:.1f}s, session={result.session_id}):\n{result.assistant_text}")
            mind = (result.mind_record or {}).get("mind") or {}
            adv = mind.get("advisor_debug") or {}
            if adv:
                self._append_log(
                    "advisor: "
                    f"mode={adv.get('mode')} weight={adv.get('personality_weight')} "
                    f"stance={adv.get('stance')} source={adv.get('source')}\n"
                    f"reason={adv.get('reason')}"
                )
            if result.saved_paths:
                self._append_log(f"已保存 → {Path(result.saved_paths[0]).parent}")
        else:
            self._append_log(f"失败 ({result.elapsed_s:.1f}s): {result.error}")
            if result.saved_paths:
                self._append_log(f"失败摘要 → {Path(result.saved_paths[0]).parent}")

    def _on_batch_done(self, ok_n: int, total: int, run_id: str) -> None:
        self._set_running(False)
        all_path = DEFAULT_RUNS / run_id / "all.txt"
        self.status.set(f"完成 {ok_n}/{total} · {all_path.name}")
        self._append_log(f"\n===== 结束 {ok_n}/{total} =====")
        self._append_log(f"汇总复制用：{all_path}\n")


def main() -> None:
    DEFAULT_RUNS.mkdir(parents=True, exist_ok=True)
    app = EmotionTestApp()
    app.mainloop()


if __name__ == "__main__":
    main()
