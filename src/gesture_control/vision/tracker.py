"""MediaPipe LIVE_STREAM adapter with position-associated handedness hysteresis."""

from collections.abc import Callable
from dataclasses import dataclass
from itertools import product
from math import hypot, isfinite
from pathlib import Path
from threading import Event, Lock, RLock, Thread, local

import cv2
import mediapipe as mp

from gesture_control.core.config import AppConfig
from gesture_control.core.models import HandObservation, HandSide, Point


@dataclass
class _Track:
    center: tuple[float, float]
    side: HandSide
    last_seen_ms: int
    conflict_count: int = 0


class HandTracker:
    # A distant new detection must not inherit the role of a vanished hand.
    MAX_ASSOCIATION_DISTANCE = 0.25

    def __init__(self, config: AppConfig, landmarker=None,
                 on_result: Callable[[tuple[HandObservation, ...], int], None] | None = None,
                 *, model_path: str | Path | None = None):
        self.config = config
        self._on_result = on_result or (lambda hands, timestamp_ms: None)
        self._submit_lock = Lock()
        self._result_lock = RLock()
        self._publication_lock = Lock()
        self._callback_context = local()
        self._cleanup_lock = Lock()
        self._cleanup_done = Event()
        self._cleanup_thread: Thread | None = None
        # Shutdown requested and native cleanup completed are distinct states.
        self._closed = False
        self._last_submitted_ms = -1
        self._last_result_ms = -1
        self._tracks: list[_Track] = []
        self._latest: tuple[HandObservation, ...] = ()
        self.error: Exception | None = None
        if landmarker is None:
            path = Path(model_path) if model_path is not None else Path(__file__).resolve().parents[1] / "resources" / "hand_landmarker.task"
            options = mp.tasks.vision.HandLandmarkerOptions(
                # Native Windows file loading fails for some Unicode paths.
                # Python reads the bundled local bytes without that limitation.
                base_options=mp.tasks.BaseOptions(model_asset_buffer=path.read_bytes()),
                running_mode=mp.tasks.vision.RunningMode.LIVE_STREAM,
                num_hands=2,
                min_hand_detection_confidence=config.min_hand_confidence,
                min_hand_presence_confidence=config.min_hand_confidence,
                min_tracking_confidence=config.min_hand_confidence,
                result_callback=self._media_pipe_result,
            )
            landmarker = mp.tasks.vision.HandLandmarker.create_from_options(options)
        self._landmarker = landmarker

    @property
    def latest(self) -> tuple[HandObservation, ...]:
        with self._result_lock:
            return self._latest

    @property
    def cleanup_complete(self) -> bool:
        return self._cleanup_done.is_set()

    def submit(self, frame, timestamp_ms: int) -> None:
        with self._submit_lock:
            if self._closed:
                raise RuntimeError("Hand tracker is closed")
            timestamp_ms = max(int(timestamp_ms), self._last_submitted_ms + 1)
            try:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                self._last_submitted_ms = timestamp_ms
                self._landmarker.detect_async(image, timestamp_ms)
            except Exception as exc:
                self.error = exc
                raise

    def _media_pipe_result(self, result, output_image, timestamp_ms: int) -> None:
        # Exceptions must not escape a native callback; controller polls error.
        try:
            self.accept_result(result, timestamp_ms)
        except Exception as exc:
            with self._result_lock:
                self.error = exc
                self._latest = ()

    @staticmethod
    def _detections(result, timestamp_ms, threshold, swap_handedness=False):
        detections = []
        for landmarks, categories in zip(result.hand_landmarks, result.handedness):
            if len(landmarks) != 21 or not categories:
                continue
            category = max(categories, key=lambda item: item.score)
            score = float(category.score)
            if not isfinite(score) or not threshold <= score <= 1.0:
                continue
            try:
                side = HandSide(category.category_name.lower())
                if swap_handedness:
                    side = HandSide.RIGHT if side is HandSide.LEFT else HandSide.LEFT
                points = tuple(Point(float(p.x), float(p.y), float(p.z)) for p in landmarks)
            except (AttributeError, TypeError, ValueError):
                continue
            if not all(isfinite(v) for p in points for v in (p.x, p.y, p.z)):
                continue
            center = (sum(points[i].x for i in (0, 5, 9, 13, 17)) / 5,
                      sum(points[i].y for i in (0, 5, 9, 13, 17)) / 5)
            detections.append((HandObservation(side, score, points, timestamp_ms), center))
        return sorted(detections, key=lambda item: item[0].confidence, reverse=True)[:2]

    def _associate(self, detections):
        # At most two hands: exhaustively minimize total distance with one-to-one
        # assignments. Matching must not depend on label or result-list order.
        best, best_key = (), (1, float("inf"))
        for assignment in product(range(-1, len(self._tracks)), repeat=len(detections)):
            assigned = [i for i in assignment if i >= 0]
            if len(set(assigned)) != len(assigned):
                continue
            distances = [hypot(detections[j][1][0] - self._tracks[i].center[0],
                               detections[j][1][1] - self._tracks[i].center[1])
                         for j, i in enumerate(assignment) if i >= 0]
            if any(d > self.MAX_ASSOCIATION_DISTANCE for d in distances):
                continue
            key = (-len(assigned), sum(distances))
            if key < best_key:
                best, best_key = assignment, key
        return best

    def accept_result(self, result, timestamp_ms: int) -> None:
        with self._result_lock:
            if self._closed or timestamp_ms <= self._last_result_ms:
                return
            self._last_result_ms = timestamp_ms
            detections = self._detections(
                result, timestamp_ms, self.config.min_hand_confidence,
                self.config.swap_handedness,
            )
            self._tracks = [t for t in self._tracks if timestamp_ms - t.last_seen_ms <= self.config.tracking_loss_release_ms]
            assignments = self._associate(detections)
            seen = set(i for i in assignments if i >= 0)
            for index, track in enumerate(self._tracks):
                if index not in seen:
                    track.conflict_count = 0
            active, observations = [], []
            for (observation, center), index in zip(detections, assignments):
                if index < 0:
                    track = _Track(center, observation.side, timestamp_ms)
                else:
                    track = self._tracks[index]
                    if observation.side == track.side:
                        track.conflict_count = 0
                    else:
                        track.conflict_count += 1
                        if track.conflict_count >= 3:
                            track.side = observation.side
                            track.conflict_count = 0
                    track.center, track.last_seen_ms = center, timestamp_ms
                active.append(track)
                observations.append(HandObservation(track.side, observation.confidence, observation.landmarks, timestamp_ms))
            # Keep at most two physical tracks, including briefly missing hands.
            missing = [t for i, t in enumerate(self._tracks) if i not in seen]
            self._tracks = (active + missing)[:2]
            # Conflicting initial labels must not overwrite each other in the
            # controller's HandSide map. Confidence order keeps the stronger one;
            # both physical tracks remain eligible for subsequent stabilization.
            by_side = {}
            for observation in observations:
                by_side.setdefault(observation.side, observation)
            self._latest = tuple(by_side.values())
            emitted = self._latest
        # Gate publication separately from state: close invalidates pending
        # results, then waits for an already-running application callback.
        with self._publication_lock:
            with self._result_lock:
                if self._closed or timestamp_ms != self._last_result_ms:
                    return
            self._callback_context.active = True
            try:
                # Another thread may read latest while this callback runs.
                # Empty detections still identify the completed submission.
                self._on_result(emitted, timestamp_ms)
            finally:
                self._callback_context.active = False

    def close(self) -> None:
        """Invalidate publication; finish cleanup, or defer it from a callback.

        Ordinary callers wait for in-flight publication/native cleanup. Callback
        callers only request shutdown, since native close joins that dispatcher;
        a worker finishes teardown and cleanup_complete signals completion.
        """
        with self._result_lock:
            self._closed = True
            self._latest = ()
            self._tracks.clear()
            if getattr(self._callback_context, "active", False):
                if self._cleanup_thread is None or not self._cleanup_thread.is_alive():
                    self._cleanup_thread = Thread(target=self._deferred_close, daemon=True, name="hand-tracker-close")
                    self._cleanup_thread.start()
                return
        self._finish_close()

    def _deferred_close(self) -> None:
        try:
            self._finish_close()
        except Exception as exc:
            # Cleanup stays incomplete so a later ordinary close can retry.
            self.error = exc

    def _finish_close(self) -> None:
        with self._cleanup_lock:
            if self._cleanup_done.is_set():
                return
            # Let pre-shutdown submissions and publications exit. Do not hold
            # either gate during native close, which may drain queued callbacks.
            with self._submit_lock:
                pass
            with self._publication_lock:
                pass
            try:
                self._landmarker.close()
            except Exception as exc:
                self.error = exc
                raise
            self._cleanup_done.set()
