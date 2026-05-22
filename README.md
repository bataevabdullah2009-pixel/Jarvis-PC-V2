# JARVIS PC V2 Minimal Assistant

## Как запускать свежую dev-версию
Запустите `RUN_DEV_FRESH.bat` двойным щелчком мыши в корне проекта.
Это запустит:
- FastAPI Backend из исходников
- Vite Frontend Dev Server с hot-reload
- Electron в режиме разработки
При закрытии Electron-окна все фоновые процессы backend/frontend автоматически остановятся.

## Как собрать и запустить свежую app-версию
Запустите `UPDATE_AND_LAUNCH_APP.bat` двойным щелчком мыши в корне проекта.
Это выполнит:
1. `git pull`
2. Проверку зависимостей
3. Запуск backend-тестов (`pytest`)
4. Сборку frontend и компиляцию backend в `.exe`
5. Упаковку Electron-приложения
6. Автоматическое архивирование старых версий в `_archive/old_builds/`
7. Копирование свежего билда в папку `app_current/`
8. Запуск актуального приложения `app_current/JARVIS PC V2.exe`

## Где лежит актуальное приложение
`app_current/JARVIS PC V2.exe` (это финальная рабочая папка, откуда всегда можно запускать свежую версию).

## Почему старый exe не обновляется
Потому что Electron package содержит уже собранный frontend/backend. После изменений кода надо пересобрать приложение или запускать dev mode.

## Как очистить старые архивные сборки
Скрипт не удаляет файлы безвозвратно. Он переносит старые сборки, установщики и legacy-артефакты в `_archive/old_builds/YYYY-MM-DD_HH-MM/`.
Для управления архивами можно запустить:
```powershell
python tools\cleanup_old_builds.py
```
После запуска проверьте отчеты:
- `tools/cleanup_report.txt`
- `tools/cleanup_report.json`

