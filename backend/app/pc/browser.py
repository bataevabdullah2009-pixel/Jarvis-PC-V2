from __future__ import annotations

import webbrowser
from typing import Any


def open_url(url: str, *, dry_run: bool = False) -> dict[str, Any]:
    if dry_run:
        return {
            "type": "open_url",
            "target": url,
            "status": "dry_run",
        }

    opened = webbrowser.open(url, new=2)
    return {
        "type": "open_url",
        "target": url,
        "status": "completed" if opened else "failed",
    }

