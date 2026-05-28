from __future__ import annotations

import os
import sys
import platform
import json
from pathlib import Path
from typing import Any

from app.core.config import PROJECT_ROOT, Settings


def build_info(settings: Settings) -> dict[str, Any]:
    # Determine if frozen (packaged)
    frozen = getattr(sys, "frozen", False)
    
    # Determine project_root and app_current
    proj_root = Path(os.getenv("JARVIS_PROJECT_ROOT", PROJECT_ROOT)).resolve()
    
    env_file_var = os.getenv("JARVIS_ENV_FILE")
    if env_file_var:
        app_curr = Path(env_file_var).resolve().parent
    elif frozen:
        app_curr = Path(sys.executable).resolve().parents[2]
    else:
        app_curr = proj_root / "app_current"

    # Try to load BUILD_INFO.json from multiple possible locations
    build_info_data = {}
    build_info_found = False
    candidates = [
        app_curr / "BUILD_INFO.json",
        proj_root / "app_current" / "BUILD_INFO.json",
        proj_root / "BUILD_INFO.json",
        Path(sys.executable).resolve().parents[2] / "BUILD_INFO.json" if frozen else None,
        Path(__file__).resolve().parents[3] / "app_current" / "BUILD_INFO.json",
    ]
    for candidate in candidates:
        if candidate and candidate.exists():
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    build_info_data = json.load(f)
                build_info_found = True
                break
            except Exception:
                pass
                
    # Get dynamic git info if running from source as fallback
    git_sha = build_info_data.get("git_sha")
    git_branch = build_info_data.get("git_branch")
    built_at = build_info_data.get("built_at")
    
    if not frozen and (not git_sha or not git_branch):
        import subprocess
        try:
            if not git_sha:
                git_sha = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL, cwd=str(PROJECT_ROOT)).decode("utf-8").strip()
            if not git_branch:
                git_branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], stderr=subprocess.DEVNULL, cwd=str(PROJECT_ROOT)).decode("utf-8").strip()
        except Exception:
            pass

    # Fallbacks
    git_sha = git_sha or "unknown"
    git_branch = git_branch or "unknown"
    built_at = built_at or "dynamic"

    frontend_mode = os.getenv("JARVIS_FRONTEND_MODE")
    if not frontend_mode:
        frontend_mode = "dev" if not frozen else "packaged"

    return {
        "app": settings.app_name,
        "version": settings.version,
        "phase": settings.phase,
        "license_enabled": False,
        "python": sys.version.split()[0],
        "platform": platform.system(),
        "platform_release": platform.release(),
        "git_sha": git_sha,
        "git_branch": git_branch,
        "built_at": built_at,
        "running_from_source": not frozen,
        "packaged": frozen,
        "backend_path": str(Path(__file__).resolve().parents[2]),
        "backend_url": f"http://127.0.0.1:{os.getenv('JARVIS_BACKEND_PORT', '18000')}",
        "packaged_source_mode": "packaged" if frozen else "source",
        "backend_executable_path": sys.executable if frozen else sys.argv[0],
        "frontend_mode": frontend_mode,
        "build_info_found": build_info_found
    }

