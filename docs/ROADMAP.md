# JARVIS PC V2 - Roadmap

## Methodology

Development order is strict:

```text
SPEC -> ARCHITECTURE -> PLAN -> TASKS -> CODE -> TESTS
```

No code starts until architecture is approved.

## Phase 0 - Specification And Architecture

Deliverables:

- `docs/SPEC.md`
- `docs/ARCHITECTURE.md`
- `docs/API_CONTRACTS.md`
- `docs/VOICE_PIPELINE.md`
- `docs/SCENARIOS.md`
- `docs/UI_SPEC.md`
- `docs/SAFETY_RULES.md`
- `docs/TEST_PLAN.md`
- `docs/ROADMAP.md`

Exit criteria:

- user approves architecture;
- Phase 1 scope is confirmed.

## Phase 1 - Working Backend Without Pretty UI

Deliverables:

1. FastAPI backend skeleton.
2. `/health`.
3. `/runtime/build-info`.
4. `/assistant/command`.
5. Command router.
6. Scenarios:
   - `welcome_home`
   - `news`
   - `workspace`
7. PC actions needed by scenarios.
8. TTS fallback text-only.
9. Logs.
10. Tests.

Exit criteria:

- manual input works for required five commands;
- automated tests pass;
- no license gate exists.

## Phase 2 - Voice

Deliverables:

1. sounddevice dependency check.
2. microphone devices.
3. microphone test with RMS.
4. record command.
5. STT integration/fallback.
6. TTS provider chain.
7. voice logs.

Exit criteria:

- microphone is visible;
- RMS shows sound;
- voice command becomes text;
- text reaches `/assistant/command`.

## Phase 3 - Minimal UI

Deliverables:

1. main screen.
2. statuses.
3. command input.
4. quick buttons.
5. settings.
6. diagnostics.

Exit criteria:

- Minimal UI starts by default;
- manual commands work through UI;
- health indicators reflect backend state.

## Phase 4 - Command Center

Deliverables:

1. Earth/location view.
2. provider panels.
3. news panel.
4. system monitor.
5. WebSocket events.
6. diagnostics panel.

Exit criteria:

- Command Center opens from Minimal UI;
- Minimal UI remains stable;
- WebSocket events are visible.

Status:

- Implemented in `frontend/src/screens/CommandCenter.tsx`.
- 3D Earth is loaded as a separate lazy chunk.
- System monitor is available at `GET /diagnostics/system-monitor`.
- WebSocket snapshots/events are available at `/ws/events`.

## Phase 5 - Packaging

Deliverables:

1. Electron app packaging.
2. hidden backend start.
3. start script.
4. installer.
5. production mode without browser dev mode.

Exit criteria:

- app launches as desktop app;
- backend starts automatically;
- core commands work after installation.

Status:

- Electron packaging is configured in `frontend/package.json`.
- Packaged app starts the backend hidden from `frontend/electron/main.cjs`.
- `tools/package_app.bat` builds a portable desktop app.
- `tools/package_installer.bat` builds an NSIS installer.
- Packaging scripts build `JarvisBackend.exe` before Electron packaging so installed apps do not depend on a system Python runtime.
- Phase 5 smoke passed: `release/win-unpacked/JARVIS PC V2.exe` starts the hidden packaged backend and routes `я вернулся` to `scenario:welcome_home`.
- Installer artifact: `release/JARVIS-PC-V2-0.1.0-x64.exe`.

## Backlog

- offline Vosk STT model management;
- command history;
- richer custom command editor;
- advanced location tools;
- plugin/skill system;
- more voice profile tuning;
- optional SQLite storage.
