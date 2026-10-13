"""Copy dsh-pet shenshen WebM into overlay/models/shenshen/videos."""

from __future__ import annotations

from catalog import LOCAL_VIDEOS, ensure_videos


def main() -> int:
    path = ensure_videos()
    n = len(list(path.rglob("*.webm")))
    print(f"ready: {path} ({n} webm)")
    print("url: /models/shenshen/videos/…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
