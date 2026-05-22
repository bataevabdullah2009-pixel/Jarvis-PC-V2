from __future__ import annotations

import os
import sys
import subprocess
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_main_py_compile() -> None:
    """Asserts that python -m py_compile app/main.py finishes with exit code 0."""
    # Run from backend folder
    backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    res = subprocess.run(
        [sys.executable, "-m", "py_compile", "app/main.py"],
        cwd=backend_root,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"app/main.py syntax check failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"


def test_health() -> None:
    """Asserts GET /health returns status 'ok'."""
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["status"] == "ok"


def test_startup_debug() -> None:
    """Asserts GET /debug/startup returns backend_started and requirements analysis."""
    response = client.get("/debug/startup")
    assert response.status_code == 200
    body = response.json()
    assert body["backend_started"] is True
    assert "python_version" in body
    assert "cwd" in body
    assert "main_file" in body
    assert "requirements_ok" in body
    assert "missing_dependencies" in body
    assert "audio_dependencies" in body
    assert "env" in body
    assert body["env"]["openrouter_key_present"] is not None


def test_voice_say_no_crash(monkeypatch) -> None:
    """Simulates /voice/say posting text and asserts the dictionary matches the new schema."""
    from app.voice.speech_orchestrator import SpeechOrchestrator

    def fake_say(self, text: str, *, dry_run: bool = False) -> dict:
        return {
            "ok": False,
            "provider": "text_only",
            "spoken": False,
            "played": False,
            "fallback_used": True,
            "error": "Simulated primary failure",
            "fix": "Check settings"
        }

    monkeypatch.setattr(SpeechOrchestrator, "say", fake_say)

    response = client.post("/voice/say", json={"text": "Привет от Джарвиса"})
    assert response.status_code == 200
    body = response.json()
    assert "provider" in body
    assert "fallback_used" in body
    assert "fix" in body
    assert "data" in body
    assert "error" in body
    assert body["ok"] is False
    assert body["error"]["code"] == "TTS_ERROR"
    assert body["error"]["details"]["fix"] == "Check settings"


def test_assistant_ask_no_crash(monkeypatch) -> None:
    """Posts to /assistant/ask to verify robust local fallback under simulation."""
    from app.providers.openrouter import PlannerResult
    from app.router.ai_planner import AIPlanner

    def fake_plan_fail(self, text: str) -> PlannerResult:
        return PlannerResult(
            status="unavailable",
            answer_text="",
            actions=[],
            provider="openrouter",
            error="Connection timed out",
            error_type="timeout",
            fix="Check internet"
        )

    monkeypatch.setattr(AIPlanner, "plan", fake_plan_fail)

    response = client.post(
        "/assistant/ask",
        json={
            "text": "Джарвис, какая погода?",
            "speak": False,
            "source": "hud",
            "context": {"dry_run": True}
        }
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True  # Controlled fallback should return ok: True
    data = body["data"]
    assert data["mode"] == "ai_error"
    assert "недоступен" in data["text"]


def test_scripts_exist() -> None:
    """Checks for the existence of RUN_DEV_FRESH.bat and UPDATE_AND_LAUNCH_APP.bat in the project root."""
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    assert os.path.exists(os.path.join(root, "RUN_DEV_FRESH.bat")), "RUN_DEV_FRESH.bat is missing at root!"
    assert os.path.exists(os.path.join(root, "UPDATE_AND_LAUNCH_APP.bat")), "UPDATE_AND_LAUNCH_APP.bat is missing at root!"
