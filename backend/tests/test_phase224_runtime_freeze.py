from __future__ import annotations

import importlib
import os
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


PROJECT_ROOT = Path(__file__).resolve().parents[2]
client = TestClient(app)


def _non_empty_lines(path: Path) -> list[str]:
    return [line for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()]


def test_start_jarvis_bat_multiline() -> None:
    path = PROJECT_ROOT / "START_JARVIS.bat"
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines == [
        "@echo off",
        'cd /d "%~dp0"',
        'powershell -NoProfile -ExecutionPolicy Bypass -File "tools\\start_jarvis.ps1"',
        "pause",
    ]
    assert path.read_bytes().count(b"\r\n") >= 4


def test_start_jarvis_ps1_multiline() -> None:
    path = PROJECT_ROOT / "tools" / "start_jarvis.ps1"
    assert len(_non_empty_lines(path)) >= 80
    assert path.read_bytes().count(b"\r\n") >= 80
    assert "18000" in path.read_text(encoding="utf-8")


def test_check_source_format_multiline() -> None:
    path = PROJECT_ROOT / "tools" / "check_source_format.py"
    assert len(_non_empty_lines(path)) >= 120
    first_line = path.read_bytes().splitlines()[0]
    assert len(first_line) < 2000


def test_readme_multiline() -> None:
    path = PROJECT_ROOT / "README.md"
    assert len(_non_empty_lines(path)) >= 30
    assert "18000" in path.read_text(encoding="utf-8")


def test_default_backend_port_is_18000(monkeypatch) -> None:
    monkeypatch.delenv("JARVIS_BACKEND_PORT", raising=False)
    monkeypatch.delenv("JARVIS_BACKEND_HOST", raising=False)
    run_backend = importlib.import_module("run_backend")
    captured = {}

    def fake_run(*args, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(run_backend.uvicorn, "run", fake_run)
    run_backend.main()
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 18000


def test_run_backend_reads_env_port(monkeypatch) -> None:
    monkeypatch.setenv("JARVIS_BACKEND_PORT", "18042")
    monkeypatch.setenv("JARVIS_BACKEND_HOST", "127.0.0.2")
    run_backend = importlib.import_module("run_backend")
    captured = {}

    def fake_run(*args, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(run_backend.uvicorn, "run", fake_run)
    run_backend.main()
    assert captured["host"] == "127.0.0.2"
    assert captured["port"] == 18042


def test_frontend_api_base_default_18000() -> None:
    path = PROJECT_ROOT / "frontend" / "src" / "api" / "client.ts"
    text = path.read_text(encoding="utf-8")
    assert 'import.meta.env.VITE_JARVIS_API_BASE || "http://127.0.0.1:18000"' in text


def test_runtime_process_info_contains_port(monkeypatch) -> None:
    monkeypatch.setenv("JARVIS_BACKEND_HOST", "127.0.0.1")
    monkeypatch.setenv("JARVIS_BACKEND_PORT", "18000")
    monkeypatch.setenv("JARVIS_LAUNCHER", "START_JARVIS")
    response = client.get("/runtime/process-info")
    assert response.status_code == 200
    body = response.json()
    assert body["host"] == "127.0.0.1"
    assert body["port"] == 18000
    assert body["launcher"] == "START_JARVIS"
    assert isinstance(body["pid"], int)


def test_launcher_ignores_port_8000_conflict() -> None:
    text = (PROJECT_ROOT / "tools" / "start_jarvis.ps1").read_text(encoding="utf-8")
    assert "$backendPort = 18000" in text
    assert "JARVIS_BACKEND_PORT" in text
    assert "$backendPort = 8000" not in text
    assert "127.0.0.1:8000" not in text


def test_no_hardcoded_8000_in_frontend_client() -> None:
    path = PROJECT_ROOT / "frontend" / "src" / "api" / "client.ts"
    text = path.read_text(encoding="utf-8")
    assert "127.0.0.1:8000" not in text
