# JARVIS PC V2 - UI Specification

## UI Strategy

Minimal UI is the default. Command Center is advanced mode. Debug information is hidden unless Debug Mode is enabled.

## Minimal UI

### Purpose

Fast command execution and clear assistant status.

### Required Elements

- Title: `JARVIS PC V2`
- Assistant status:
  - `Готов, сэр.`
  - `Слушаю, сэр.`
  - `Выполняю, сэр.`
  - `Ошибка микрофона.`
- Central orb animation.
- Text command input.
- Microphone button.
- Quick buttons:
  - `Голос`
  - `Новости`
  - `Музыка`
  - `Найти локацию`
  - `Рабочая среда`
  - `Командный центр`
  - `Настройки`
- Four compact statuses:
  - `Backend`
  - `Микрофон`
  - `ИИ`
  - `Команды`

### Behavior

- Enter submits text to `/assistant/command`.
- Microphone button calls voice endpoints.
- Quick buttons call scenario endpoints or prefilled commands.
- Backend status polls `/health`.
- Debug Mode reveals raw JSON and build info.

## Command Center

### Purpose

Advanced operational HUD for diagnostics, locations, provider status, news, and system events.

### Required Areas

- Earth visualization.
- Locations panel.
- Providers panel.
- News panel.
- System monitor.
- Event stream from `/ws/events`.
- Diagnostics panel.

### Phase 4 Implementation

- Earth visualization uses a lazy-loaded Three.js scene.
- Command Center consumes `/ws/events`, `/voice/dependency-check`, `/diagnostics/full-test`, and `/diagnostics/system-monitor`.
- Minimal UI remains the default screen.

### Rules

- Command Center must not be the default screen.
- Command Center must not break Minimal UI state.
- It should consume the same backend APIs as Minimal UI.
- Expensive visual effects should be optional or degraded on weak machines.

## Settings

Settings screen must support:

- voice profile;
- provider status;
- project path;
- default browser/news/music URLs;
- Debug Mode;
- offline mode preference;
- safe command allowlist visibility.

Secrets must be masked. API keys are never shown in full.

## Diagnostics

Diagnostics screen must support:

- `/health/full`;
- `/voice/dependency-check`;
- `/voice/devices`;
- microphone test;
- scenario test;
- event log view in Debug Mode.

## Debug Mode

Only Debug Mode may show:

- raw JSON;
- logs;
- build info details;
- provider error details;
- internal event payloads.

## Visual Priority

Phase order:

1. Working backend logic.
2. Minimal UI command flow.
3. Minimal UI voice controls.
4. Diagnostics visibility.
5. Command Center visuals.
