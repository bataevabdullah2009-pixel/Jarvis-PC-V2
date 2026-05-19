from __future__ import annotations

from app.core.config import Settings
from app.music.kion_music import play_music_search


TRIGGERS = {
    "открой музыку",
    "включи музыку",
    "найди back in black",
    "включи back in black",
    "поставь back in black",
    "back in black",
}


def run(settings: Settings, *, dry_run: bool = False, query: str = "Back in Black") -> dict:
    action = play_music_search(settings, query=query, dry_run=dry_run)
    response_text = f"Я открыл {query}, сэр."

    return {
        "scenario": "music",
        "status": "completed",
        "response_text": response_text,
        "actions": [action],
        "warnings": [] if action.get("playback_attempted") else [action.get("note", "Autoplay may require a browser click.")],
    }
