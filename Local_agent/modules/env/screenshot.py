from __future__ import annotations

import base64
import io
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from modules.env.config import env_settings

logger = logging.getLogger(__name__)


def encode_pil_to_payload(
    image,
    *,
    save_dir: Path | None = None,
    filename_prefix: str = "shot",
) -> dict[str, Any]:
    """PIL Image → JPEG Base64，并写入 data 目录。"""
    from PIL import Image

    width, height = image.size
    max_w = env_settings.screenshot_max_width
    if width > max_w:
        ratio = max_w / width
        image = image.resize((max_w, int(height * ratio)), Image.Resampling.LANCZOS)
        width, height = image.size

    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=env_settings.screenshot_jpeg_quality, optimize=True)
    raw = buffer.getvalue()

    result: dict[str, Any] = {
        "format": "jpeg",
        "width": width,
        "height": height,
        "size_bytes": len(raw),
        "image_base64": base64.b64encode(raw).decode("ascii"),
    }

    target_dir = save_dir or (env_settings.data_dir / "screenshots")
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = target_dir / f"{filename_prefix}_{stamp}.jpg"
    path.write_bytes(raw)
    result["saved_path"] = str(path)
    return result


def capture_desktop_jpeg(*, save_dir: Path | None = None) -> dict[str, Any]:
    """截取当前桌面，压缩为 JPEG，可选保存到本地目录。"""
    try:
        from PIL import ImageGrab
    except ImportError as exc:
        raise RuntimeError("Pillow 未安装，无法截图") from exc

    image = ImageGrab.grab(all_screens=True)
    result = encode_pil_to_payload(image, save_dir=save_dir, filename_prefix="shot")
    logger.info("Screenshot saved to %s", result.get("saved_path"))
    return result


async def capture_desktop_async(*, save_dir: Path | None = None) -> dict[str, Any]:
    import asyncio

    return await asyncio.to_thread(capture_desktop_jpeg, save_dir=save_dir)
