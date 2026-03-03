"""Minimal in-process metric event sink for Q2 operational reporting."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

METRICS_LOG_PATH = Path("runs/metrics_q2_events.jsonl")


def _normalize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def emit_q2_metric_event(event_type: str, **fields: Any) -> None:
    """Append one JSONL metric event used by `structured-search metrics report`."""
    payload = {
        "event_type": event_type,
        "recorded_at": datetime.now(UTC).isoformat(),
    }
    payload.update({key: _normalize_value(value) for key, value in fields.items()})
    METRICS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with METRICS_LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
