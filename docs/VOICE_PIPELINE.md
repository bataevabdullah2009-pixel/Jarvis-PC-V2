# JARVIS PC V2 - Voice Pipeline

## Goal

Voice must improve the assistant without becoming a single point of failure. If any voice component breaks, manual command input remains usable.

## Pipeline

```text
microphone
-> wake/clap
-> record audio
-> STT
-> transcript
-> /assistant/command
-> response text
-> TTS
-> audio playback
-> UI state
```

## Modes

### Manual Text

Always available. This is the fallback path for all phases.

### Manual Record

The user presses a microphone button. Backend records a short clip, runs STT if configured, then submits transcript to `/assistant/command`.

### Listener

The backend listens for wake word and/or clap, then records a command.

## Dependency Rules

### sounddevice Missing

Expected behavior:

- `/voice/dependency-check` returns `sounddevice.available = false`.
- UI shows install hint.
- Manual text commands still work.

Install hint:

```text
pip install sounddevice
```

### Microphone Missing

Expected behavior:

- `/voice/devices` returns empty list.
- UI status becomes "Ошибка микрофона."
- Manual text commands still work.

### STT Not Configured

Expected behavior:

- microphone tests still work;
- recording can capture audio diagnostics;
- transcript is unavailable;
- UI tells user STT is not configured.

### Fish Audio Failure

Expected behavior:

- fallback to offline TTS;
- if offline TTS works, speak locally;
- if offline TTS fails, use text-only response.

### Offline TTS Failure

Expected behavior:

- assistant returns `response_text`;
- UI displays text;
- no crash.

## TTS Provider Priority

1. Fish Audio.
2. Offline TTS through pyttsx3 / Windows SAPI.
3. Text-only.

## STT Provider Priority

Initial target:

1. Configured online STT provider if available.
2. Vosk offline STT if installed and model exists.
3. Transcript unavailable, but microphone diagnostics remain available.

V2 Phase 2 includes an offline Vosk path. The default model path is:

```text
backend\models\vosk-model-small-ru-0.22
```

The helper script `tools/download_vosk_model.py` installs that model locally. The model directory is ignored by git.

## Voice State Model

Possible states:

- `idle`
- `listening`
- `recording`
- `transcribing`
- `executing`
- `speaking`
- `error`
- `text_only`

## Voice Logs

Voice logs must include:

- dependency availability;
- selected microphone device;
- RMS/peak from microphone test;
- STT provider selection;
- TTS provider selection;
- fallback path;
- sanitized errors.

Never log secret API keys.

## TTS Provider Chain

Phase 2 TTS order:

1. Fish Audio through `https://api.fish.audio/v1/tts`.
2. Offline TTS through pyttsx3 / Windows SAPI.
3. Text-only fallback.

Tests and diagnostics may use `dry_run` so the backend can validate the path without spending online TTS quota or speaking unexpectedly.
