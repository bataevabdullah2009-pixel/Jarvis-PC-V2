from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ListenerState:
    running: bool = False
    wake_word_enabled: bool = False
    clap_enabled: bool = False
    device_id: str = "default"

    def to_dict(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "wake_word": self.wake_word_enabled,
            "clap": self.clap_enabled,
            "device_id": self.device_id,
        }


listener_state = ListenerState()


def start_listener(*, wake_word: bool = True, clap: bool = True, device_id: str = "default") -> dict[str, Any]:
    listener_state.running = True
    listener_state.wake_word_enabled = wake_word
    listener_state.clap_enabled = clap
    listener_state.device_id = device_id
    return listener_state.to_dict()


def stop_listener() -> dict[str, Any]:
    listener_state.running = False
    listener_state.wake_word_enabled = False
    listener_state.clap_enabled = False
    return listener_state.to_dict()
