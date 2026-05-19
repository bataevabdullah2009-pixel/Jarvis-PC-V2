from __future__ import annotations

from app.core.config import Settings
from app.pc.apps import open_app, open_folder
from app.pc.browser import open_url


TRIGGERS = {
    "настрой мою среду работы",
    "рабочий режим",
    "запусти рабочую среду",
    "открой мою рабочую среду",
}


def run(settings: Settings, *, dry_run: bool = False) -> dict:
    actions = [
        open_url(settings.chatgpt_url, dry_run=dry_run),
        open_app("vs code", settings, dry_run=dry_run),
        open_folder(settings.workspace_project_path, dry_run=dry_run),
    ]

    return {
        "scenario": "workspace",
        "status": "completed",
        "response_text": "Рабочая среда готова, сэр.",
        "actions": actions,
        "warnings": [],
    }
