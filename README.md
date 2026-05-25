# JARVIS PC V2 Minimal Assistant

## Главный Запуск

Запускайте JARVIS из корня проекта:

```bat
START_JARVIS.bat
```

`START_JARVIS.bat` является основным launcher для обычной работы.

Backend работает на фиксированном порту `18000`.

Frontend работает на порту `5173`.

Backend URL:

```text
http://127.0.0.1:18000
```

Frontend API base:

```text
VITE_JARVIS_API_BASE=http://127.0.0.1:18000
```

Если другой backend занимает порт `8000`, это не мешает JARVIS.

Порт `8000` не является runtime-портом JARVIS.

## AI Providers

JARVIS использует provider routing:

```text
JARVIS_AI_PRIMARY=groq
JARVIS_AI_FALLBACK=openrouter
JARVIS_AI_ALLOW_LOCAL_FALLBACK=true
```

Groq работает через OpenAI-compatible endpoint:

```text
https://api.groq.com/openai/v1/chat/completions
```

OpenRouter остается fallback provider.

Если оба облачных provider недоступны, JARVIS возвращает локальный fallback text.

Локальные команды выполняются без обращения к AI.

Выбор primary/fallback доступен через настройки UI и через `.env`.

## Voice Stack

Основной голос:

```text
JARVIS_TTS_PRIMARY=fish_audio
JARVIS_TTS_REQUIRE_FISH_AUDIO=true
JARVIS_TTS_FALLBACK_ENABLED=false
```

В Jarvis style запрещены Edge TTS и pyttsx3 fallback.

Если Fish Audio недоступен, runtime возвращает `text_only` с точной причиной.

`provider=none` считается ошибкой и не должен появляться в TTS ответах.

Очередь TTS публикует финальные статусы:

```text
tts.queued
tts.started
tts.generated
tts.played
tts.failed
```

`/voice/tts-status` показывает последний job, provider, ошибку и размер очереди.

## Local Voice Providers

Архитектура подготовлена для локальных voice providers:

```text
fish_audio
piper_local
xtts_local
gpt_sovits_local
text_only
```

Piper, XTTS и GPT-SoVITS не устанавливаются автоматически.

Диагностика доступна через:

```text
GET /debug/local-voice-status
```

## Listener

Listener по умолчанию включен:

```text
JARVIS_LISTENER_ENABLED=true
JARVIS_LISTENER_AUTOSTART=true
JARVIS_WAKE_WORDS=джарвис,чарли,jarvis
JARVIS_COMMAND_RECORD_SECONDS=6
JARVIS_COOLDOWN_MS=2500
JARVIS_IGNORE_SELF_AUDIO=true
```

Если микрофон или STT не готовы, backend не падает.

Listener переходит в `blocked` и возвращает точную причину.

Статус доступен через:

```text
GET /voice/listener-status
```

## Anti-Echo

Пока JARVIS говорит, listener не отправляет transcript в assistant.

После TTS включается cooldown.

Transcript, похожий на последний TTS text, игнорируется.

После повторяющегося self-echo listener блокируется.

Новый assistant request сериализуется и не стартует параллельно с предыдущим.

## Diagnostics

Основные endpoints:

```powershell
curl.exe http://127.0.0.1:18000/health
curl.exe http://127.0.0.1:18000/debug/env-status
curl.exe http://127.0.0.1:18000/debug/ai-provider-status
curl.exe http://127.0.0.1:18000/debug/voice-provider-status
curl.exe http://127.0.0.1:18000/debug/local-voice-status
curl.exe http://127.0.0.1:18000/voice/listener-status
```

Проверка Groq:

```powershell
curl.exe -X POST http://127.0.0.1:18000/debug/test-groq -H "Content-Type: application/json" -d "{\"text\":\"Ответь одним словом: OK\"}"
```

Проверка голоса:

```powershell
curl.exe -X POST http://127.0.0.1:18000/debug/test-jarvis-voice -H "Content-Type: application/json" -d "{\"text\":\"Проверка голоса Джарвиса.\"}"
```

## Smoke Runtime

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\smoke_runtime.ps1
```

Smoke проверяет backend startup, diagnostics endpoints, listener state и assistant ask на порту `18000`.

## Source Format Guard

Перед commit:

```powershell
python tools\check_source_format.py
```

Guard проверяет переносы строк, минимальную длину launcher-файлов, длинную первую строку и компиляцию Python.
