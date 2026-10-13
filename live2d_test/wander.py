"""Idle wander: pick facing from room to move, then a matching walk clip."""

from __future__ import annotations

import random
from typing import Any

from catalog import MOVE_MARGIN, MOVE_MAX_PX, MOVE_MIN_PX, roll_next


def pick_chain(player: Any) -> tuple[str | None, bool, str | None]:
    cat = player.cat
    exclude = player.clip.name if player.clip else None
    name = roll_next(cat.cats, exclude=exclude)
    if not name:
        return None, False, None
    if name not in (cat.cats.get("moves") or []):
        return name, False, None
    facing = choose_facing(player.facing, getattr(player, "room", None))
    clip = pick_move_clip(cat.cats.get("moves") or [], facing)
    return clip or name, True, facing


def choose_facing(current: str, room: dict[str, float] | None) -> str:
    facing = "left" if current == "left" else "right"
    if not room:
        return facing
    cx = float(room.get("cx") or 0)
    left = float(room.get("left") or 0)
    right = float(room.get("right") or 0)
    margin = float(room.get("margin") or MOVE_MARGIN) + MOVE_MIN_PX
    space_l = cx - left
    space_r = right - cx
    if space_l < margin <= space_r:
        return "right"
    if space_r < margin <= space_l:
        return "left"
    if random.random() < 0.72:
        return facing
    return "right" if space_r >= space_l else "left"


def pick_move_clip(moves: list[str], facing: str) -> str | None:
    if not moves:
        return None
    lefts = [name for name in moves if "左" in name]
    rights = [name for name in moves if "左" not in name]
    if facing == "left" and lefts:
        return random.choice(lefts)
    pool = rights or moves
    return random.choice(pool)


def plan_walk(
    *,
    wx: int,
    wy: int,
    width: int,
    height: int,
    facing: str,
    left: int,
    top: int,
    right: int,
    bottom: int,
) -> dict[str, int] | None:
    """Pick a target in the open direction; flip if the wall is too close."""
    half = width / 2
    cx = wx + half
    margin = MOVE_MARGIN
    facing = choose_facing(facing, {"cx": cx, "left": left, "right": right, "margin": margin})
    sign = -1 if facing == "left" else 1
    lo = left + margin + half
    hi = right - margin - half
    if hi <= lo:
        return None
    if sign > 0:
        max_dist = min(MOVE_MAX_PX, hi - cx)
    else:
        max_dist = min(MOVE_MAX_PX, cx - lo)
    if max_dist < 36:
        facing = "left" if facing == "right" else "right"
        sign = -1 if facing == "left" else 1
        max_dist = min(MOVE_MAX_PX, (hi - cx) if sign > 0 else (cx - lo))
    if max_dist < 36:
        return None
    min_dist = min(MOVE_MIN_PX, max_dist)
    distance = random.randint(int(min_dist), int(max_dist))
    target_cx = cx + sign * distance
    target_cx = min(max(target_cx, lo), hi)
    comfort = bottom - height - 64
    if wy < top + margin:
        target_y = top + margin
    elif wy + height > bottom - margin:
        target_y = bottom - height - margin
    elif random.random() < 0.35:
        target_y = int(round(wy * 0.7 + comfort * 0.3))
        target_y = min(max(target_y, top + margin), max(top + margin, bottom - height - margin))
    else:
        target_y = wy
    return {
        "facing": facing,
        "target_x": int(round(target_cx - half)),
        "target_y": int(round(target_y)),
    }
