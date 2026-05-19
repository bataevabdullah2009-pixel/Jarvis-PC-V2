from __future__ import annotations

import os
import platform
import shutil
from datetime import UTC, datetime
from typing import Any


def get_system_status() -> dict[str, Any]:
    disk = shutil.disk_usage("/")
    data: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "platform": platform.system(),
        "platform_release": platform.release(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count() or 0,
        "cpu_percent": None,
        "memory_percent": None,
        "memory_used_gb": None,
        "memory_total_gb": None,
        "disk_percent": round((disk.used / disk.total) * 100, 2) if disk.total else None,
        "disk_free_gb": round(disk.free / (1024**3), 2),
        "disk_total_gb": round(disk.total / (1024**3), 2),
    }

    try:
        import psutil

        memory = psutil.virtual_memory()
        data.update(
            {
                "cpu_percent": psutil.cpu_percent(interval=0.1),
                "memory_percent": memory.percent,
                "memory_used_gb": round(memory.used / (1024**3), 2),
                "memory_total_gb": round(memory.total / (1024**3), 2),
            }
        )
    except Exception as exc:
        data["monitor_warning"] = exc.__class__.__name__

    return data
