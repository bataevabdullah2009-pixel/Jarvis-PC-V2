from __future__ import annotations

import platform
import sys
from typing import Any

from app.core.config import Settings


def build_info(settings: Settings) -> dict[str, Any]:
    return {
        "app": settings.app_name,
        "version": settings.version,
        "phase": settings.phase,
        "license_enabled": False,
        "python": sys.version.split()[0],
        "platform": platform.system(),
        "platform_release": platform.release(),
    }

