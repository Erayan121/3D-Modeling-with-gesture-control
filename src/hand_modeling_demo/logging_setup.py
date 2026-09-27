from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Mapping
from uuid import uuid4


ALLOWED_FIELDS = frozenset(
    {
        "state",
        "mode",
        "command",
        "error_type",
        "duration_ms",
        "processed_fps",
        "queue_depth",
        "entity_count",
    }
)


class EventLogger:
    def __init__(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(f"hand_modeling_demo.{uuid4().hex}")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        self.handler = RotatingFileHandler(
            path,
            maxBytes=2 * 1024 * 1024,
            backupCount=2,
            encoding="utf-8",
        )
        self.handler.setFormatter(logging.Formatter("%(message)s"))
        self.logger.addHandler(self.handler)

    def write(self, kind: str, fields: Mapping[str, object]) -> None:
        log_event(self.logger, kind, fields)

    def close(self) -> None:
        self.handler.flush()
        self.handler.close()
        self.logger.removeHandler(self.handler)


def configure_logging(path: str | Path) -> EventLogger:
    return EventLogger(path)


def log_event(logger: logging.Logger, kind: str, fields: Mapping[str, object]) -> None:
    unknown = set(fields) - ALLOWED_FIELDS
    if unknown:
        raise TypeError(f"private or unsupported log fields: {sorted(unknown)}")
    logger.info(json.dumps({"event": kind, **fields}, ensure_ascii=False))
