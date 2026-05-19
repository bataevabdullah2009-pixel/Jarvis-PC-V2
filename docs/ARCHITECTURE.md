# JARVIS PC V2 - Architecture

## System Shape

JARVIS PC V2 is a local desktop assistant composed of:

- FastAPI backend for command processing, scenarios, voice services, providers, storage, diagnostics, and event streaming.
- Electron + React frontend for Minimal UI, Command Center, settings, and diagnostics.
- Local configuration files for settings, scenarios, and custom commands.
- Logs for observability and debugging.

## Repository Structure

```text
Jarvis_PC_V2/
  backend/
    app/
      main.py
      core/
        config.py
        logging.py
        runtime.py
        safety.py
      voice/
        microphone.py
        stt.py
        tts.py
        wake.py
        clap.py
        voice_pipeline.py
      router/
        command_router.py
        ai_planner.py
        intent_detector.py
      scenarios/
        welcome_home.py
        news.py
        workspace.py
        music.py
        location.py
      pc/
        apps.py
        browser.py
        volume.py
        screenshots.py
        hotkeys.py
        system.py
      providers/
        openrouter.py
        groq.py
        fish_audio.py
        offline_tts.py
      news/
        feed.py
        reader.py
      music/
        kion_music.py
        browser_music.py
      geo/
        location_service.py
      events/
        websocket_bus.py
      diagnostics/
        health.py
        full_test.py
      storage/
        settings_store.py
        command_store.py
    config/
      settings.json
      local_commands_ru.json
      scenarios.json
    logs/
    requirements.txt
    pyproject.toml
  frontend/
    electron/
    src/
      screens/
        MinimalUI.tsx
        CommandCenter.tsx
        Settings.tsx
        Diagnostics.tsx
      components/
      api/
      styles/
  docs/
  tools/
    start_dev.bat
    check_env.py
    find_old_jarvis_versions.py
    archive_old_jarvis_versions.py
```

## Backend Layers

### API Layer

FastAPI exposes HTTP endpoints and WebSocket events. API handlers should be thin:

1. validate request;
2. call domain service;
3. return normalized response;
4. emit events where useful.

### Command Router

The command router is the central execution path. It receives text commands from UI, voice pipeline, tests, or API clients.

Pipeline:

```text
User input
-> normalize text
-> scenario matcher
-> custom command matcher
-> local command matcher
-> skill matcher
-> AI planner fallback
-> safety check
-> execute
-> event bus
-> TTS
-> UI update
-> logs
```

### Scenario Layer

Scenarios are deterministic workflows. They should return structured action results and user-facing speech text. They should not directly know about UI implementation.

### PC Control Layer

PC modules wrap OS-level behavior:

- apps
- browser
- volume
- screenshots
- hotkeys
- system

All PC actions must pass through safety rules.

### Provider Layer

Provider clients isolate online services:

- OpenRouter for AI planning.
- Groq as optional AI/STT provider.
- Fish Audio for online TTS.
- Offline TTS through local Windows options.

Provider errors must be converted to predictable internal errors and fallback states.

### Event Bus

The backend publishes events to `/ws/events` for frontend state updates:

- status changes;
- command lifecycle;
- scenario progress;
- voice state;
- provider failures;
- diagnostics.

### Storage Layer

Storage is local and file-based in early phases:

- `settings.json`
- `local_commands_ru.json`
- `scenarios.json`

Later phases may add SQLite if command history, audit, or richer state requires it.

## Frontend Layers

### Minimal UI

Default screen for real work:

- assistant status;
- orb state;
- text command input;
- microphone button;
- quick buttons;
- compact health statuses.

### Command Center

Advanced operational HUD:

- Earth visualization;
- locations;
- provider status;
- news panel;
- system monitor;
- event stream;
- diagnostics.

### Debug Mode

Raw JSON, logs, build info, and internal diagnostics are visible only when Debug Mode is enabled.

## Configuration And Secrets

Secrets must not be committed. Required secret-like values:

- Fish Audio API key.
- OpenRouter API key.
- Fish Audio voice/model id.

Recommended environment variables:

- `JARVIS_FISH_AUDIO_API_KEY`
- `JARVIS_OPENROUTER_API_KEY`
- `JARVIS_FISH_AUDIO_VOICE_ID`

Local ignored settings can mirror these values for developer convenience, but repository templates must contain placeholders only.

## Build And Runtime

Development mode:

- backend runs with FastAPI/Uvicorn;
- frontend runs with Electron/Vite or equivalent;
- tools/start_dev.bat starts both when implemented.

Production mode:

- Electron launches a hidden backend process;
- browser dev mode is disabled;
- logs remain available locally;
- no license checks block features.

