# JARVIS PC V2 - Test Plan

## Testing Strategy

Every phase must have tests before being called complete. Phase 1 focuses on backend command routing and deterministic scenarios.

## Phase 1 Tests

### Unit Tests

Command normalization:

- strips punctuation;
- lowercases text;
- handles optional `джарвис` prefix;
- keeps Russian text intact.

Scenario matching:

- `Джарвис, я вернулся` -> `welcome_home`
- `Есть новости?` -> `news`
- `Настрой мою среду работы` -> `workspace`

Safety:

- safe URL open allowed;
- Telegram allowlist open allowed;
- shutdown requires confirmation;
- unknown shell command denied or requires confirmation.

AI fallback:

- unknown command calls planner when provider available;
- if provider unavailable, returns:

```text
Сэр, интернет недоступен. Локальные команды работают.
```

TTS fallback:

- Fish Audio failure falls back to offline TTS;
- offline TTS failure returns text-only.

### API Tests

Required:

- `GET /health`
- `GET /runtime/build-info`
- `POST /assistant/command`

Manual command acceptance:

- `Джарвис, я вернулся`
- `Есть новости?`
- `Настрой мою среду работы`
- `Джарвис, открой Telegram`
- `Джарвис, придумай идею для сайта`

## Phase 2 Tests

Voice dependency:

- sounddevice installed/not installed.
- microphone exists/not found.

Microphone:

- device list returns structured data.
- RMS test returns numeric metrics.

STT:

- configured provider returns transcript.
- missing STT does not break microphone test.
- Vosk is reported as configured when package and local model exist.

Voice command:

- transcript is sent to `/assistant/command`.

TTS:

- Fish Audio dry-run path is available when credentials exist.
- offline TTS fallback is available.
- text-only fallback remains final fallback.

Music playback:

- music scenario returns `play_music_search`, not plain `open_url`.
- welcome-home scenario attempts playback of Back in Black.

## Phase 3 Tests

Minimal UI:

- loads by default;
- health status visible;
- command input submits;
- quick buttons call expected endpoints;
- error state visible.

## Phase 4 Tests

Command Center:

- opens from Minimal UI;
- receives WebSocket events;
- Earth/location view does not break core command flow.

## Phase 5 Tests

Packaging:

- Electron launches hidden backend;
- backend health is reachable from UI;
- no browser dev mode in production;
- no license gate blocks features.

## Manual Smoke Test

Before any "done" claim:

1. Start backend.
2. Check `/health`.
3. Run five Phase 1 manual commands.
4. Verify logs.
5. Verify fallback message with AI disabled.
6. Run automated tests.
