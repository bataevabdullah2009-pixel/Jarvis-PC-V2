# JARVIS PC V2 - Product Specification

## Mission

JARVIS PC V2 is a local Windows-first personal assistant for voice commands, scripted scenarios, PC control, news, music, and AI fallback. The product must work first, then become visually impressive.

The default experience is PC-only. No license gate is enabled in V2. No feature may be blocked by license state, product mismatch, or "LOCAL INVALID" checks.

## Core Principles

1. Working logic before visual polish.
2. Minimal UI is the default interface.
3. Command Center is an advanced mode, not the primary flow.
4. The assistant must never silently fail.
5. Voice failure must degrade to text input and visible status.
6. Online provider failure must degrade to local commands and text-only output.
7. Dangerous actions require confirmation.
8. Secrets are never committed to repository files.

## Target Platform

- OS: Windows 10/11.
- Runtime: local backend process plus Electron frontend.
- Backend: Python, FastAPI.
- Frontend: Electron, React, TypeScript.
- Network: optional. Offline mode must keep local commands usable.

## Primary Interfaces

### Minimal UI

The default screen. It provides status, command input, microphone button, quick scenario buttons, and compact health indicators.

### Command Center

Advanced HUD mode with Earth, locations, providers, news, system monitor, events, and diagnostics. This mode must not block or replace Minimal UI.

## Functional Scope

### Voice Assistant

- Microphone discovery.
- Wake word.
- Clap trigger.
- Manual command recording.
- STT.
- TTS.
- Text fallback when voice components fail.

### Scenarios

Required initial scenarios:

- "Джарвис, я вернулся"
- "Есть новости?"
- "Настрой мою среду работы"
- "Найди локацию"
- "Открой музыку"

### Music

- Open KION/MTS Music search.
- Search for "Back in Black".
- Attempt to open track or search page.
- Browser fallback if deep integration is unavailable.

### News

- Open news in browser.
- Try RSS/feed retrieval.
- Read 3-5 short headlines.
- If feed is unavailable, open browser and say so honestly.

### Workspace

- Open ChatGPT.
- Open VS Code.
- Open configured project path.
- Optionally open terminal.

### PC Control

- Open apps from allowlist.
- Open sites.
- Volume up/down.
- Screenshots.
- Hotkeys.
- Local scenarios.

### AI Fallback

If no deterministic route matches, the assistant sends the command to an AI planner. The planner must decide one of:

- answer with text;
- execute a safe action;
- ask a clarification;
- request confirmation for a risky action.

If AI is unavailable:

> Сэр, интернет недоступен. Локальные команды работают.

### Offline Mode

Offline mode must support:

- local command routing;
- local scenarios that do not require online APIs;
- offline TTS where possible;
- optional offline STT through Vosk.

## Voice Profiles

Supported profile names:

- Jarvis style
- Calm Russian
- Robot
- Friday style
- Custom

Provider priority:

1. Fish Audio online TTS.
2. Offline TTS through pyttsx3 / Windows SAPI.
3. Text-only fallback.

Provider credentials must be configured via environment variables or local ignored settings, never committed to docs or source.

## Phase 1 Definition Of Done

Phase 1 is backend-only and complete when manual text input works for:

- "Джарвис, я вернулся"
- "Есть новости?"
- "Настрой мою среду работы"
- "Джарвис, открой Telegram"
- "Джарвис, придумай идею для сайта"

Required Phase 1 deliverables:

- `/health`
- `/runtime/build-info`
- `/assistant/command`
- command router
- `welcome_home`, `news`, `workspace` scenarios
- text-only TTS fallback
- logs
- tests

