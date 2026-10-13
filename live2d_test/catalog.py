"""Shenshen WebM catalog — folder layout copied from dsh-pet.

Canvas 640×360, feet at y=330. Animation chain: 30% idle / 10% turn /
40% random act / 20% move. Videos live under overlay/models/shenshen/videos/.
"""

from __future__ import annotations

import json
import random
import shutil
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent
LOCAL_VIDEOS = ROOT / "overlay" / "models" / "shenshen" / "videos"
OLD_VIDEOS = ROOT / "overlay" / "models" / "deepseek" / "videos"
UPSTREAM_VIDEOS = (
    ROOT.parent / "dsh-pet-indesktop-main" / "assets" / "characters" / "shenshen" / "videos"
)

CANVAS_W = 640
CANVAS_H = 360
FEET_Y = 330
PAD = CANVAS_H - FEET_Y
FRAME_MS = 42
P_IDLE = 0.20
P_TURN = 0.30
P_ACTS = 0.70
MOVE_MIN_PX = 90
MOVE_MAX_PX = 360
MOVE_MARGIN = 28
MOVE_LEAD_SEC = 1.3
MOVE_TAIL_SEC = 1.3
DRAG_THRESHOLD = 5
DEFAULT_SCALE = 0.72
CORNER_MARGIN = 24
SCALE_STEPS = (0.5, 0.72, 0.85, 1.0)

DIR_IDLE = "idle"
DIR_TURN = "turn"
DIR_MOVE = "move"
DIR_CLICK = "click"
DIR_DRAG = "drag"
DIR_RANDOM = "random"
DIR_EVENTS = "events"

URL_PREFIX = "/models/shenshen/videos/"

GROUP_ORDER = (DIR_IDLE, DIR_TURN, DIR_MOVE, DIR_CLICK, DIR_DRAG, DIR_RANDOM, DIR_EVENTS)
GROUP_LABELS = {
    DIR_IDLE: "待机",
    DIR_TURN: "转向",
    DIR_MOVE: "移动",
    DIR_CLICK: "点击",
    DIR_DRAG: "拖拽",
    DIR_RANDOM: "日常",
    DIR_EVENTS: "事件",
}

THEME_ORDER = (
    "idle",
    "turn",
    "move",
    "click",
    "drag",
    "work",
    "eat",
    "festival",
    "play",
    "rest",
    "talk",
    "event",
    "daily",
)
THEME_LABELS = {
    "idle": "待机",
    "turn": "转向",
    "move": "移动",
    "click": "点击",
    "drag": "拖拽",
    "work": "工作",
    "eat": "吃喝",
    "festival": "节庆",
    "play": "玩耍",
    "rest": "休息",
    "talk": "碎碎念 / 说话",
    "event": "余额",
    "daily": "其它日常",
}
THEME_KEYS = {
    "work": ("写代码", "吃Token", "工作状态", "轻快记录", "深度思考"),
    "eat": ("吃", "午餐", "早餐", "晚餐", "火锅", "冰淇淋", "零食", "白饭", "是啊，吃什么"),
    "festival": (
        "月饼",
        "粽子",
        "汤圆",
        "饺子",
        "年糕",
        "青团",
        "腊八",
        "重阳",
        "长寿面",
        "福字",
        "红包",
        "孔明灯",
        "河灯",
        "烟花",
        "圣诞",
        "雪人",
        "茱萸",
        "乞巧",
        "舞狮",
        "赏月",
        "南瓜",
        "汤圆",
    ),
    "play": (
        "魔方",
        "秋千",
        "风筝",
        "水枪",
        "游戏",
        "陀螺",
        "毽子",
        "木马",
        "五子棋",
        "扑克",
        "宅舞",
        "女仆舞",
        "抛接",
        "气球",
        "笛子",
        "小提琴",
        "汽车",
        "跳舞",
        "踢毽",
        "摇扇",
        "撸猫",
        "照镜子",
    ),
    "rest": ("哈欠", "小憩", "打瞌睡", "沉眠", "伸懒腰", "刷牙"),
    "talk": ("碎碎念", "哼歌", "礼仪", "挥手"),
    "event": ("余额",),
}


