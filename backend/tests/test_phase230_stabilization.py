from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.core.config import CONFIG_DIR, Settings, patch_settings
from app.main import app
from app.router.command_router import CommandRouter
from app.voice import anti_echo
from app.voice.audio_capture import diagnose_microphone_error, resolve_input_device, safe_open_input_stream
from app.voice.speech_queue import speech_queue
from app.voice.wakeword import extract_wake_command


ROOT = Path(__file__).resolve().parents[2]
client = TestClient(app)


def _restore(path: Path):
    original = path.read_text(encoding="utf-8") if path.exists() else None
    try:
        yield
    finally:
        if original is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(original, encoding="utf-8", newline="\n")


def test_listener_never_unknown_reason() -> None:
    data = client.get("/voice/listener-status").json()["data"]
    forbidden = {"unknown reason", "stopped without reason", "причина не указана"}
    assert str(data.get("last_error_type") or "").lower() not in forbidden
    assert str(data.get("last_error") or "").lower() not in forbidden


def test_listener_blocked_has_error_type_and_fix() -> None:
    from app.voice.listener import voice_listener

    voice_listener.block("microphone_open_failed", "Choose another input device.", "PortAudio failed")
    data = voice_listener.status()["data"]
    assert data["state"] == "blocked"
    assert data["last_error_type"]
    assert data["last_error"]
    assert data["fix"]


def test_microphone_open_error_maps_to_windows_audio_host_error() -> None:
    diagnosis = diagnose_microphone_error("PaErrorCode -9999 WdmSyncIoctl DeviceIoControl GLE = 0x00000490")
    assert diagnosis["error_type"] == "windows_audio_host_error"
    assert diagnosis["fixes"]


def test_device_selection_persists_name_and_id() -> None:
    settings_path = CONFIG_DIR / "settings.json"
    restore = _restore(settings_path)
    next(restore)
    try:
        updated = patch_settings(
            {
                "listener_device_id": "3",
                "listener_device_name": "ME6S Microphone",
                "listener_device_hostapi": "WASAPI",
                "listener_device_channels": 1,
                "listener_device_samplerate": 48000,
            }
        )
        assert updated.listener_device_id == "3"
        assert updated.listener_device_name == "ME6S Microphone"
        assert updated.listener_device_hostapi == "WASAPI"
        assert updated.listener_device_channels == 1
        assert updated.listener_device_samplerate == 48000
    finally:
        try:
            next(restore)
        except StopIteration:
            pass


class _FakeSD:
    default = type("Default", (), {"device": [2, None]})()

    def __init__(self) -> None:
        self.open_calls: list[dict[str, Any]] = []
        self.fail_until = 0

    def query_devices(self) -> list[dict[str, Any]]:
        return [
            {"name": "Old Mic", "max_input_channels": 1, "default_samplerate": 44100.0, "hostapi": 0},
            {"name": "Other Mic", "max_input_channels": 1, "default_samplerate": 44100.0, "hostapi": 0},
            {"name": "ME6S Microphone", "max_input_channels": 2, "default_samplerate": 48000.0, "hostapi": 0},
        ]

    def query_hostapis(self, index: int) -> dict[str, Any]:
        return {"name": "WASAPI" if index == 0 else "MME"}

    def InputStream(self, **kwargs: Any) -> Any:
        self.open_calls.append(kwargs)
        if len(self.open_calls) <= self.fail_until:
            raise RuntimeError("Invalid sample rate")

        class Stream:
            def start(self) -> None:
                return None

            def stop(self) -> None:
                return None

            def close(self) -> None:
                return None

            def read(self, frames: int):
                return ([[0.01] for _ in range(frames)], False)

        return Stream()


def test_device_rebind_by_name_when_id_changes(monkeypatch) -> None:
    fake = _FakeSD()
    monkeypatch.setattr("app.voice.audio_capture._require_sounddevice", lambda: fake)
    settings = Settings()
    settings.listener_device_id = "99"
    settings.listener_device_name = "ME6S Microphone"
    resolved = resolve_input_device(settings)
    assert resolved["ok"] is True
    assert resolved["device_id"] == 2
    assert resolved["device_name"] == "ME6S Microphone"


def test_safe_open_input_stream_attempts_multiple_samplerates(monkeypatch) -> None:
    fake = _FakeSD()
    fake.fail_until = 3
    monkeypatch.setattr("app.voice.audio_capture._require_sounddevice", lambda: fake)
    opened = safe_open_input_stream(device_id="2")
    try:
        rates = [call["samplerate"] for call in fake.open_calls]
        assert rates[:4] == [16000, 48000, 44100, 48000]
        assert len(opened.attempts) >= 4
        assert opened.attempts[-1]["ok"] is True
    finally:
        opened.close()


def test_debug_open_microphone_endpoint_shape(monkeypatch) -> None:
    def fake_debug(**kwargs: Any) -> dict[str, Any]:
        return {
            "selected_device": {"id": "3"},
            "opened_device": {"id": "3"},
            "attempts": [{"attempt": 1, "ok": True}],
            "rms": 0.02,
            "peak": 0.04,
            "heard_signal": True,
            "final_error_type": None,
            "final_error": None,
            "fixes": [],
        }

    monkeypatch.setattr("app.main.debug_open_microphone", fake_debug)
    data = client.post("/voice/debug-open-microphone", json={"device_id": "3", "duration_seconds": 1}).json()
    assert data["ok"] is True
    assert {"selected_device", "opened_device", "attempts", "rms", "peak", "heard_signal", "final_error_type", "final_error", "fixes"}.issubset(data["data"])


