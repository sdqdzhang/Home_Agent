"""
LLM 模型配置注册表 — tkinter 可视化。

运行（在 Local_agent 目录下）:
    python test/test_llm_registry_gui.py

或双击 test/run_llm_registry_gui.bat
"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

_TEST_DIR = Path(__file__).resolve().parent
_ROOT = _TEST_DIR.parent
for p in (_ROOT, _TEST_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from common import LogPanel, ROOT
from shared.llm.errors import EndpointInUseError
from shared.llm.registry import get_model_registry


class LlmRegistryApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("LLM 模型配置")
        self.geometry("980x640")
        self.minsize(860, 520)

        self.registry = get_model_registry()
        self.registry.ensure_seeded()

        self._selected_endpoint_id: str | None = None
        self._endpoint_map: dict[str, str] = {}

        self._build()
        self.refresh_all()
        self._log(f"数据库: {self.registry.store.db_path}")
        self._log("左侧选端点编辑；下方改槽位绑定。有槽位引用时不可删除端点。")

    def _build(self) -> None:
        root = ttk.Frame(self, padding=8)
        root.pack(fill="both", expand=True)

        paned = ttk.Panedwindow(root, orient="horizontal")
        paned.pack(fill="both", expand=True)

        left = ttk.Frame(paned, padding=(0, 4))
        right = ttk.Frame(paned, padding=(4, 0))
        paned.add(left, weight=1)
        paned.add(right, weight=2)

        ttk.Label(left, text="模型端点").pack(anchor="w")
        self.endpoint_tree = ttk.Treeview(
            left,
            columns=("name", "cap", "model", "slots"),
            show="headings",
            height=12,
        )
        for col, text, width in (
            ("name", "名称", 120),
            ("cap", "类型", 48),
            ("model", "默认模型", 100),
            ("slots", "引用数", 48),
        ):
            self.endpoint_tree.heading(col, text=text)
            self.endpoint_tree.column(col, width=width, stretch=col == "name")
        self.endpoint_tree.pack(fill="both", expand=True, pady=4)
        self.endpoint_tree.bind("<<TreeviewSelect>>", self._on_endpoint_select)

        ep_btns = ttk.Frame(left)
        ep_btns.pack(fill="x")
        ttk.Button(ep_btns, text="新建", command=self._new_endpoint).pack(side="left")
        ttk.Button(ep_btns, text="保存", command=self._save_endpoint).pack(side="left", padx=4)
        ttk.Button(ep_btns, text="删除", command=self._delete_endpoint).pack(side="left")
        ttk.Button(ep_btns, text="刷新", command=self.refresh_all).pack(side="left", padx=4)

        form = ttk.LabelFrame(right, text="端点详情", padding=8)
        form.pack(fill="x")

        self.var_name = tk.StringVar()
        self.var_capability = tk.StringVar(value="chat")
        self.var_base_url = tk.StringVar()
        self.var_api_key = tk.StringVar()
        self.var_model = tk.StringVar()
        self.var_timeout = tk.StringVar(value="120")
        self.var_max_tokens = tk.StringVar(value="4096")
        self.var_temperature = tk.StringVar(value="0.2")
        self.var_enabled = tk.BooleanVar(value=True)
        self.var_usage = tk.StringVar(value="")

        grid = ttk.Frame(form)
        grid.pack(fill="x")
        rows = [
            ("ID", "var_id", None),
            ("名称", "var_name", None),
            ("类型", "var_capability", "combo_cap"),
            ("Base URL", "var_base_url", None),
            ("API Key", "var_api_key", None),
            ("默认模型", "var_model", None),
            ("Timeout", "var_timeout", None),
            ("Max tokens", "var_max_tokens", None),
            ("Temperature", "var_temperature", None),
        ]
        self.var_id = tk.StringVar()
        for row, (label, attr, kind) in enumerate(rows):
            ttk.Label(grid, text=label).grid(row=row, column=0, sticky="w", pady=2)
            var = getattr(self, attr)
            if kind == "combo_cap":
                w = ttk.Combobox(grid, textvariable=var, values=("chat", "embed"), width=48, state="readonly")
            else:
                w = ttk.Entry(grid, textvariable=var, width=50)
                if attr == "var_id":
                    w.configure(state="readonly")
            w.grid(row=row, column=1, sticky="ew", padx=4)
        ttk.Checkbutton(form, text="启用", variable=self.var_enabled).pack(anchor="w", pady=4)
        ttk.Label(form, textvariable=self.var_usage, foreground="#666").pack(anchor="w")

        bind_frame = ttk.LabelFrame(right, text="槽位绑定", padding=8)
        bind_frame.pack(fill="both", expand=True, pady=(8, 0))

        self.binding_tree = ttk.Treeview(
            bind_frame,
            columns=("slot", "label", "endpoint", "override", "resolved", "source"),
            show="headings",
            height=10,
        )
        for col, text, width in (
            ("slot", "槽位", 110),
            ("label", "说明", 90),
            ("endpoint", "绑定端点", 100),
            ("override", "模型覆盖", 90),
            ("resolved", "实际模型", 90),
            ("source", "来源", 72),
        ):
            self.binding_tree.heading(col, text=text)
            self.binding_tree.column(col, width=width, stretch=col in ("slot", "endpoint"))
        self.binding_tree.pack(fill="both", expand=True)
        self.binding_tree.bind("<<TreeviewSelect>>", self._on_binding_select)

        edit = ttk.Frame(bind_frame)
        edit.pack(fill="x", pady=6)
        ttk.Label(edit, text="槽位").pack(side="left")
        self.var_bind_slot = tk.StringVar()
        self.combo_slot = ttk.Combobox(edit, textvariable=self.var_bind_slot, width=18, state="readonly")
        self.combo_slot.pack(side="left", padx=4)
        ttk.Label(edit, text="端点").pack(side="left")
        self.var_bind_endpoint = tk.StringVar()
        self.combo_bind_ep = ttk.Combobox(edit, textvariable=self.var_bind_endpoint, width=22, state="readonly")
        self.combo_bind_ep.pack(side="left", padx=4)
        ttk.Label(edit, text="模型覆盖").pack(side="left")
        self.var_bind_model = tk.StringVar()
        ttk.Entry(edit, textvariable=self.var_bind_model, width=14).pack(side="left", padx=4)
        ttk.Button(edit, text="应用绑定", command=self._apply_binding).pack(side="left", padx=4)
        ttk.Button(edit, text="清除覆盖", command=self._clear_binding_override).pack(side="left")

        ttk.Label(root, text="日志").pack(anchor="w", pady=(8, 0))
        self.log = LogPanel(root)
        self.log.pack(fill="both", expand=True, pady=4)

    def _log(self, msg: str) -> None:
        self.log.append(msg)

    def refresh_all(self) -> None:
        self._reload_endpoints()
        self._reload_bindings()
        self._reload_combos()

    def _reload_endpoints(self) -> None:
        self.endpoint_tree.delete(*self.endpoint_tree.get_children())
        self._endpoint_map.clear()
        for ep in self.registry.list_endpoints():
            usage = self.registry.endpoint_usage(ep.id)
            iid = ep.id
            self._endpoint_map[iid] = ep.name
            self.endpoint_tree.insert(
                "",
                "end",
                iid=iid,
                values=(ep.name, ep.capability, ep.default_model, len(usage)),
            )

    def _reload_bindings(self) -> None:
        self.binding_tree.delete(*self.binding_tree.get_children())
        endpoints = {ep.id: ep.name for ep in self.registry.list_endpoints()}
        for slot in self.registry.list_slot_definitions():
            binding = self.registry.get_binding(slot.slot_key)
            resolved = self.registry.resolve(slot.slot_key)
            ep_name = endpoints.get(binding.endpoint_id, binding.endpoint_id) if binding else "—"
            override = binding.model_override if binding and binding.model_override else ""
            self.binding_tree.insert(
                "",
                "end",
                iid=slot.slot_key,
                values=(
                    slot.slot_key,
                    slot.label,
                    ep_name,
                    override,
                    resolved.model,
                    resolved.source,
                ),
            )

    def _reload_combos(self) -> None:
        slots = [s.slot_key for s in self.registry.list_slot_definitions()]
        self.combo_slot.configure(values=slots)
        if slots and not self.var_bind_slot.get():
            self.var_bind_slot.set(slots[0])

        ep_labels = [f"{ep.name} ({ep.id})" for ep in self.registry.list_endpoints()]
        self._endpoint_labels = ep_labels
        self._endpoint_label_to_id = {
            label: ep.id for label, ep in zip(ep_labels, self.registry.list_endpoints(), strict=True)
        }
        self.combo_bind_ep.configure(values=ep_labels)

    def _on_endpoint_select(self, _event: object = None) -> None:
        sel = self.endpoint_tree.selection()
        if not sel:
            return
        ep_id = sel[0]
        self._selected_endpoint_id = ep_id
        ep = self.registry.get_endpoint(ep_id)
        self.var_id.set(ep.id)
        self.var_name.set(ep.name)
        self.var_capability.set(ep.capability)
        self.var_base_url.set(ep.base_url)
        self.var_api_key.set(ep.api_key)
        self.var_model.set(ep.default_model)
        self.var_timeout.set(str(ep.timeout))
        self.var_max_tokens.set("" if ep.max_tokens is None else str(ep.max_tokens))
        self.var_temperature.set("" if ep.temperature is None else str(ep.temperature))
        self.var_enabled.set(ep.enabled)
        slots = self.registry.endpoint_usage(ep.id)
        if slots:
            self.var_usage.set(f"被以下槽位引用：{', '.join(slots)}")
        else:
            self.var_usage.set("未被任何槽位引用，可直接删除")

    def _on_binding_select(self, _event: object = None) -> None:
        sel = self.binding_tree.selection()
        if not sel:
            return
        slot_key = sel[0]
        self.var_bind_slot.set(slot_key)
        binding = self.registry.get_binding(slot_key)
        if not binding:
            return
        for label, ep_id in self._endpoint_label_to_id.items():
            if ep_id == binding.endpoint_id:
                self.var_bind_endpoint.set(label)
                break
        self.var_bind_model.set(binding.model_override or "")

    def _parse_optional_float(self, text: str) -> float | None:
        text = text.strip()
        return float(text) if text else None

    def _parse_optional_int(self, text: str) -> int | None:
        text = text.strip()
        return int(text) if text else None

    def _new_endpoint(self) -> None:
        self._selected_endpoint_id = None
        self.var_id.set("（新建）")
        self.var_name.set("新模型")
        self.var_capability.set("chat")
        self.var_base_url.set("http://127.0.0.1:11434/v1")
        self.var_api_key.set("ollama")
        self.var_model.set("llama3.2")
        self.var_timeout.set("120")
        self.var_max_tokens.set("4096")
        self.var_temperature.set("0.2")
        self.var_enabled.set(True)
        self.var_usage.set("")
        self.endpoint_tree.selection_remove(self.endpoint_tree.selection())

    def _save_endpoint(self) -> None:
        try:
            name = self.var_name.get().strip()
            if not name:
                raise ValueError("名称不能为空")
            capability = self.var_capability.get().strip()
            base_url = self.var_base_url.get().strip()
            api_key = self.var_api_key.get().strip()
            model = self.var_model.get().strip()
            timeout = float(self.var_timeout.get().strip() or "120")
            max_tokens = self._parse_optional_int(self.var_max_tokens.get())
            temperature = self._parse_optional_float(self.var_temperature.get())
            enabled = self.var_enabled.get()

            if self._selected_endpoint_id:
                ep = self.registry.update_endpoint(
                    self._selected_endpoint_id,
                    name=name,
                    capability=capability,
                    base_url=base_url,
                    api_key=api_key,
                    default_model=model,
                    timeout=timeout,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    enabled=enabled,
                    clear_max_tokens=max_tokens is None,
                    clear_temperature=temperature is None,
                )
                self._log(f"已更新端点: {ep.name} ({ep.id})")
            else:
                ep = self.registry.create_endpoint(
                    name=name,
                    capability=capability,
                    base_url=base_url,
                    api_key=api_key,
                    default_model=model,
                    timeout=timeout,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    enabled=enabled,
                )
                self._selected_endpoint_id = ep.id
                self._log(f"已创建端点: {ep.name} ({ep.id})")

            self.refresh_all()
            self.endpoint_tree.selection_set(ep.id)
            self._on_endpoint_select()
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))
            self._log(f"!!! 保存失败: {exc}")

    def _delete_endpoint(self) -> None:
        if not self._selected_endpoint_id:
            messagebox.showinfo("提示", "请先在左侧选择一个端点")
            return
        ep_id = self._selected_endpoint_id
        usage = self.registry.endpoint_usage(ep_id)
        if usage:
            slots = "、".join(usage)
            messagebox.showwarning(
                "无法删除",
                f"该模型仍被以下槽位使用：\n{slots}\n\n请先在下方「槽位绑定」将这些槽位改绑到其他模型，然后再删除。",
            )
            self._log(f"删除被拒绝（引用）: {ep_id} ← {slots}")
            return
        ep = self.registry.get_endpoint(ep_id)
        if not messagebox.askyesno("确认删除", f"确定删除端点「{ep.name}」？"):
            return
        try:
            self.registry.delete_endpoint(ep_id)
            self._log(f"已删除端点: {ep.name}")
            self._selected_endpoint_id = None
            self._new_endpoint()
            self.refresh_all()
        except EndpointInUseError as exc:
            messagebox.showwarning("无法删除", str(exc))
            self._log(f"!!! {exc}")

    def _apply_binding(self) -> None:
        slot_key = self.var_bind_slot.get().strip()
        label = self.var_bind_endpoint.get().strip()
        if not slot_key or not label:
            messagebox.showinfo("提示", "请选择槽位和端点")
            return
        endpoint_id = self._endpoint_label_to_id.get(label)
        if not endpoint_id:
            messagebox.showerror("错误", "无效的端点选择")
            return
        model_override = self.var_bind_model.get().strip() or None
        try:
            binding = self.registry.upsert_binding(
                slot_key,
                endpoint_id,
                model_override=model_override,
                clear_model_override=model_override is None,
            )
            self._log(f"已绑定 {slot_key} → {endpoint_id}" + (f" (model={model_override})" if model_override else ""))
            self.refresh_all()
            self.binding_tree.selection_set(binding.slot_key)
        except Exception as exc:
            messagebox.showerror("绑定失败", str(exc))
            self._log(f"!!! 绑定失败: {exc}")

    def _clear_binding_override(self) -> None:
        slot_key = self.var_bind_slot.get().strip()
        label = self.var_bind_endpoint.get().strip()
        if not slot_key or not label:
            return
        endpoint_id = self._endpoint_label_to_id.get(label)
        if not endpoint_id:
            return
        try:
            self.registry.upsert_binding(
                slot_key,
                endpoint_id,
                clear_model_override=True,
            )
            self.var_bind_model.set("")
            self._log(f"已清除 {slot_key} 的模型覆盖")
            self.refresh_all()
        except Exception as exc:
            messagebox.showerror("操作失败", str(exc))


if __name__ == "__main__":
    app = LlmRegistryApp()
    app.mainloop()
