from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from app.core.config import Settings


def open_app(app_name: str, settings: Settings, *, dry_run: bool = False) -> dict[str, Any]:
    normalized = app_name.lower().strip()
    candidates = settings.allowed_apps.get(normalized)

    if not candidates:
        return {
            "type": "open_app",
            "target": app_name,
            "status": "blocked",
            "message": "Приложение не находится в allowlist.",
        }

    if dry_run:
        return {
            "type": "open_app",
            "target": app_name,
            "status": "dry_run",
            "candidate": candidates[0],
        }

    for candidate in candidates:
        if candidate == "start":
            os.startfile("https://www.google.com")  # type: ignore[attr-defined]
            return {"type": "open_app", "target": app_name, "status": "completed", "candidate": candidate}
        executable = shutil.which(candidate)
        if executable:
            subprocess.Popen([executable], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {
                "type": "open_app",
                "target": app_name,
                "status": "completed",
                "candidate": candidate,
            }

    return {
        "type": "open_app",
        "target": app_name,
        "status": "not_found",
        "message": f"Не удалось найти {app_name} в PATH.",
    }


def open_folder(path: str, *, dry_run: bool = False) -> dict[str, Any]:
    if dry_run:
        return {
            "type": "open_folder",
            "target": path,
            "status": "dry_run",
        }

    folder = Path(path)
    if not folder.exists():
        return {
            "type": "open_folder",
            "target": path,
            "status": "not_found",
            "message": "Папка не найдена.",
        }

    os.startfile(str(folder))  # type: ignore[attr-defined]
    return {
        "type": "open_folder",
        "target": path,
        "status": "completed",
    }