def ensure_videos() -> Path:
    """Prefer the sandbox copy; migrate the old deepseek folder; else copy upstream."""
    if _has_webm(LOCAL_VIDEOS):
        return LOCAL_VIDEOS
    LOCAL_VIDEOS.parent.mkdir(parents=True, exist_ok=True)
    if _has_webm(OLD_VIDEOS):
        if LOCAL_VIDEOS.exists():
            shutil.rmtree(LOCAL_VIDEOS)
        shutil.move(str(OLD_VIDEOS), str(LOCAL_VIDEOS))
        return LOCAL_VIDEOS
    if _has_webm(UPSTREAM_VIDEOS):
        if LOCAL_VIDEOS.exists():
            shutil.rmtree(LOCAL_VIDEOS)
        shutil.copytree(UPSTREAM_VIDEOS, LOCAL_VIDEOS)
        return LOCAL_VIDEOS
    raise FileNotFoundError(
        "找不到神神 WebM。把 dsh-pet-indesktop-main 放在仓库旁，或运行 python fetch_shenshen.py"
    )


def _has_webm(path: Path) -> bool:
    return path.is_dir() and any(path.rglob("*.webm"))


def scan(video_dir: Path | None = None) -> dict:
    root = Path(video_dir) if video_dir is not None else ensure_videos()
    files: dict[str, str] = {}
    folder_files: dict[str, list[str]] = {}
    for path in sorted(root.rglob("*.webm")):
        rel = path.relative_to(root)
        name = path.stem
        files[name] = rel.as_posix()
        folder = rel.parts[0].lower() if len(rel.parts) > 1 else ""
        folder_files.setdefault(folder, []).append(name)
    cats = build_categories(folder_files)
    return {
        "root": str(root),
        "files": files,
        "folder_files": folder_files,
        "categories": cats,
    }


def build_categories(folder_files: dict[str, list[str]]) -> dict:
    idles = list(folder_files.get(DIR_IDLE, []))
    turns = list(folder_files.get(DIR_TURN, []))
    moves = list(folder_files.get(DIR_MOVE, []))
    clicks = list(folder_files.get(DIR_CLICK, []))
    drags = list(folder_files.get(DIR_DRAG, []))
    events = list(folder_files.get(DIR_EVENTS, []))
    randoms = list(folder_files.get(DIR_RANDOM, []))

    inplace = [m for m in moves if "原地" in m]
    moves = [m for m in moves if "原地" not in m]

    known = {DIR_IDLE, DIR_TURN, DIR_MOVE, DIR_CLICK, DIR_DRAG, DIR_RANDOM, DIR_EVENTS}
    extra: list[str] = []
    for folder, names in folder_files.items():
        if folder not in known:
            extra.extend(names)

    acts: list[str] = []
    seen: set[str] = set()
    for name in [*randoms, *events, *extra, *inplace]:
        if name not in seen:
            seen.add(name)
            acts.append(name)

    if not idles:
        idles = acts[:1] if acts else []

    return {
        "idle": idles[0] if idles else None,
        "turn": turns[0] if turns else None,
        "drag": drags[0] if drags else None,
        "idles": idles,
        "turns": turns,
        "moves": moves,
        "clicks": clicks,
        "events": events,
        "acts": acts,
    }


def pick_from_pool(pool: list[str], exclude: str | None = None) -> str | None:
    entries = [n for n in pool if n != exclude] or list(pool)
    return random.choice(entries) if entries else None


def pick_keyword(pool: list[str], keys: list[str], exclude: str | None = None) -> str | None:
    hits = [n for n in pool if n != exclude and any(k in n for k in keys)]
    return pick_from_pool(hits, exclude)


def roll_next(pools: dict, exclude: str | None = None) -> str | None:
    """30% idle / 10% turn / 40% act / 20% move (move pool ignores exclude)."""
    idles = pools.get("idles") or []
    turns = pools.get("turns") or []
    acts = pools.get("acts") or []
    moves = pools.get("moves") or []
    roll = random.random()
    if roll < P_IDLE:
        return pick_from_pool(idles, exclude) if idles else pick_from_pool(acts, exclude)
    if roll < P_TURN:
        return pick_from_pool(turns, exclude) if turns else pick_from_pool(acts, exclude)
    if roll < P_ACTS:
        return pick_from_pool(acts, exclude)
    return pick_from_pool(moves) if moves else pick_from_pool(acts, exclude)


