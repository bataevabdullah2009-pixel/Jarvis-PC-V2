from __future__ import annotations

from app.core.config import Settings
from app.music.kion_music import play_music_search


TRIGGERS = {
    "джарвис я вернулся",
    "я вернулся",
    "я дома",
    "джарвис я дома",
    "стартовый режим",
}


def run(settings: Settings, *, dry_run: bool = False) -> dict:
    action = play_music_search(settings, query="Back in Black", dry_run=dry_run)
    return {
        "scenario": "welcome_home",
        "status": "completed",
        "response_text": "С возвращением, сэр. Я открыл Back in Black.",
        "actions": [action],
        "warnings": [] if action.get("playback_attempted") else [action.get("note", "Autoplay may require a browser click.")],
    }
