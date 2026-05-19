from __future__ import annotations

import json
from typing import Any

from app.core.config import CONFIG_DIR


def get_commands() -> dict[str, Any]:
    path = CONFIG_DIR / "local_commands_ru.json"
    if not path.exists():
        return {"commands": []}
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)

