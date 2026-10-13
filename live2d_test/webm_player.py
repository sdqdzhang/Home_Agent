"""Decode VP9-alpha WebM to RGBA, using dsh-pet's playback contract.

Same decode path (imageio-ffmpeg, libvpx-vp9, RGBA32). The smoothness
bits copied from ``webm_clip`` — not the process-lifetime machinery:

- reader stamps each frame with a 0-based source-timeline index
- queue-full drops a frame but still advances that index (wall-clock)
- GUI QTimer takes one queued frame per tick (never drain-to-latest)
- idle throttle: timer interval × N and reader blocks instead of dropping
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Any, Callable, Iterable

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QImage

from catalog import CANVAS_H, CANVAS_W, FRAME_MS

_INPUT = ["-c:v", "libvpx-vp9", "-threads", "1"]
PLAYBACK_FPS = 1000.0 / FRAME_MS  # 24fps fallback, same as dsh-pet
_QUEUE_SIZE = 8
_END_MARKER_TIMEOUT = 5.0


def timer_interval_ms(
    fps: float,
    *,
    speed: float = 1.0,
    throttle: int = 1,
    fallback_ms: int = FRAME_MS,
) -> int:
    speed = max(0.1, float(speed))
    if fps > 0:
        base = max(1, int(round(1000 / (fps * speed))))
    else:
        base = max(1, int(round(fallback_ms / speed)))
    return max(1, base * max(1, int(throttle)))


def stamp_source_indices(
    frames: Iterable[bytes],
    q,
    is_stopped: Callable[[], bool],
    timeout: float = 0.2,
    throttled: Callable[[], bool] | None = None,
) -> None:
    """Tag decoded frames with source-timeline indices, then enqueue.

    Queue items are ``(rgba_bytes, src_idx)``. When the queue is full the
    unthrottled path drops the frame but still advances ``src_idx``, so a
    later display frame stays on the video clock. The throttled path retries
    the same frame (backpressure) and only advances after a successful put.
    """
    src_idx = 0
    it = iter(frames)
    while True:
        try:
            frame = next(it)
        except StopIteration:
            break
        if is_stopped():
            break
        if throttled is not None and throttled():
            while not is_stopped():
                try:
                    q.put((frame, src_idx), timeout=timeout)
                    src_idx += 1
                    break
                except queue.Full:
                    continue
        else:
            try:
                q.put((frame, src_idx), timeout=timeout)
            except queue.Full:
                pass
            src_idx += 1


def _offer(out_q: queue.Queue, gen: int, kind: str, payload: Any) -> None:
    try:
        out_q.put((gen, kind, payload), timeout=0.2)
    except queue.Full:
        pass


def _put_end(
    out_q: queue.Queue,
    gen: int,
    stop_evt: threading.Event,
    current_gen: Callable[[], int],
    error: str | None = None,
) -> None:
    deadline = time.monotonic() + _END_MARKER_TIMEOUT
    kind = "error" if error else "end"
    while not stop_evt.is_set() and current_gen() == gen:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        try:
            out_q.put((gen, kind, error), timeout=min(0.5, remaining))
            return
        except queue.Full:
            continue


class _FrameSink:
    """Wrap ``(data, src_idx)`` puts as tagged player-queue items."""

    def __init__(self, q: queue.Queue, gen: int) -> None:
        self._q = q
        self._gen = gen

    def put(self, item, timeout: float = 0.2) -> None:
        data, src_idx = item
        self._q.put((self._gen, "frame", data, src_idx), timeout=timeout)


class WebmPlayer(QObject):
    frame_ready = Signal(object)  # QImage
    finished = Signal()
    meta_ready = Signal(float)  # duration seconds

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._gen = 0
        self._stop = threading.Event()
        self._queue: queue.Queue = queue.Queue(maxsize=_QUEUE_SIZE)
        self._fps = PLAYBACK_FPS
        self._speed = 1.0
        self._src_idx = 0
        self._consumed = 0
        self._playing = False
        self._frame_w = CANVAS_W
        self._frame_h = CANVAS_H
        self._decode_throttle_divisor = 1
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(self._timer_interval())
        self._timer.timeout.connect(self._pump)

    @property
    def elapsed(self) -> float:
        fps = max(self._fps * self._speed, 1e-6)
        return self._src_idx / fps

    @property
    def decode_throttle_divisor(self) -> int:
        return self._decode_throttle_divisor

    def set_decode_throttle(self, divisor: int) -> None:
        divisor = max(1, int(divisor))
        if divisor == self._decode_throttle_divisor:
            return
        self._decode_throttle_divisor = divisor
        self._timer.setInterval(self._timer_interval())

    def play(self, path: str) -> None:
        self.stop()
        self._gen += 1
        gen = self._gen
        stop_evt = threading.Event()
        out_q: queue.Queue = queue.Queue(maxsize=_QUEUE_SIZE)
        self._stop = stop_evt
        self._queue = out_q
        self._src_idx = 0
        self._consumed = 0
        self._playing = True
        threading.Thread(
            target=self._reader,
            args=(str(path), gen, stop_evt, out_q),
            daemon=True,
            name="ha-webm",
        ).start()
        self._timer.start(self._timer_interval())

    def stop(self) -> None:
        self._playing = False
        self._stop.set()
        self._timer.stop()
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def shutdown(self) -> None:
        self.stop()

    def _timer_interval(self) -> int:
        return timer_interval_ms(
            self._fps,
            speed=self._speed,
            throttle=self._decode_throttle_divisor,
        )

    def _reader(self, path: str, gen: int, stop_evt: threading.Event, out_q: queue.Queue) -> None:
        import imageio_ffmpeg

        stream = None
        try:
            stream = imageio_ffmpeg.read_frames(
                path,
                pix_fmt="rgba",
                bits_per_pixel=32,
                input_params=list(_INPUT),
            )
            meta = next(stream)
            if gen != self._gen or stop_evt.is_set():
                return
            self._apply_meta(meta if isinstance(meta, dict) else {})
            _offer(out_q, gen, "meta", meta if isinstance(meta, dict) else {})
            stamp_source_indices(
                stream,
                _FrameSink(out_q, gen),
                lambda: gen != self._gen or stop_evt.is_set(),
                throttled=lambda: self._decode_throttle_divisor > 1,
            )
            if gen == self._gen and not stop_evt.is_set():
                _put_end(out_q, gen, stop_evt, lambda: self._gen)
        except Exception as exc:
            _put_end(out_q, gen, stop_evt, lambda: self._gen, error=str(exc))
        finally:
            if stream is not None:
                try:
                    stream.close()
                except Exception:
                    pass

    def _pump(self) -> None:
        # One display frame per tick. Meta/stale items may be drained first.
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                return
            gen = item[0]
            if gen != self._gen:
                continue
            kind = item[1]
            if kind == "meta":
                self._on_meta(item[2] if isinstance(item[2], dict) else {})
                continue
            if kind == "frame":
                self._process_frame(item[2], item[3])
                return
            if kind in {"end", "error"}:
                if kind == "error":
                    print(f"[webm] decode failed: {item[2]}")
                if self._playing:
                    self._playing = False
                    self._timer.stop()
                    self.finished.emit()
                return

    def _apply_meta(self, meta: dict[str, Any]) -> None:
        fps = meta.get("fps")
        if fps:
            try:
                self._fps = float(fps)
            except (TypeError, ValueError):
                pass
        size = meta.get("source_size") or meta.get("size")
        if isinstance(size, (list, tuple)) and len(size) >= 2:
            self._frame_w = max(1, int(size[0]))
            self._frame_h = max(1, int(size[1]))

    def _on_meta(self, meta: dict[str, Any]) -> None:
        self._apply_meta(meta)
        self._timer.setInterval(self._timer_interval())
        duration = float(meta.get("duration") or 0)
        self.meta_ready.emit(duration)

    def _process_frame(self, data: bytes, src_idx: int) -> None:
        img = self._to_image(data)
        if img is None:
            return
        self._src_idx = int(src_idx)
        self._consumed += 1
        self.frame_ready.emit(img)

    def _to_image(self, frame: bytes) -> QImage | None:
        if not frame:
            return None
        n = len(frame)
        w, h = self._frame_w, self._frame_h
        expect = w * h * 4
        if n != expect:
            if n % 4:
                return None
            w, h = _guess_size(n // 4)
        img = QImage(frame, w, h, w * 4, QImage.Format.Format_RGBA8888)
        if img.isNull():
            return None
        return img.copy()


def _guess_size(pixels: int) -> tuple[int, int]:
    if pixels == CANVAS_W * CANVAS_H:
        return CANVAS_W, CANVAS_H
    w = 640
    if pixels % w == 0:
        return w, pixels // w
    return pixels, 1
