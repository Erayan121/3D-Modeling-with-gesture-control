"""Bounded-memory camera capture. Frames are mirrored here, exactly once."""

from collections.abc import Callable, Iterable
from threading import Event, Lock, Thread, current_thread
from time import monotonic_ns
from typing import Any

import cv2
import numpy as np


class CameraSource:
    def __init__(self, index: int = 0, capture_factory: Callable[..., Any] | None = None):
        self.index = index
        self._capture_factory = capture_factory or cv2.VideoCapture
        self._capture = None
        self._thread: Thread | None = None
        self._stop = Event()
        self._lock = Lock()
        self._latest: tuple[int, np.ndarray, int] | None = None
        self._sequence = 0
        self._timestamp_ms = -1
        self.actual_size: tuple[int, int] | None = None
        self.error: Exception | None = None

    @staticmethod
    def discover(indices: Iterable[int] = range(5), capture_factory=None) -> tuple[int, ...]:
        """Explicit, bounded device probing; never called automatically on import."""
        factory = capture_factory or cv2.VideoCapture
        found = []
        for index in indices:
            for backend in (cv2.CAP_DSHOW, cv2.CAP_ANY):
                capture = None
                try:
                    capture = factory(index, backend)
                    if capture.isOpened():
                        found.append(index)
                        break
                except (OSError, cv2.error):
                    continue
                finally:
                    if capture is not None:
                        capture.release()
        return tuple(found)

    def open(self) -> None:
        if self._capture is not None:
            return
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError("Previous camera read has not stopped yet")
        self.error = None
        self.actual_size = None
        last_error = None
        for backend in (cv2.CAP_DSHOW, cv2.CAP_ANY):
            capture = None
            try:
                capture = self._capture_factory(self.index, backend)
                if not capture.isOpened():
                    continue
                for width, height in ((1280, 720), (640, 480)):
                    capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                    capture.set(cv2.CAP_PROP_FPS, 30)
                    ok, frame = capture.read()
                    if not ok or frame is None or frame.size == 0:
                        continue
                    # Drivers can silently negotiate another supported resolution.
                    actual = (frame.shape[1], frame.shape[0])
                    if (width, height) == (1280, 720) and actual != (1280, 720):
                        continue
                    self.actual_size = actual
                    self._stop.clear()
                    self._capture = capture
                    self._publish(frame)
                    self._thread = Thread(target=self._capture_loop, args=(capture,), daemon=True, name="camera-capture")
                    self._thread.start()
                    return
            except (OSError, cv2.error) as exc:
                last_error = exc
            finally:
                if capture is not None and capture is not self._capture:
                    capture.release()
        self.error = RuntimeError(f"Unable to open camera {self.index}")
        raise self.error from last_error

    def _publish(self, frame: np.ndarray) -> None:
        mirrored = cv2.flip(frame, 1)
        with self._lock:
            if self._stop.is_set():
                return
            self._sequence += 1
            self._timestamp_ms = max(monotonic_ns() // 1_000_000, self._timestamp_ms + 1)
            self._latest = (self._sequence, mirrored, self._timestamp_ms)

    def _capture_loop(self, capture) -> None:
        try:
            while not self._stop.is_set():
                ok, frame = capture.read()
                if self._stop.is_set():
                    break
                if not ok or frame is None or frame.size == 0:
                    raise RuntimeError(f"Camera {self.index} stopped delivering frames")
                self._publish(frame)
        except Exception as exc:
            with self._lock:
                if not self._stop.is_set():
                    self.error = exc
                    self._latest = None
                    self._stop.set()

    def read_latest(self) -> tuple[int, np.ndarray, int] | None:
        with self._lock:
            if self._latest is None:
                return None
            sequence, frame, timestamp = self._latest
            return sequence, frame.copy(), timestamp

    def close(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not current_thread():
            thread.join(timeout=1.0)
        capture, self._capture = self._capture, None
        if capture is not None:
            capture.release()
        with self._lock:
            self._latest = None
