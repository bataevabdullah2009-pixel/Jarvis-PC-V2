from __future__ import annotations

from urllib.parse import quote

from app.core.config import Settings
from app.pc.browser import open_url
from app.pc.hotkeys import send_enter, send_media_play_pause


def play_music_search(
    settings: Settings,
    *,
    query: str,
    dry_run: bool = False,
    load_delay_seconds: float = 4,
) -> dict:
    url = settings.kion_music_search_url.format(query=quote(query))
    actions = [open_url(url, dry_run=dry_run)]

    # KION/MTS Music is a browser player. Real autoplay may be blocked by browser
    # policy or login state, so we attempt playback and report that separately.
    actions.append(send_enter(dry_run=dry_run, delay_seconds=load_delay_seconds if not dry_run else 0))
    actions.append(send_media_play_pause(dry_run=dry_run, delay_seconds=0.5 if not dry_run else 0))

    playback_attempted = all(action["status"] in {"completed", "dry_run"} for action in actions[1:])
    return {
        "type": "play_music_search",
        "target": query,
        "url": url,
        "status": "playback_attempted" if playback_attempted else "playback_attempt_failed",
        "provider": "kion_music",
        "actions": actions,
        "playback_attempted": playback_attempted,
        "note": "Browser/login/autoplay policy can still block real playback.",
    }
