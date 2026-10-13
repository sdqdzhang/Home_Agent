"""Qt control panel specialized for shenshen WebM clips."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

SCENES = [
    ("auto", "自动闲逛", {"work_mode": "idle", "interaction_mode": "chat", "talking": False, "alert": "none", "emotion": {"mood": "平静"}}),
    ("work", "写代码 / 吃 Token", {"work_mode": "executing", "interaction_mode": "task", "talking": False, "alert": "none"}),
    ("think", "深度思考", {"work_mode": "deep_tech", "interaction_mode": "task", "talking": False, "alert": "none"}),
    ("wrap", "清点归档", {"work_mode": "wrapping_up", "interaction_mode": "task", "talking": False, "alert": "none"}),
    ("look", "东张西望", {"work_mode": "idle", "interaction_mode": "exploratory", "talking": False, "alert": "none"}),
    ("talk", "哼歌说话", {"work_mode": "chat", "interaction_mode": "chat", "talking": True, "alert": "none"}),
    ("rest", "打哈欠休息", {"work_mode": "idle", "interaction_mode": "chat", "talking": False, "alert": "none", "emotion": {"mood": "疲惫"}}),
]

QUICK_ACTS = [
    ("poke", "戳一下", None),
    ("clip", "被吓一跳", "被吓一跳"),
    ("clip", "雀跃庆祝", "工作状态-雀跃庆祝"),
    ("clip", "哈欠连天", "哈欠连天"),
    ("clip", "超大伸懒腰", "超大伸懒腰"),
    ("clip", "女仆屈膝礼仪", "女仆屈膝礼仪"),
]


class LabWindow(QWidget):
    def __init__(self, store, hooks: dict[str, Callable]) -> None:
        super().__init__(None)
        self.store = store
        self._hooks = hooks
        self._pushing = False
        self.setWindowTitle("live2d_test · lab")
        self.resize(420, 760)

        root = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        lay = QVBoxLayout(inner)

        title = QLabel("神神 · 实验室")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        lay.addWidget(title)
        hint = QLabel("按现有 WebM 切姿态。点动作库里的一条就循环播这一条。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #8b97ab;")
        lay.addWidget(hint)

        row = QHBoxLayout()
        restore = QPushButton("唤出桌宠")
        restore.clicked.connect(lambda: self._hooks.get("restore") and self._hooks["restore"]())
        auto = QPushButton("恢复自动闲逛")
        auto.clicked.connect(self._resume_auto)
        row.addWidget(restore)
        row.addWidget(auto)
        lay.addLayout(row)

        self.now = QLabel("…")
        self.now.setWordWrap(True)
        lay.addWidget(_box("现在在播", self.now))

        self.scene = QComboBox()
        for value, label, _patch in SCENES:
            self.scene.addItem(label, value)
        self.scene.currentIndexChanged.connect(self._apply_scene)
        lay.addWidget(_box("姿态", self.scene))

        quick = QWidget()
        quick_lay = QVBoxLayout(quick)
        quick_lay.setContentsMargins(0, 0, 0, 0)
        grid = QHBoxLayout()
        for i, spec in enumerate(QUICK_ACTS):
            if i and i % 3 == 0:
                quick_lay.addLayout(grid)
                grid = QHBoxLayout()
            kind, label, name = spec
            btn = QPushButton(label)
            btn.clicked.connect(lambda _=False, k=kind, n=name: self._quick(k, n))
            grid.addWidget(btn)
        quick_lay.addLayout(grid)
        lay.addWidget(_box("互动", quick))

        self.filter = QLineEdit()
        self.filter.setPlaceholderText("筛选动作")
        self.filter.textChanged.connect(self._apply_filter)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemClicked.connect(self._on_clip)
        self.tree.setMinimumHeight(260)
        clip_box = QVBoxLayout()
        clip_box.addWidget(self.filter)
        clip_box.addWidget(self.tree)
        wrap = QWidget()
        wrap.setLayout(clip_box)
        lay.addWidget(_box("动作库", wrap))

        self.through = QCheckBox("穿透点击")
        self.ontop = QCheckBox("置顶")
        self.ontop.setChecked(True)
        self.edge = QCheckBox("边缘探头（真贴到左右屏边才吸）")
        self.edge.setChecked(True)
        self.through.stateChanged.connect(self._flags)
        self.ontop.stateChanged.connect(self._flags)
        self.edge.stateChanged.connect(self._edge)
        self.scale = QSlider(Qt.Orientation.Horizontal)
        self.scale.setRange(45, 115)
        self.scale.setValue(72)
        self.scale_label = QLabel("大小 72%")
        self.scale.valueChanged.connect(self._scale)
        win_inner = QWidget()
        win_lay = QVBoxLayout(win_inner)
        win_lay.addWidget(self.through)
        win_lay.addWidget(self.ontop)
        win_lay.addWidget(self.edge)
        win_lay.addWidget(self.scale_label)
        win_lay.addWidget(self.scale)
        lay.addWidget(_box("窗口", win_inner))

        scroll.setWidget(inner)
        root.addWidget(scroll)
        self._fill_clips()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(400)
        self.refresh()

    def closeEvent(self, event) -> None:  # noqa: N802
        hook = self._hooks.get("quit")
        if hook:
            hook()
        super().closeEvent(event)

    def _fill_clips(self) -> None:
        groups = self.store.cat.list_themed_groups()
        self.tree.clear()
        for group in groups:
            parent = QTreeWidgetItem([f"{group['label']} · {len(group['clips'])}"])
            for clip in group["clips"]:
                child = QTreeWidgetItem([clip["name"]])
                child.setData(0, Qt.ItemDataRole.UserRole, clip["name"])
                parent.addChild(child)
            self.tree.addTopLevelItem(parent)
            parent.setExpanded(group["id"] in {"idle", "click", "work"})

    def _apply_filter(self, text: str) -> None:
        q = (text or "").strip().lower()
        for i in range(self.tree.topLevelItemCount()):
            parent = self.tree.topLevelItem(i)
            visible = 0
            for j in range(parent.childCount()):
                child = parent.child(j)
                name = child.text(0).lower()
                ok = (not q) or q in name
                child.setHidden(not ok)
                if ok:
                    visible += 1
            parent.setHidden(visible == 0)

    def _on_clip(self, item: QTreeWidgetItem, _col: int) -> None:
        name = item.data(0, Qt.ItemDataRole.UserRole)
        if not name:
            return
        self.store.play_named(str(name))
        self.refresh()

    def _resume_auto(self) -> None:
        self._pushing = True
        try:
            self.scene.setCurrentIndex(0)
        finally:
            self._pushing = False
        self.store.patch_state(SCENES[0][2])
        self.store.resume_auto()
        self.refresh()

    def _apply_scene(self) -> None:
        if self._pushing:
            return
        key = self.scene.currentData()
        patch = next((p for value, _label, p in SCENES if value == key), None)
        if not patch:
            return
        if key not in {"auto", "rest"}:
            with self.store.lock:
                self.store.player.pinned = None
        self.store.patch_state(patch)
        if key == "auto":
            self.store.resume_auto()
        elif key == "rest":
            self.store.play_named("哈欠连天")
        self.refresh()

    def _quick(self, kind: str, name: str | None) -> None:
        if kind == "poke":
            self.store.event("playful_interaction")
        elif name:
            self.store.play_named(name)
        self.refresh()

    def _flags(self) -> None:
        if self._pushing:
            return
        self.store.set_window_flags(click_through=self.through.isChecked(), on_top=self.ontop.isChecked())

    def _edge(self) -> None:
        if self._pushing:
            return
        enabled = self.edge.isChecked()
        self.store.edge.set_enabled(enabled)

    def _scale(self, value: int) -> None:
        self.scale_label.setText(f"大小 {int(value)}%")
        if self._pushing:
            return
        self.store.set_scale(value=value / 100)

    def refresh(self) -> None:
        data = self.store.snapshot()
        clip = data.get("clip") or {}
        name = clip.get("name") or "（还没播）"
        kind = f" · {clip['kind']}" if clip.get("kind") else ""
        pin = " · 固定" if data.get("pinned") else ""
        self.now.setText(name + kind + pin)
        self._pushing = True
        try:
            self.through.setChecked(bool(data.get("click_through")))
            self.ontop.setChecked(data.get("on_top") is not False)
            edge = (data.get("edge") or {}).get("enabled")
            self.edge.setChecked(edge is not False)
            scale = data.get("scale")
            if isinstance(scale, (int, float)):
                pct = int(round(float(scale) * 100))
                if not self.scale.isSliderDown():
                    self.scale.setValue(pct)
                    self.scale_label.setText(f"大小 {pct}%")
            scene = _scene_from_state(data.get("state") or {})
            idx = self.scene.findData(scene)
            if idx >= 0 and not self.scene.hasFocus():
                self.scene.setCurrentIndex(idx)
            current = clip.get("name")
            if current:
                found = self.tree.findItems(current, Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive)
                if found:
                    self.tree.setCurrentItem(found[0])
        finally:
            self._pushing = False


def _scene_from_state(state: dict[str, Any]) -> str:
    if state.get("talking"):
        return "talk"
    work = state.get("work_mode") or "idle"
    interaction = state.get("interaction_mode") or "chat"
    mood = (state.get("emotion") or {}).get("mood") or "平静"
    if work == "executing":
        return "work"
    if work in {"deep_tech", "clarifying"}:
        return "think"
    if work == "wrapping_up":
        return "wrap"
    if interaction == "exploratory":
        return "look"
    if mood == "疲惫":
        return "rest"
    return "auto"


def _box(title: str, widget: QWidget) -> QGroupBox:
    box = QGroupBox(title)
    lay = QVBoxLayout(box)
    lay.addWidget(widget)
    return box
