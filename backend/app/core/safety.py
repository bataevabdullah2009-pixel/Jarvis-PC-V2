from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import Settings


SAFE_ACTIONS = {
    "open_url",
    "play_music_search",
    "read_news",
    "location_search",
    "volume_up",
    "volume_down",
    "screenshot",
}

CONFIRMATION_ACTIONS = {
    "shutdown",
    "restart",
    "close_process",
    "run_shell",
    "install_package",
    "move_file",
    "edit_settings",
}

DEV_MODE_ONLY_ACTIONS = {
    "delete_file",
    "format_disk",
    "registry_edit",
    "disable_defender",
}

DANGEROUS_SHELL_PATTERN = re.compile(r"\b(del|rm|format|reg|Remove-Item|rmdir)\b", re.IGNORECASE)


@dataclass(slots=True)
class SafetyDecision:
    allowed: bool
    requires_confirmation: bool
    forbidden: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "requires_confirmation": self.requires_confirmation,
            "forbidden": self.forbidden,
            "reason": self.reason,
        }


class SafetyService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def validate(self, action: dict[str, Any]) -> SafetyDecision:
        action_type = str(action.get("type", "")).strip()
        target = str(action.get("target", "")).strip()

        if action_type in DEV_MODE_ONLY_ACTIONS:
            return SafetyDecision(False, False, True, f"{action_type} запрещено без dev mode")

        if action_type == "run_shell" and DANGEROUS_SHELL_PATTERN.search(target):
            return SafetyDecision(False, False, True, "shell-команда содержит опасный токен")

        if action_type == "open_app":
            if target.lower() in self.settings.allowed_apps:
                return SafetyDecision(True, False, False, "приложение находится в allowlist")
            return SafetyDecision(False, True, False, "неизвестное приложение требует подтверждения")

        if action_type == "open_folder":
            return self._validate_folder(target)

        if action_type in SAFE_ACTIONS:
            return SafetyDecision(True, False, False, "безопасное действие")

        if action_type in CONFIRMATION_ACTIONS:
            return SafetyDecision(False, True, False, "действие требует подтверждения")

        return SafetyDecision(False, True, False, "неизвестное действие требует подтверждения")

    def _validate_folder(self, target: str) -> SafetyDecision:
        if not target:
            return SafetyDecision(False, True, False, "папка не указана")

        target_path = Path(target)
        for allowed in self.settings.allowed_folders:
            try:
                allowed_path = Path(allowed)
                if target_path == allowed_path or allowed_path in target_path.parents:
                    return SafetyDecision(True, False, False, "папка находится в allowlist")
            except OSError:
                continue

        return SafetyDecision(False, True, False, "папка не находится в allowlist")

