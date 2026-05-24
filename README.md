# JARVIS PC V2 Minimal Assistant

## Главный запуск

Запускайте JARVIS только из корня проекта:

```bat
START_JARVIS.bat
```

`START_JARVIS.bat` вызывает `tools\start_jarvis.ps1`, который:

- определяет root проекта;
- останавливает старые JARVIS процессы;
- освобождает port 8000 только от `LISTENING` JARVIS PID;
- игнорирует `TIME_WAIT` и PID 0;
- проверяет `backend\.env`;
- проверяет и устанавливает backend dependencies;
- проверяет и устанавливает frontend dependencies;
- запускает FastAPI backend и ждёт `/health`;
- запускает Vite frontend и ждёт `http://127.0.0.1:5173`;
- запускает Electron;
- при закрытии Electron останавливает backend и frontend.

## Legacy launchers

Эти файлы оставлены только для совместимости:

- `RUN_DEV_FRESH.bat` перенаправляет на `START_JARVIS.bat`.
- `UPDATE_AND_LAUNCH_APP.bat` нужен только для update/package сценария.

Для обычного запуска их не используйте.

## Diagnostics

Backend runtime diagnostics:

```powershell
curl.exe http://127.0.0.1:8000/debug/env-status
curl.exe http://127.0.0.1:8000/debug/network-status
curl.exe http://127.0.0.1:8000/debug/voice-provider-status
```

OpenRouter проверяется отдельно от наличия ключа. Если ключ есть, но сеть/TLS падает, UI должен показывать network timeout, а не "OpenRouter API key отсутствует".

Jarvis voice зафиксирован на Fish Audio для `Jarvis style`. Если Fish Audio недоступен, система переходит в `text_only`; Edge TTS и pyttsx3 не используются как чужой голос.

## Runtime Smoke

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\smoke_runtime.ps1
```

Smoke падает при crash backend. OpenRouter network timeout считается warning, потому что внешний провайдер может быть временно недоступен, а локальные команды должны продолжать работать.
