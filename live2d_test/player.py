"""Pet clip state machine (dsh-pet: chain + request_link_anim + click interrupt)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from catalog import Catalog
from director import link_clip, mode_key, next_busy, oneshot_name
from mapper import PresentationIntent, map_mind_state


@dataclass
class Clip:
    name: str
    url: str
    kind: str


class Player:
    def __init__(self, cat: Catalog) -> None:
        self.cat = cat
        self.intent = map_mind_state()
        self.clip: Clip | None = None
        self.play_id = 0
        self.pending_link: str | None = None
        self.dragging = False
        self.busy_seq = 0
        self.mode: tuple | None = None
        self.want_walk = False
        self.walk: dict[str, Any] | None = None
        self.facing = "right"
        self.pinned: str | None = None
        self.room: dict[str, float] | None = None

    def snapshot_clip(self) -> dict[str, Any] | None:
        if not self.clip:
            return None
        return {
            "name": self.clip.name,
            "url": self.clip.url,
            "kind": self.clip.kind,
            "play_id": self.play_id,
            "want_walk": self.want_walk,
            "path": str(self.cat.file_path(self.clip.name) or ""),
        }

    def is_oneshot(self) -> bool:
        return bool(self.clip and self.clip.kind in {"act", "click", "move", "event"})

    def play(self, name: str | None, *, want_walk: bool = False) -> dict[str, Any] | None:
        if not name or name not in self.cat.files:
            name = self.cat.idle
        if not name:
            return None
        self.want_walk = bool(want_walk)
        self.walk = None
        self.clip = Clip(name, self.cat.url(name), self.cat.kind(name))
        self.play_id += 1
        return self.snapshot_clip()

    def start(self) -> dict[str, Any] | None:
        return self.play(self.cat.idle)

    def _request(self, name: str | None, *, interrupt: bool) -> dict[str, Any] | None:
        if not name:
            return None
        if interrupt or not self.is_oneshot():
            self.pending_link = None
            return self.play(name, want_walk=False)
        self.pending_link = name
        return None

    def poke(self) -> dict[str, Any] | None:
        self.pinned = None
        name = oneshot_name("poke", self.cat)
        return self._request(name, interrupt=True)

    def preview(self, name: str) -> dict[str, Any] | None:
        if name not in self.cat.files:
            return None
        self.pinned = name
        self.pending_link = None
        self.dragging = False
        self.want_walk = False
        self.walk = None
        return self.play(name)

    def unpin(self) -> dict[str, Any] | None:
        self.pinned = None
        return self.chain()

    def drag_start(self) -> dict[str, Any] | None:
        self.pinned = None
        self.dragging = True
        self.want_walk = False
        self.walk = None
        if self.cat.drag:
            return self.play(self.cat.drag)
        return None

    def drag_end(self) -> dict[str, Any] | None:
        self.dragging = False
        if self.clip and self.clip.kind == "drag":
            return self.play(self.cat.idle)
        return None

    def on_ended(self) -> dict[str, Any] | None:
        if self.pinned:
            return self.play(self.pinned)
        if self.dragging and self.cat.drag:
            return self.play(self.cat.drag)
        if self.pending_link:
            name = self.pending_link
            self.pending_link = None
            return self.play(name)
        if self._busy():
            self.busy_seq += 1
            name = link_clip(self.intent, self.cat, self.busy_seq) or next_busy(self.cat, self.busy_seq)
            return self.play(name)
        return self.chain()

    def chain(self) -> dict[str, Any] | None:
        from wander import pick_chain

        name, want_walk, facing = pick_chain(self)
        if facing:
            self.facing = facing
        return self.play(name, want_walk=want_walk)

    def apply_intent(self, intent: PresentationIntent) -> dict[str, Any] | None:
        prev_shot = self.intent.one_shot
        self.intent = intent
        if self.pinned:
            return None
        if intent.one_shot and intent.one_shot != prev_shot:
            interrupt = intent.one_shot == "poke"
            return self._request(oneshot_name(intent.one_shot, self.cat), interrupt=interrupt)

        key = mode_key(intent)
        key_wo_shot = key[:-1]
        prev = self.mode
        self.mode = key
        if prev is not None and prev[:-1] == key_wo_shot:
            return None

        if self._busy():
            self.busy_seq += 1
            name = link_clip(intent, self.cat, self.busy_seq)
            return self._request(name, interrupt=False)

        self.pending_link = None
        self.busy_seq = 0
        if prev is None or self.is_oneshot():
            return None
        return self.chain()

    def _busy(self) -> bool:
        if self.intent.alert and self.intent.alert != "none":
            return True
        if self.intent.talking:
            return True
        return self.intent.motion in {"work", "think", "wrap"}
