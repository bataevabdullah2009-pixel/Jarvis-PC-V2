# JARVIS PC V2 - API Contracts

## Conventions

Base URL in development:

```text
http://127.0.0.1:8000
```

All JSON responses follow the common envelope where practical:

```json
{
  "ok": true,
  "data": {},
  "error": null
}
```

Error shape:

```json
{
  "ok": false,
  "data": null,
  "error": {
    "code": "MICROPHONE_NOT_FOUND",
    "message": "Микрофон не найден.",
    "details": {}
  }
}
```

## Health

### GET /health

Returns lightweight backend health.

Response:

```json
{
  "ok": true,
  "data": {
    "status": "ok",
    "service": "jarvis-pc-v2-backend"
  },
  "error": null
}
```

### GET /health/full

Runs broader health checks.

Response data:

```json
{
  "backend": "ok",
  "settings": "ok",
  "commands": "ok",
  "voice": "degraded",
  "ai": "unknown",
  "tts": "text_only",
  "warnings": []
}
```

### GET /runtime/build-info

Returns build/runtime metadata.

Response data:

```json
{
  "app": "JARVIS PC V2",
  "version": "0.1.0",
  "phase": "phase-1",
  "license_enabled": false,
  "python": "3.x",
  "platform": "Windows"
}
```

## Voice

### GET /voice/dependency-check

Checks voice dependencies without requiring a microphone.

Response data:

```json
{
  "sounddevice": {
    "available": false,
    "install_hint": "pip install sounddevice"
  },
  "stt": {
    "configured": false,
    "provider": null
  },
  "tts": {
    "mode": "text_only",
    "providers": ["fish_audio", "offline_tts", "text_only"]
  }
}
```

### GET /voice/devices

Lists audio input devices.

Response data:

```json
{
  "input_devices": [
    {
      "id": "0",
      "name": "Microphone Array",
      "channels": 1,
      "default": true
    }
  ]
}
```

### POST /voice/test-microphone

Request:

```json
{
  "device_id": "default",
  "duration_seconds": 3
}
```

Response data:

```json
{
  "device_id": "default",
  "rms": 0.034,
  "peak": 0.21,
  "heard_signal": true
}
```

### POST /voice/record-command

Records one command and returns transcript if STT is configured.

Request:

```json
{
  "device_id": "default",
  "max_seconds": 8,
  "send_to_assistant": true,
  "dry_run": false
}
```

Response data:

```json
{
  "transcript": "джарвис есть новости",
  "stt": {
    "configured": true,
    "provider": "vosk"
  },
  "assistant_result": {}
}
```

### POST /voice/start-listener

Starts wake/clap listener.

Request:

```json
{
  "wake_word": true,
  "clap": true,
  "device_id": "default"
}
```

### POST /voice/stop-listener

Stops listener.

## Assistant

### POST /assistant/command

Main command entrypoint.

Request:

```json
{
  "text": "Джарвис, я вернулся",
  "source": "manual",
  "context": {}
}
```

Response data:

```json
{
  "command_id": "cmd_001",
  "status": "completed",
  "route": "scenario:welcome_home",
  "response_text": "С возвращением, сэр.",
  "spoken": false,
  "actions": [
    {
      "type": "open_url",
      "status": "completed",
      "target": "https://music.kion.ru/search?text=Back%20in%20Black"
    }
  ],
  "requires_confirmation": false
}
```

### POST /assistant/plan

Calls planner without executing actions.

Request:

```json
{
  "text": "закрой все процессы chrome",
  "context": {}
}
```

Response data:

```json
{
  "intent": "close_process",
  "risk": "requires_confirmation",
  "answer_text": null,
  "actions": []
}
```

### POST /assistant/confirm

Confirms a pending risky action.

Request:

```json
{
  "confirmation_id": "confirm_001",
  "approved": true
}
```

## Scenarios

### POST /scenarios/welcome-home

Runs welcome home scenario.

### POST /scenarios/news

Runs news scenario.

### POST /scenarios/workspace

Runs workspace scenario.

### POST /scenarios/music

Runs music scenario.

Request:

```json
{
  "query": "Back in Black"
}
```

### POST /scenarios/location

Runs location scenario.

Request:

```json
{
  "query": "Москва"
}
```

## News

### POST /news/open-and-read

Request:

```json
{
  "limit": 5,
  "open_browser": true
}
```

Response data:

```json
{
  "opened_browser": true,
  "source": "rss",
  "headlines": [
    {
      "title": "Example headline",
      "url": "https://example.com/news/1"
    }
  ],
  "response_text": "Вот главные новости, сэр..."
}
```

## Settings

### GET /settings

Returns sanitized settings. Secrets must be masked.

### PATCH /settings

Requires safety check because settings edits can alter behavior.

Request:

```json
{
  "voice": {
    "profile": "Jarvis style"
  },
  "debug_mode": false
}
```

## Commands

### GET /commands

Returns built-in and custom commands.

### POST /commands/custom

Creates a custom command.

### PATCH /commands/custom/{id}

Updates a custom command.

### DELETE /commands/custom/{id}

Deletes a custom command.

## Diagnostics

### GET /diagnostics/full-test

Runs full diagnostics and returns structured result.

### GET /diagnostics/system-monitor

Returns system monitor data for Command Center.

Response data:

```json
{
  "cpu_percent": 18.2,
  "memory_percent": 63.4,
  "disk_percent": 38.6,
  "disk_free_gb": 571.38
}
```

### POST /diagnostics/scenario-test

Request:

```json
{
  "scenario": "welcome_home",
  "dry_run": true
}
```

## WebSocket

### /ws/events

Event shape:

```json
{
  "event_id": "evt_001",
  "type": "assistant.status",
  "timestamp": "2026-05-18T12:00:00Z",
  "payload": {
    "status": "Выполняю, сэр."
  }
}
```

Initial event types:

- `assistant.status`
- `assistant.command.received`
- `assistant.command.completed`
- `assistant.command.failed`
- `scenario.started`
- `scenario.completed`
- `voice.listener.started`
- `voice.listener.stopped`
- `voice.error`
- `provider.error`
- `diagnostics.result`
