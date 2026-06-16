from __future__ import annotations

import logging
import platform
from pathlib import Path
from typing import Any

from modules.env.config import env_settings
from modules.env.screenshot import encode_pil_to_payload

logger = logging.getLogger(__name__)


def capture_camera_jpeg(*, save_dir: Path | None = None) -> dict[str, Any]:
    """调用默认摄像头拍一张照片，JPEG + Base64。"""
    try:
        import cv2
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("需要 opencv-python-headless 与 Pillow：pip install opencv-python-headless") from exc

    index = env_settings.camera_index
    cap = None
    backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF] if platform.system().lower() == "windows" else [cv2.CAP_V4L2]
    for backend in [None, *backends]:
        try:
            cap = cv2.VideoCapture(index, backend) if backend is not None else cv2.VideoCapture(index)
            if cap.isOpened():
                break
            cap.release()
            cap = None
        except Exception:
            if cap:
                cap.release()
            cap = None

    if cap is None or not cap.isOpened():
        raise RuntimeError(f"无法打开摄像头（index={index}），请检查设备与权限")

    try:
        for _ in range(env_settings.camera_warmup_frames):
            cap.read()
        ok, frame = cap.read()
    finally:
        cap.release()

    if not ok or frame is None:
        raise RuntimeError("摄像头未返回有效画面")

    image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    target = save_dir or (env_settings.data_dir / "camera")
    result = encode_pil_to_payload(image, save_dir=target, filename_prefix="cam")
    result["capture_type"] = "camera"
    result["camera_index"] = index
    logger.info("Camera photo saved to %s", result.get("saved_path"))
    return result


async def capture_camera_async(*, save_dir: Path | None = None) -> dict[str, Any]:
    import asyncio

    return await asyncio.to_thread(capture_camera_jpeg, save_dir=save_dir)
