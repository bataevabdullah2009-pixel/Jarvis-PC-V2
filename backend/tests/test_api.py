from app.main import app
from app.providers.openrouter import PlannerResult
from app.router.ai_planner import AIPlanner
from fastapi.testclient import TestClient


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["status"] == "ok"


def test_build_info_has_license_disabled() -> None:
    response = client.get("/runtime/build-info")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["app"] == "JARVIS PC V2"
    assert data["license_enabled"] is False


def test_assistant_command_contract_welcome_home() -> None:
    response = client.post(
        "/assistant/command",
        json={
            "text": "Джарвис, я вернулся",
            "source": "test",
            "context": {"dry_run": True},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["route"] == "scenario"
    assert body["data"]["route_detail"] == "scenario:welcome_home"
    assert body["data"]["actions"][0]["type"] == "play_music_search"


def test_scenario_music_contract() -> None:
    response = client.post(
        "/scenarios/music",
        json={"context": {"dry_run": True, "query": "Back in Black"}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["actions"][0]["playback_attempted"] is True


def test_commands_contract() -> None:
    response = client.get("/commands")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert "commands" in body["data"]


def test_diagnostics_contract() -> None:
    response = client.get("/diagnostics/full-test")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["checks"]["backend"] == "ok"


def test_system_monitor_contract() -> None:
    response = client.get("/diagnostics/system-monitor")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert "cpu_count" in body["data"]
    assert "disk_free_gb" in body["data"]


def test_assistant_command_contract_ai(monkeypatch) -> None:
    def fake_plan(self: AIPlanner, text: str) -> PlannerResult:
        return PlannerResult(
            status="answered",
            answer_text="Идея: локальная панель для быстрых AI-команд.",
            actions=[],
            provider="test",
        )

    monkeypatch.setattr(AIPlanner, "plan", fake_plan)
    response = client.post(
        "/assistant/command",
        json={
            "text": "Джарвис, придумай идею для сайта",
            "source": "test",
            "context": {"dry_run": True},
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["route"] == "ai_fallback"
    assert "Идея" in data["response_text"]


def test_assistant_ask_local_command() -> None:
    response = client.post(
        "/assistant/ask",
        json={
            "text": "Джарвис, я вернулся",
            "speak": False,
            "source": "hud",
            "context": {"dry_run": True},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["mode"] == "local"
    assert data["route"] == "scenario"
    assert data["route_detail"] == "scenario:welcome_home"
    assert data["executed"] is True
    assert len(data["actions"]) > 0


def test_assistant_ask_ai_without_key(monkeypatch) -> None:
    # Temporarily clean API keys to force fallback by monkeypatching get_settings
    from app.core.config import Settings
    settings_inst = Settings.load()
    settings_inst.openrouter_api_key = None
    settings_inst.groq_api_key = None

    monkeypatch.setattr("app.main.get_settings", lambda: settings_inst)
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings_inst)

    response = client.post(
        "/assistant/ask",
        json={
            "text": "Джарвис, как дела?",
            "speak": False,
            "source": "hud",
            "context": {"dry_run": True},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["mode"] == "ai_limited"
    assert data["provider"] == "text_only"
    assert "облачный AI сейчас недоступен" in data["response_text"]


def test_setup_readiness() -> None:
    response = client.get("/setup/readiness")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["backend_ok"] is True
    assert data["assistant_ask_ok"] is True
    assert "local_commands_ok" in data
    assert "openrouter_configured" in data
    assert "openrouter_model" in data
    assert "fish_audio_configured" in data
    assert "tts_primary" in data
    assert "tts_fallback_enabled" in data
    assert "tts_fallback_ready" in data
    assert "microphone_dependency_ok" in data
    assert "voice_pipeline_ok" in data
    assert data["hud_events_ok"] is True
    assert "warnings" in data


def test_commands_test_diagnostic() -> None:
    response = client.get("/commands/test", params={"text": "я вернулся"})
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["normalized"] == "я вернулся"
    assert data["diagnostic"] is True
    assert data["matched"]["action"] == "scenario"
    assert data["matched"]["value"] == "welcome_home"


def test_assistant_ask_no_key_no_crash(monkeypatch) -> None:
    from app.core.config import Settings
    settings_inst = Settings.load()
    settings_inst.openrouter_api_key = None
    settings_inst.groq_api_key = None
    monkeypatch.setattr("app.main.get_settings", lambda: settings_inst)
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings_inst)

    response = client.post(
        "/assistant/ask",
        json={
            "text": "Как дела?",
            "speak": True,
            "source": "hud",
            "context": {"dry_run": True},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["mode"] == "ai_limited"
    assert "облачный AI сейчас недоступен" in body["data"]["response_text"]


def test_assistant_ask_mock_ai_success(monkeypatch) -> None:
    from app.core.config import Settings
    settings_inst = Settings.load()
    settings_inst.openrouter_api_key = "fake_key"
    monkeypatch.setattr("app.main.get_settings", lambda: settings_inst)
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings_inst)

    def fake_plan(self, text: str) -> PlannerResult:
        return PlannerResult(
            status="answered",
            answer_text="Привет, сэр! Все системы функционируют отлично.",
            actions=[],
            provider="openrouter",
            model="openai/gpt-4o-mini",
            openrouter_called=True,
            status_code=200,
            latency_ms=150
        )
    monkeypatch.setattr(AIPlanner, "plan", fake_plan)

    response = client.post(
        "/assistant/ask",
        json={
            "text": "Джарвис, как дела?",
            "speak": False,
            "source": "hud",
            "context": {"dry_run": True},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["mode"] == "ai"
    assert body["data"]["provider"] == "openrouter"
    assert "Привет, сэр" in body["data"]["response_text"]


def test_local_command_without_openrouter(monkeypatch) -> None:
    from app.core.config import Settings
    settings_inst = Settings.load()
    settings_inst.openrouter_api_key = None
    settings_inst.groq_api_key = None
    monkeypatch.setattr("app.main.get_settings", lambda: settings_inst)
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings_inst)

    response = client.post(
        "/assistant/ask",
        json={
            "text": "Джарвис, я вернулся",
            "speak": False,
            "source": "hud",
            "context": {"dry_run": True},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["mode"] == "local"
    assert body["data"]["route_detail"] == "scenario:welcome_home"


def test_tts_fallback(monkeypatch) -> None:
    from app.voice.speech_orchestrator import SpeechOrchestrator
    
    def fake_say(self, text: str, *, dry_run: bool = False) -> dict:
        return {
            "requested": True,
            "ok": True,
            "provider": "pyttsx3",
            "mode": "pyttsx3",
            "spoken": True,
            "played": True,
            "audio_available": False,
            "fallback_used": True,
            "error": None,
            "text": text,
            "status": "completed",
            "latency_ms": 100,
            "audio_bytes": 0,
            "format": "wav"
        }
    monkeypatch.setattr(SpeechOrchestrator, "say", fake_say)

    response = client.post(
        "/voice/say",
        json={"text": "Привет от Джарвиса"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["fallback_used"] is True
    assert body["data"]["provider"] == "pyttsx3"


def test_existing_endpoints_still_work() -> None:
    resp1 = client.get("/health")
    assert resp1.status_code == 200
    assert resp1.json()["ok"] is True

    resp2 = client.get("/health/full")
    assert resp2.status_code == 200
    assert resp2.json()["ok"] is True

    resp3 = client.get("/voice/tts-status")
    assert resp3.status_code == 200
    assert resp3.json()["ok"] is True

    resp4 = client.post(
        "/assistant/command",
        json={
            "text": "Джарвис, я вернулся",
            "source": "test",
            "context": {"dry_run": True},
        },
    )
    assert resp4.status_code == 200
    assert resp4.json()["ok"] is True


def test_env_status_openrouter_fields() -> None:
    response = client.get("/debug/env-status")
    assert response.status_code == 200
    body = response.json()
    assert "env_loaded" in body
    assert "paths_checked" in body
    assert "paths_loaded" in body
    assert "openrouter" in body
    assert "key_present" in body["openrouter"]
    assert "key_prefix" in body["openrouter"]
    assert "model" in body["openrouter"]
    assert "model_present" in body["openrouter"]
    assert "fixes" in body


def test_openrouter_no_key(monkeypatch) -> None:
    from app.core.config import Settings
    from app.providers.openrouter import OpenRouterPlanner
    settings_inst = Settings.load()
    settings_inst.openrouter_api_key = None
    monkeypatch.setattr("app.providers.openrouter.Settings", lambda: settings_inst)

    planner = OpenRouterPlanner(settings_inst)
    res = planner.test("Привет")
    assert res["ok"] is False
    assert res["called"] is False
    assert res["error_type"] == "openrouter_key_missing"
    assert "API key is missing" in res["error_message"]
    assert "fix" in res


def test_openrouter_mock_success(monkeypatch) -> None:
    import httpx
    from app.core.config import Settings
    from app.providers.openrouter import OpenRouterPlanner

    class MockResponse:
        status_code = 200
        text = '{"choices": [{"message": {"content": "ГРОЗНЫЙ-777"}}]}'
        def json(self):
            return {"choices": [{"message": {"content": "ГРОЗНЫЙ-777"}}]}

    def mock_post(self, url, **kwargs):
        return MockResponse()

    monkeypatch.setattr(httpx.Client, "post", mock_post)

    settings_inst = Settings.load()
    settings_inst.openrouter_api_key = "fake_key_123456789012"
    settings_inst.openrouter_model = "openai/gpt-4o-mini"

    planner = OpenRouterPlanner(settings_inst)
    res = planner.test("Скажи строго эту фразу: ГРОЗНЫЙ-777")
    assert res["ok"] is True
    assert res["called"] is True
    assert res["status_code"] == 200
    assert "ГРОЗНЫЙ-777" in res["response_preview"]


def test_openrouter_mock_401(monkeypatch) -> None:
    import httpx
    from app.core.config import Settings
    from app.providers.openrouter import OpenRouterPlanner

    class MockResponse:
        status_code = 401
        reason_phrase = "Unauthorized"
        text = '{"error": {"message": "Invalid API Key", "code": 401}}'
        def json(self):
            return {"error": {"message": "Invalid API Key", "code": 401}}

    def mock_post(self, url, **kwargs):
        return MockResponse()

    monkeypatch.setattr(httpx.Client, "post", mock_post)

    settings_inst = Settings.load()
    settings_inst.openrouter_api_key = "fake_key_123456789012"
    settings_inst.openrouter_model = "openai/gpt-4o-mini"

    planner = OpenRouterPlanner(settings_inst)
    res = planner.test("Привет")
    assert res["ok"] is False
    assert res["called"] is True
    assert res["status_code"] == 401
    assert res["error_type"] == "invalid_key"
    assert "invalid API key" in res["error_message"]
    assert "Неверный OpenRouter API ключ" in res["fix"]


def test_assistant_ask_calls_openrouter_when_key_present(monkeypatch) -> None:
    from app.core.config import Settings
    settings_inst = Settings.load()
    settings_inst.openrouter_api_key = "fake_key_123456789012"
    monkeypatch.setattr("app.main.get_settings", lambda: settings_inst)
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings_inst)

    def fake_plan(self, text: str) -> PlannerResult:
        return PlannerResult(
            status="answered",
            answer_text="Я Джарвис, сэр.",
            actions=[],
            provider="openrouter",
            model="openai/gpt-4o-mini",
            openrouter_called=True,
            status_code=200,
            latency_ms=100
        )
    monkeypatch.setattr(AIPlanner, "plan", fake_plan)

    response = client.post(
        "/assistant/ask",
        json={
            "text": "Кто ты?",
            "speak": False,
            "source": "hud",
            "context": {"dry_run": True},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["mode"] == "ai"
    assert data["openrouter_called"] is True
    assert "Я Джарвис" in data["response_text"]


def test_assistant_ask_local_command_does_not_call_openrouter(monkeypatch) -> None:
    from app.core.config import Settings
    settings_inst = Settings.load()
    settings_inst.openrouter_api_key = "fake_key_123456789012"
    monkeypatch.setattr("app.main.get_settings", lambda: settings_inst)
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings_inst)

    openrouter_called_flag = False
    def fake_plan(self, text: str) -> PlannerResult:
        nonlocal openrouter_called_flag
        openrouter_called_flag = True
        return PlannerResult(
            status="answered",
            answer_text="AI reply",
            actions=[],
            provider="openrouter",
            openrouter_called=True
        )
    monkeypatch.setattr(AIPlanner, "plan", fake_plan)

    response = client.post(
        "/assistant/ask",
        json={
            "text": "Джарвис, я вернулся",
            "speak": False,
            "source": "hud",
            "context": {"dry_run": True},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["mode"] == "local"
    assert data["openrouter_called"] is False
    assert openrouter_called_flag is False
