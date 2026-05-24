from __future__ import annotations

import time
import threading
from typing import Any


class PendingConfirmationStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: dict[str, Any] | None = None

    def set_pending(self, action: dict[str, Any], summary: str, lifetime_seconds: float = 30.0) -> dict[str, Any]:
        """Saves a pending action to confirm."""
        with self._lock:
            now = time.time()
            self._pending = {
                "id": f"act_{int(now)}",
                "created_at": now,
                "expires_at": now + lifetime_seconds,
                "action": action,
                "summary": summary
            }
            return self._pending

    def get_pending(self) -> dict[str, Any] | None:
        """Retrieves active pending action if it has not expired yet."""
        with self._lock:
            if not self._pending:
                return None
            
            # Check expiration
            if time.time() > self._pending["expires_at"]:
                self._pending = None
                return None
                
            return self._pending

    def clear_pending(self) -> None:
        """Clears the pending action."""
        with self._lock:
            self._pending = None

    def is_expired(self) -> bool:
        """Checks if a pending action is set but expired."""
        with self._lock:
            if not self._pending:
                return False
            return time.time() > self._pending["expires_at"]


# Global pending confirmation store
pending_store = PendingConfirmationStore()
