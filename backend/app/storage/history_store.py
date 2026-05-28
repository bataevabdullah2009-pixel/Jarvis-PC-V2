from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from uuid import uuid4
from typing import Any, Dict, List
from app.core.config import CONFIG_DIR

logger = logging.getLogger("jarvis.history")
HISTORY_FILE_PATH = CONFIG_DIR / "command_history.json"


class HistoryStore:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(HistoryStore, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self.lock = threading.Lock()
        self._initialized = True

    def _read_history(self) -> List[Dict[str, Any]]:
        if not HISTORY_FILE_PATH.exists():
            return []
        try:
            with HISTORY_FILE_PATH.open("r", encoding="utf-8") as file:
                data = json.load(file)
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "history" in data:
                return data["history"]
            return []
        except Exception as e:
            logger.error("[HISTORY] Failed to read history JSON: %s", e)
            return []

    def _write_history(self, history: List[Dict[str, Any]]) -> None:
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with HISTORY_FILE_PATH.open("w", encoding="utf-8", newline="\n") as file:
                json.dump(history, file, ensure_ascii=False, indent=2)
                file.write("\n")
        except Exception as e:
            logger.error("[HISTORY] Failed to write history JSON: %s", e)

    def add_item(
        self,
        command_id: str | None,
        user_text: str,
        assistant_text: str,
        route: str,
        status: str,
        latency_ms: int | None = None
    ) -> Dict[str, Any]:
        with self.lock:
            history = self._read_history()
            
            # Format time as HH:MM
            now = datetime.now()
            time_str = now.strftime("%H:%M")
            
            # Ensure unique id
            item_id = command_id or f"cmd_{uuid4().hex[:12]}"
            
            # Build doubly-keyed dictionary to satisfy both UI camelCase and pytest snake_case
            item = {
                "id": item_id,
                "time": time_str,
                "user_text": user_text,
                "userText": user_text,
                "assistant_text": assistant_text,
                "assistantText": assistant_text,
                "route": route,
                "latency": latency_ms,
                "status": status,
                "created_at": datetime.utcnow().isoformat() + "Z"
            }
            
            # Insert at the beginning of the list
            history.insert(0, item)
            
            # Limit history list size to recent 100 entries to prevent file bloat
            history = history[:100]
            self._write_history(history)
            
            logger.info("[HISTORY] Logged command history item: id=%s user='%s' route=%s", item_id, user_text[:30], route)
            return item

    def get_items(self, limit: int = 24) -> List[Dict[str, Any]]:
        with self.lock:
            history = self._read_history()
            return history[:limit]

    def clear(self) -> None:
        with self.lock:
            self._write_history([])


history_store = HistoryStore()