def clip_url(rel: str) -> str:
    parts = str(rel).replace("\\", "/").split("/")
    return URL_PREFIX + "/".join(quote(p) for p in parts if p)


class Catalog:
    def __init__(self, video_dir: Path | None = None) -> None:
        data = scan(video_dir)
        self.root = Path(data["root"])
        self.files: dict[str, str] = data["files"]
        self.folder_files: dict[str, list[str]] = data["folder_files"]
        self.cats: dict = data["categories"]

    @property
    def idle(self) -> str | None:
        return self.cats["idle"]

    @property
    def turn(self) -> str | None:
        return self.cats["turn"]

    @property
    def drag(self) -> str | None:
        return self.cats["drag"]

    def url(self, name: str) -> str:
        rel = self.files[name]
        return clip_url(rel)

    def file_path(self, name: str) -> Path | None:
        rel = self.files.get(name)
        if not rel:
            return None
        return self.root / rel

    def list_groups(self) -> list[dict]:
        groups: list[dict] = []
        seen: set[str] = set()
        for folder in (*GROUP_ORDER, *sorted(self.folder_files)):
            if folder in seen:
                continue
            seen.add(folder)
            names = list(self.folder_files.get(folder) or [])
            if not names:
                continue
            groups.append(
                {
                    "id": folder,
                    "label": GROUP_LABELS.get(folder, folder),
                    "clips": [{"name": n, "kind": self.kind(n)} for n in names],
                }
            )
        return groups

    def theme_of(self, name: str) -> str:
        folder = ""
        rel = self.files.get(name) or ""
        if "/" in rel.replace("\\", "/"):
            folder = rel.replace("\\", "/").split("/", 1)[0].lower()
        if folder in {DIR_IDLE, DIR_TURN, DIR_MOVE, DIR_CLICK, DIR_DRAG}:
            return folder
        for theme, keys in THEME_KEYS.items():
            if any(key in name for key in keys):
                return theme
        if folder == DIR_EVENTS:
            return "event"
        return "daily"

    def list_themed_groups(self) -> list[dict]:
        buckets: dict[str, list[dict]] = {key: [] for key in THEME_ORDER}
        extra: dict[str, list[dict]] = {}
        for name in self.files:
            theme = self.theme_of(name)
            item = {"name": name, "kind": self.kind(name)}
            if theme in buckets:
                buckets[theme].append(item)
            else:
                extra.setdefault(theme, []).append(item)
        groups: list[dict] = []
        for theme in THEME_ORDER:
            clips = buckets.get(theme) or []
            if not clips:
                continue
            groups.append({"id": theme, "label": THEME_LABELS.get(theme, theme), "clips": clips})
        for theme, clips in extra.items():
            groups.append({"id": theme, "label": THEME_LABELS.get(theme, theme), "clips": clips})
        return groups

    def kind(self, name: str) -> str:
        if name in self.cats["clicks"]:
            return "click"
        if name == self.cats["drag"]:
            return "drag"
        if name in self.cats["moves"]:
            return "move"
        if name in self.cats["idles"]:
            return "idle"
        if name in self.cats["turns"]:
            return "turn"
        if name in self.cats["events"]:
            return "event"
        return "act"

    def to_public(self) -> dict:
        return {
            "canvas": {"w": CANVAS_W, "h": CANVAS_H, "feet_y": FEET_Y, "pad": PAD},
            "scale": DEFAULT_SCALE,
            "categories": self.cats,
            "groups": self.list_groups(),
            "themes": self.list_themed_groups(),
            "count": len(self.files),
        }


def write_public_json(dest: Path | None = None) -> Path:
    cat = Catalog()
    path = dest or (ROOT / "overlay" / "catalog.json")
    path.write_text(json.dumps(cat.to_public(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
