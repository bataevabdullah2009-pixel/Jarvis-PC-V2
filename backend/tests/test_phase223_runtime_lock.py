from __future__ import annotations

import httpx
import requests
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app
from app.providers.openrouter import OpenRouterPlanner, PlannerResult
from app.router.ai_planner import AIPlanner
from app.voice.speech_orchestrator import SpeechOrchestrator


client = TestClient(app)


def _settings_with_openrouter() -> Settings:
    settings = Settings()
    settings.openrouter_api_key = "fake_openrouter_key"
    settings.openrouter_model = "openai/gpt-4o-mini"
    settings.openrouter_connect_timeout = 10
    settings.openrouter_read_timeout = 20
    settings.openrouter_total_timeout = 30
    settings.openrouter_max_retries = 0
    return settings


def test_openrouter_network_timeout_structured(monkeypatch) -> None:
    def fake_httpx_post(self, url, **kwargs):
        raise httpx.ConnectTimeout("_ssl.c:993: The handshake operation timed out")

    def fake_requests_post(*args, **kwargs):
        raise requests.exceptions.ConnectTimeout("_ssl.c:993: The handshake operation timed out")

    monkeypatch.setattr(httpx.Client, "post", fake_httpx_post)
    monkeypatch.setattr(requests, "post", fake_requests_post)

    result = OpenRouterPlanner(_settings_with_openrouter()).plan("ping")

    assert result.status == "unavailable"
    assert result.called is True
    assert result.error_type == "tls_handshake_timeout"
    assert "_ssl.c:993" not in result.answer_text
    assert "OpenRouter сейчас не отвечает по сети" in result.answer_text


def test_openrouter_key_present_but_timeout_not_key_missing(monkeypatch) -> None:
    def fake_httpx_post(self, url, **kwargs):
        raise httpx.ReadTimeout("read timed out")

    def fake_requests_post(*args, **kwargs):
        raise requests.exceptions.ReadTimeout("read timed out")

    monkeypatch.setattr(httpx.Client, "post", fake_httpx_post)
    monkeypatch.setattr(requests, "post", fake_requests_post)

    result = OpenRouterPlanner(_settings_with_openrouter()).plan("ping")

    assert result.called is True
    assert result.error_type == "network_timeout"
    assert result.error_type != "openrouter_key_missing"
    assert "API key is missing" not in (result.error_message or "")


def test_assistant_ask_mock_openrouter_success(monkeypatch) -> None:
    settings = _settings_with_openrouter()
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings)

    def fake_plan(self, text: str, context=None) -> PlannerResult:
        return PlannerResult(
            status="answered",
            answer_text="Mock OpenRouter success",
            actions=[],
            provider="openrouter",
            model="openai/gpt-4o-mini",
            status_code=200,
            openrouter_called=True,
        )

    monkeypatch.setattr(AIPlanner, "plan", fake_plan)

    response = client.post(
        "/assistant/ask",
        json={"text": "Джарвис, как дела?", "speak": False, "source": "hud", "context": {"dry_run": True}},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["mode"] == "ai"
    assert data["provider"] == "openrouter"
    assert data["openrouter_called"] is True
    assert data["response_text"] == "Mock OpenRouter success"


def test_pytest_does_not_require_real_openrouter_key(monkeypatch) -> None:
    settings = Settings()
    settings.openrouter_api_key = None

    def fail_if_called(self, url, **kwargs):
        raise AssertionError("pytest must not call the real OpenRouter network")

    monkeypatch.setattr(httpx.Client, "post", fail_if_called)

    result = OpenRouterPlanner(settings).test("ping")

    assert result["ok"] is False
    assert result["called"] is False
    assert result["error_type"] == "openrouter_key_missing"


def test_network_status_endpoint_shape(monkeypatch) -> None:
    from app.main import debug_network_status

    class FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeResponse:
        status_code = 200
        text = "{}"

    def fake_getaddrinfo(*args, **kwargs):
        return [("ok",)]

    def fake_create_connection(*args, **kwargs):
        return FakeSocket()

    def fake_httpx_get(self, url, **kwargs):
        return FakeResponse()

    monkeypatch.setattr("socket.getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr("socket.create_connection", fake_create_connection)
    monkeypatch.setattr(httpx.Client, "get", fake_httpx_get)

    body = debug_network_status()
    assert "ok" in body
    assert "openrouter" in body
    openrouter = body["openrouter"]
    assert openrouter["dns_ok"] is True
    assert openrouter["tcp_ok"] is True
    assert openrouter["httpx_ok"] is True
    assert openrouter["requests_ok"] is False
    assert openrouter["status_code"] == 200
    assert "latency_ms" in openrouter
    assert "error_type" in openrouter
    assert "fix" in openrouter


def test_fish_audio_mock_success() -> None:
    settings = Settings()
    settings.fish_audio_api_key = "fish_key"
    settings.fish_audio_voice_id = "fish_voice"
    settings.tts_primary = "fish_audio"
    settings.tts_require_fish_audio = True
    settings.tts_fallback_enabled = False

    orchestrator = SpeechOrchestrator(settings)
    result = orchestrator.say("Jarvis test", dry_run=True)

    assert result["ok"] is True
    assert result["provider"] == "fish_audio"
    assert result["status"] == "dry_run"


def test_jarvis_voice_lock_blocks_edge_and_pyttsx3(monkeypatch) -> None:
    settings = Settings()
    settings.voice_profile = "Jarvis style"
    settings.tts_primary = "fish_audio"
    settings.tts_require_fish_audio = True
    settings.tts_fallback_enabled = False
    settings.fish_audio_api_key = "fish_key"
    settings.fish_audio_voice_id = "fish_voice"

    orchestrator = SpeechOrchestrator(settings)
    monkeypatch.setattr(orchestrator.fish, "available", lambda: True)
    monkeypatch.setattr(orchestrator.fish, "synthesize", lambda text: {"ok": False, "error": "fish down", "status": "failed"})
    edge_called = {"value": False}
    offline_called = {"value": False}

    def edge_synthesize(text):
        edge_called["value"] = True
        return {"ok": True, "status": "completed"}

    def offline_speak(text, dry_run=False):
        offline_called["value"] = True
        return {"ok": True, "status": "completed"}

    monkeypatch.setattr(orchestrator.edge, "available", lambda: True)
    monkeypatch.setattr(orchestrator.edge, "synthesize", edge_synthesize)
    monkeypatch.setattr(orchestrator.offline, "available", lambda: True)
    monkeypatch.setattr(orchestrator.offline, "speak", offline_speak)

    result = orchestrator.say("Jarvis test")

    assert result["provider"] == "text_only"
    assert result["error_type"] == "fish_audio_unavailable"
    assert result["fallback_used"] is False
    assert edge_called["value"] is False
    assert offline_called["value"] is False