def test_listener_enabled_not_stopped_without_reason() -> None:
    patch_settings({"listener_enabled": True, "listener_autostart": True})
    data = client.get("/voice/listener-status").json()["data"]
    if data["running"] is False:
        assert data["state"] in {"blocked", "error"}
        assert data["last_error_type"]
        assert data["last_error"] or data["failed_check"]
        assert data["fix"]


def test_wakeword_ignores_without_name() -> None:
    assert extract_wake_command("как дела", ["джарвис", "чарли", "jarvis"])["triggered"] is False


def test_wakeword_accepts_jarvis_command() -> None:
    result = extract_wake_command("Джарвис, как дела", ["джарвис", "чарли", "jarvis"])
    assert result == {"triggered": True, "wake_word": "джарвис", "command_text": "как дела", "reason": "wake_word_found"}


def test_anti_echo_blocks_self_audio() -> None:
    anti_echo._speaking = False
    anti_echo._cooldown_until = 0.0
    anti_echo._last_tts_text = "Я открыл браузер, сэр."
    anti_echo._consecutive_echo_count = 0
    anti_echo._self_echo_loop_triggered = False
    result = anti_echo.should_ignore_transcript("я открыл браузер сэр")
    assert result["ignore"] is True


def test_commands_crud_create() -> None:
    path = CONFIG_DIR / "local_commands_ru.json"
    restore = _restore(path)
    next(restore)
    try:
        created = client.post("/commands", json={"title": "Phase create", "phrases": ["phase create"], "action_type": "speak", "action_value": "ok"}).json()["data"]
        assert created["id"]
        assert created["title"] == "Phase create"
    finally:
        try:
            next(restore)
        except StopIteration:
            pass


def test_commands_crud_update() -> None:
    path = CONFIG_DIR / "local_commands_ru.json"
    restore = _restore(path)
    next(restore)
    try:
        created = client.post("/commands", json={"title": "Phase update", "phrases": ["phase update"], "action_type": "speak", "action_value": "ok"}).json()["data"]
        updated = client.patch(f"/commands/{created['id']}", json={"action_value": "updated"}).json()["data"]
        assert updated["action_value"] == "updated"
    finally:
        try:
            next(restore)
        except StopIteration:
            pass


def test_commands_crud_delete() -> None:
    path = CONFIG_DIR / "local_commands_ru.json"
    restore = _restore(path)
    next(restore)
    try:
        created = client.post("/commands", json={"title": "Phase delete", "phrases": ["phase delete"], "action_type": "speak", "action_value": "ok"}).json()["data"]
        deleted = client.delete(f"/commands/{created['id']}").json()["data"]
        assert deleted["deleted"] is True
    finally:
        try:
            next(restore)
        except StopIteration:
            pass


def test_command_router_uses_custom_command() -> None:
    path = CONFIG_DIR / "local_commands_ru.json"
    restore = _restore(path)
    next(restore)
    try:
        client.post("/commands", json={"title": "Router custom", "phrases": ["router custom"], "action_type": "speak", "action_value": "router says ok"})
        result = CommandRouter(Settings()).handle("router custom", source="test", context={"speak": False})
        assert result["route"] == "local_command"
        assert "router says ok" in result["response_text"]
    finally:
        try:
            next(restore)
        except StopIteration:
            pass


def test_tts_job_reaches_final_status() -> None:
    class FakeTTS:
        def speak(self, text: str, *, dry_run: bool = False, blocking: bool = False) -> dict[str, Any]:
            return {"ok": True, "provider": "text_only", "status": "text_only", "played": False, "spoken": False}

    speech_queue.submit("phase230_tts", "test", "hello", FakeTTS())
    speech_queue._queue.join()
    assert speech_queue.status()["last_job_status"] in {"played", "failed", "text_only", "cancelled"}


def test_ui_no_unknown_reason() -> None:
    text = (ROOT / "frontend" / "src" / "screens" / "MinimalUI.tsx").read_text(encoding="utf-8")
    assert "unknown reason" not in text
    assert "stopped without reason" not in text


def test_ui_has_autolisten_toggle() -> None:
    text = (ROOT / "frontend" / "src" / "screens" / "MinimalUI.tsx").read_text(encoding="utf-8")
    assert "24/7" in text
    assert "listener_enabled" in text


def test_ui_has_microphone_debug_button() -> None:
    text = (ROOT / "frontend" / "src" / "screens" / "MinimalUI.tsx").read_text(encoding="utf-8")
    assert "onTestMicrophone(selectedDevice)" in text
    assert "debugOpenMicrophone" in (ROOT / "frontend" / "src" / "api" / "client.ts").read_text(encoding="utf-8")


def test_ui_has_commands_crud() -> None:
    text = (ROOT / "frontend" / "src" / "screens" / "MinimalUI.tsx").read_text(encoding="utf-8")
    assert "api.createCommand" in text
    assert "api.updateCommand" in text
    assert "api.deleteCommand" in text
