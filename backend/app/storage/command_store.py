from __future__ import annotations

import json
from datetime import datetime
from uuid import uuid4
from typing import Any

from app.core.config import CONFIG_DIR


COMMANDS_PATH = CONFIG_DIR / "local_commands_ru.json"


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _read_store() -> dict[str, Any]:
    if not COMMANDS_PATH.exists():
        return {"commands": []}
    with COMMANDS_PATH.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        return {"commands": []}
    commands = data.get("commands")
    if not isinstance(commands, list):
        data["commands"] = []
    return data


def _write_store(data: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with COMMANDS_PATH.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")


def normalize_command(command: dict[str, Any]) -> dict[str, Any]:
    command_id = str(command.get("id") or str(uuid4()))
    title = str(command.get("title") or command.get("name") or command_id)
    phrases = command.get("phrases") or command.get("triggers") or []
    if isinstance(phrases, str):
        phrases = [part.strip() for part in phrases.split(",") if part.strip()]
    phrases = [str(phrase).strip() for phrase in phrases if str(phrase).strip()]
    raw_action = command.get("action")
    action_type = str(command.get("action_type") or (raw_action.get("type") if isinstance(raw_action, dict) else raw_action) or "speak").strip()
    action_value = str(
        command.get("action_value")
        or command.get("value")
        or (raw_action.get("target") if isinstance(raw_action, dict) else "")
        or (raw_action.get("value") if isinstance(raw_action, dict) else "")
        or ""
    ).strip()
    created_at = str(command.get("created_at") or _now_iso())
    updated_at = str(command.get("updated_at") or created_at)
    confirm_required = bool(command.get("confirm_required", command.get("confirmation_required", action_type == "run_shell")))
    if action_type == "run_shell":
        confirm_required = True
    enabled = bool(command.get("enabled", True))
    return {
        **command,
        "id": command_id,
        "title": title,
        "name": title,
        "phrases": phrases,
        "triggers": phrases,
        "action_type": action_type,
        "action": action_type,
        "action_value": action_value,
        "value": action_value,
        "enabled": enabled,
        "confirm_required": confirm_required,
        "confirmation_required": confirm_required,
        "created_at": created_at,
        "updated_at": updated_at,
    }


def get_commands() -> dict[str, Any]:
    data = _read_store()
    data["commands"] = [normalize_command(command) for command in data.get("commands", []) if isinstance(command, dict)]
    return data


def create_command(payload: dict[str, Any]) -> dict[str, Any]:
    data = get_commands()
    command = normalize_command({**payload, "id": payload.get("id") or str(uuid4()), "created_at": _now_iso(), "updated_at": _now_iso()})
    existing_ids = {item["id"] for item in data["commands"]}
    if command["id"] in existing_ids:
        command["id"] = str(uuid4())
    data["commands"].append(command)
    _write_store(data)
    return command


def update_command(command_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
    data = get_commands()
    for index, command in enumerate(data["commands"]):
        if command["id"] != command_id:
            continue
        updated = normalize_command({**command, **patch, "id": command_id, "updated_at": _now_iso()})
        data["commands"][index] = updated
        _write_store(data)
        return updated
    return None


def delete_command(command_id: str) -> bool:
    data = get_commands()
    before = len(data["commands"])
    data["commands"] = [command for command in data["commands"] if command["id"] != command_id]
    if len(data["commands"]) == before:
        return False
    _write_store(data)
    return True
