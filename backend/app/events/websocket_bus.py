from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


class EventBus:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def emit(self, event_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        event = {
            "event_id": f"evt_{uuid4().hex[:12]}",
            "type": event_type,
            "timestamp": datetime.now(UTC).isoformat(),
            "payload": payload or {},
        }
        self.events.append(event)
        self.events = self.events[-200:]
        return event

    def recent(self) -> list[dict[str, Any]]:
        return list(self.events)

    def recent_since(self, offset: int) -> tuple[int, list[dict[str, Any]]]:
        safe_offset = max(0, min(offset, len(self.events)))
        return len(self.events), self.events[safe_offset:]


event_bus = EventBus()
