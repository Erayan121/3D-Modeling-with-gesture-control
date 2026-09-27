from math import cos, pi, sin

from hand_modeling_demo.config import Settings
from hand_modeling_demo.domain import Vec2
from hand_modeling_demo.gestures.circles import CircleEvent, CircleRecognizer


def circle_points(*, turns: float, clockwise: bool, duration_ms: int, radius: float = 0.12):
    count = 81
    direction = 1.0 if clockwise else -1.0
    return [
        (
            Vec2(
                0.5 + radius * cos(direction * turns * 2 * pi * index / (count - 1)),
                0.5 + radius * sin(direction * turns * 2 * pi * index / (count - 1)),
            ),
            round(duration_ms * index / (count - 1)),
        )
        for index in range(count)
    ]


def feed(recognizer: CircleRecognizer, points):
    return [event for point, timestamp in points if (event := recognizer.update(point, timestamp))]


def test_two_clockwise_turns_emit_redo_once() -> None:
    recognizer = CircleRecognizer(Settings())

    assert feed(recognizer, circle_points(turns=2, clockwise=True, duration_ms=1800)) == [
        CircleEvent.REDO
    ]
    assert recognizer.update(Vec2(0.5, 0.5), 2200) is None


def test_two_counterclockwise_turns_emit_undo() -> None:
    recognizer = CircleRecognizer(Settings())

    assert feed(recognizer, circle_points(turns=2, clockwise=False, duration_ms=1800)) == [
        CircleEvent.UNDO
    ]


def test_small_open_and_slow_paths_do_not_trigger() -> None:
    settings = Settings(circle_max_ms=2500)
    tiny = circle_points(turns=2, clockwise=True, duration_ms=1800, radius=0.02)
    open_arc = circle_points(turns=1.75, clockwise=True, duration_ms=1800)
    slow = circle_points(turns=2, clockwise=True, duration_ms=4000)

    assert feed(CircleRecognizer(settings), tiny) == []
    assert feed(CircleRecognizer(settings), open_arc) == []
    assert feed(CircleRecognizer(settings), slow) == []


def test_reset_rearms_after_one_trigger() -> None:
    recognizer = CircleRecognizer(Settings())
    path = circle_points(turns=2, clockwise=True, duration_ms=1800)
    assert feed(recognizer, path) == [CircleEvent.REDO]
    assert feed(recognizer, path) == []

    recognizer.reset()

    assert feed(recognizer, path) == [CircleEvent.REDO]
