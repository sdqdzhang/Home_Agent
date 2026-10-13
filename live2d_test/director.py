"""PresentationIntent → a concrete WebM clip name (dsh-pet link mapping)."""

from __future__ import annotations

from catalog import Catalog, pick_from_pool, pick_keyword
from mapper import PresentationIntent

BUSY_MAIN = ("写代码", "吃Token")
BUSY_BREAK = ("轻快记录", "漂浮踏步")
BUSY_MAIN_KEYS = ("代码", "Token", "忙碌点按", "敲击桌面")
BUSY_BREAK_KEYS = ("轻快记录", "踏步", "伸懒腰")
THINK_KEYS = ("深度思考", "思考冒泡")
WRAP_KEYS = ("清点归档", "归档")
FLINCH_KEYS = ("吓",)
NOD_KEYS = ("雀跃", "庆祝")
ALERT_KEYS = ("垂头叹气", "皱眉", "袋空", "哈欠")
TALK_KEYS = ("哼歌", "礼仪", "挥手")
TIRED_KEYS = ("哈欠", "小憩", "打瞌睡", "沉眠")


def oneshot_name(kind: str, cat: Catalog) -> str | None:
    acts = cat.cats["acts"]
    if kind == "poke":
        return pick_from_pool(cat.cats["clicks"])
    if kind == "flinch":
        return pick_keyword(acts, list(FLINCH_KEYS)) or pick_from_pool(cat.cats["clicks"])
    if kind == "nod":
        return pick_keyword(acts, list(NOD_KEYS)) or pick_from_pool(acts)
    return pick_from_pool(cat.cats["clicks"])


def next_busy(cat: Catalog, seq: int) -> str | None:
    """写代码 / 吃Token 交替，每第 3 次插播摸鱼。seq 从 1 起。"""
    acts = cat.cats["acts"]
    moves = cat.cats["moves"]
    main = [n for n in BUSY_MAIN if n in acts]
    brk = [n for n in BUSY_BREAK if n in acts or n in moves]
    if not main:
        main = [n for n in acts if any(k in n for k in BUSY_MAIN_KEYS)]
    if not brk:
        brk = [n for n in [*acts, *moves] if any(k in n for k in BUSY_BREAK_KEYS)]
    if not main:
        main = list(acts)
    if not main and not brk:
        return cat.idle
    if brk and seq % 3 == 0:
        return brk[(seq // 3 - 1) % len(brk)]
    if main:
        return main[(seq - 1) % len(main)]
    return brk[(seq - 1) % len(brk)]


def link_clip(intent: PresentationIntent, cat: Catalog, busy_seq: int) -> str | None:
    """None means 'run the idle animation chain'."""
    acts = cat.cats["acts"]
    if intent.alert and intent.alert != "none":
        return pick_keyword(acts, list(ALERT_KEYS)) or pick_keyword(acts, list(TIRED_KEYS)) or cat.idle
    if intent.motion == "work":
        return next_busy(cat, busy_seq)
    if intent.motion == "think":
        return pick_keyword(acts, list(THINK_KEYS)) or next_busy(cat, busy_seq)
    if intent.motion == "wrap":
        return pick_keyword(acts, list(WRAP_KEYS)) or pick_keyword(acts, ["工作"]) or next_busy(cat, busy_seq)
    if intent.talking:
        return pick_keyword(acts, list(TALK_KEYS)) or pick_from_pool(cat.cats["clicks"])
    if intent.gaze == "aside" and cat.turn:
        return cat.turn
    return None


def mode_key(intent: PresentationIntent) -> tuple:
    return (
        intent.motion,
        intent.alert or "none",
        bool(intent.talking),
        intent.gaze,
        intent.one_shot,
    )
