from __future__ import annotations

import importlib.util
import sys
from typing import Any


REQUIRED_IMPORTS: dict[str, str] = {
    "python-dotenv": "dotenv",
    "httpx": "httpx",
    "requests": "requests",
    "sounddevice": "sounddevice",
    "numpy": "numpy",
    "vosk": "vosk",
    "pyttsx3": "pyttsx3",
}


def check_backend_dependencies() -> dict[str, Any]:
    installed = {
        package_name: importlib.util.find_spec(import_name) is not None
        for package_name, import_name in REQUIRED_IMPORTS.items()
    }
    missing = [package_name for package_name, ok in installed.items() if not ok]
    return {
        "ok": not missing,
        "python": sys.executable,
        "missing": missing,
        "installed": installed,
        "install_command": "python -m pip install -r requirements.txt",
    }
