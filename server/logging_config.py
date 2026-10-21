"""Structured (one JSON object per line) logging for the backend, stdlib only."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

_STD_ATTRS = set(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in vars(record).items():
            if key not in _STD_ATTRS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str | None = None) -> None:
    """Install the JSON handler on the `aura` logger tree (idempotent)."""
    root = logging.getLogger("aura")
    if any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level or os.environ.get("AURA_LOG_LEVEL") or "INFO")
    root.propagate = False


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"aura.{name}")
