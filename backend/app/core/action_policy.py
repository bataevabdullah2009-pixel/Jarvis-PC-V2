from __future__ import annotations

import re
from typing import Any

# Lists of action types
SAFE_NO_CONFIRM = {
    "open_url",
    "play_music_search",
    "read_news",
    "volume_up",
    "volume_down",
    "mute",
    "unmute",
    "screenshot",
    "respond_text",
    "reminder",
    "add_reminder",
    "welcome_home",
    "workspace",
    "news",
    "music",
    "scenario",
}

CONFIRM_REQUIRED = {
    "shutdown",
    "restart",
    "close_process",
    "close_all_apps",
    "run_shell",
    "edit_settings",
    "delete_file",
    "send_email",
    "send_message",
    "pay",
    "purchase",
    "clear_history",
}

FORBIDDEN_ACTIONS = {
    "delete_system_files",
    "format_disk",
    "registry_edit",
    "disable_defender",
    "malicious_command"
}

AFFIRMATIVE_KEYWORDS = {"подтверждаю", "да", "выполняй", "согласен", "confirm", "yes", "do it", "конечно"}
CANCEL_KEYWORDS = {"отмена", "нет", "не надо", "отменить", "cancel", "no", "stop", "прекратить"}


class ActionPolicy:
    @staticmethod
    def classify_action(action: dict[str, Any]) -> tuple[str, str]:
        """
        Classifies an action as 'SAFE', 'CONFIRM_REQUIRED', or 'FORBIDDEN'.
        Returns a tuple of (status, reason).
        """
        action_type = str(action.get("type", action.get("action", ""))).strip().lower()
        target = str(action.get("target", action.get("value", ""))).strip().lower()

        if action_type in FORBIDDEN_ACTIONS:
            return "FORBIDDEN", f"Действие '{action_type}' категорически запрещено из соображений безопасности Windows."

        # Safety filters on shell tools
        if action_type == "run_shell":
            dangerous_tokens = ["del", "rm", "format", "reg", "remove-item", "rmdir", "attrib", "shutdown"]
            if any(token in target for token in dangerous_tokens):
                return "FORBIDDEN", "Shell-команда содержит потенциально опасные токены."
            return "CONFIRM_REQUIRED", "Выполнение произвольных shell-команд требует подтверждения."

        if action_type == "delete_file":
            # Check for system files
            if "windows" in target or "system32" in target or "appdata" in target:
                return "FORBIDDEN", "Удаление системных файлов и папок запрещено."
            return "CONFIRM_REQUIRED", f"Требуется подтверждение удаления файла: '{target}'."

        if action_type == "open_app":
            # Common safe apps
            safe_apps = {"telegram", "discord", "code", "browser", "explorer", "taskmgr"}
            if any(app in target for app in safe_apps):
                return "SAFE", "Приложение находится в списке безопасных программ."
            return "SAFE", "Открытие приложений является безопасным действием."  # Requirements say opening apps is SAFE

        if action_type in SAFE_NO_CONFIRM:
            return "SAFE", "Безопасное стандартное действие."

        if action_type in CONFIRM_REQUIRED:
            return "CONFIRM_REQUIRED", f"Действие '{action_type}' требует явного согласия сэра."

        # Default fallback for unknown actions
        return "SAFE", "Неизвестное действие классифицировано как безопасное."

    @staticmethod
    def is_confirmation_intent(text: str) -> bool:
        """Checks if the text contains a confirmation affirmation word."""
        if not text:
            return False
        normalized = text.lower().strip().strip("!.,? ")
        return normalized in AFFIRMATIVE_KEYWORDS or any(kw in normalized for kw in ["подтверждаю", "выполняй"])

    @staticmethod
    def is_cancellation_intent(text: str) -> bool:
        """Checks if the text contains a cancellation keyword."""
        if not text:
            return False
        normalized = text.lower().strip().strip("!.,? ")
        return normalized in CANCEL_KEYWORDS
