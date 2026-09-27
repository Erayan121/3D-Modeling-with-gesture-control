import json
from time import perf_counter

import numpy as np
import pytest

from hand_modeling_demo.config import Settings
from hand_modeling_demo.gestures.interpreter import GestureInterpreter, InteractionFrame
from hand_modeling_demo.logging_setup import EventLogger, configure_logging


def test_log_rejects_frames_landmarks_and_pointer_trajectories(tmp_path) -> None:
    logger = EventLogger(tmp_path / "demo.log")
    with pytest.raises(TypeError, match="frame"):
        logger.write("tracking", {"frame": np.zeros((10, 10, 3))})
    with pytest.raises(TypeError, match="landmarks"):
        logger.write("tracking", {"landmarks": [(0, 0, 0)] * 21})
    with pytest.raises(TypeError, match="pointer"):
        logger.write("tracking", {"pointer": (0.4, 0.5)})


def test_allowed_event_is_structured_utf8_json(tmp_path) -> None:
    path = tmp_path / "demo.log"
    logger = EventLogger(path)
    logger.write("command", {"command": "创建", "entity_count": 2})
    logger.close()

    record = json.loads(path.read_text(encoding="utf-8"))
    assert record == {"event": "command", "command": "创建", "entity_count": 2}


def test_configure_logging_uses_two_megabyte_rotation_and_two_backups(tmp_path) -> None:
    logger = configure_logging(tmp_path / "demo.log")
    handler = logger.handler
    assert handler.maxBytes == 2 * 1024 * 1024
    assert handler.backupCount == 2
    logger.close()


def test_interpreter_p95_is_below_five_ms() -> None:
    interpreter = GestureInterpreter(Settings())
    frame = InteractionFrame(0, {}, {}, {}, None)
    samples = []
    for _ in range(3000):
        started = perf_counter()
        interpreter.update(frame)
        samples.append(perf_counter() - started)

    assert float(np.percentile(samples, 95)) < 0.005
