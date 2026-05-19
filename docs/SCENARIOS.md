# JARVIS PC V2 - Scenarios

## Scenario Contract

Each scenario receives normalized input/context and returns:

```json
{
  "scenario": "welcome_home",
  "status": "completed",
  "response_text": "С возвращением, сэр.",
  "actions": [],
  "warnings": []
}
```

Scenarios may request PC actions, but those actions must still pass safety validation.

## welcome_home

### Triggers

- `джарвис я вернулся`
- `я вернулся`
- `джарвис я дома`
- `стартовый режим`

### Actions

1. Say: `С возвращением, сэр.`
2. Open KION/MTS Music search:

```text
https://music.kion.ru/search?text=Back%20in%20Black
```

3. Attempt to start/open the track if possible.
4. If autoplay is impossible, say:

```text
Я открыл Back in Black в Кион Музыке, сэр.
```

### Phase 1 Behavior

Open browser search page and return text response. Do not depend on audio playback success.

## news

### Triggers

- `есть новости`
- `что нового`
- `открой новости`
- `прочитай новости`

### Actions

1. Open browser with configured news page.
2. Try RSS/feed retrieval.
3. Extract 3-5 headlines.
4. Read short summary.
5. If feed is unavailable, open browser and say fallback:

```text
Сэр, я открыл новости в браузере. Лента сейчас недоступна, поэтому прочитать заголовки не удалось.
```

### Phase 1 Behavior

Use browser opening plus optional feed read if dependency-free implementation is available.

## workspace

### Triggers

- `настрой мою среду работы`
- `рабочий режим`
- `запусти рабочую среду`

### Actions

1. Open ChatGPT.
2. Open VS Code.
3. Open configured project path.
4. Optionally open terminal.
5. Say:

```text
Рабочая среда готова, сэр.
```

### Configurable Values

- ChatGPT URL.
- VS Code executable or command.
- Project path.
- Open terminal flag.

Default project path candidates:

- `C:\Jarvis\jarvis-car`
- configured V2 project path.

## music

### Triggers

- `открой музыку`
- `включи музыку`
- `найди back in black`

### Actions

1. Build KION/MTS Music search URL.
2. Open in browser.
3. Attempt playback through browser focus plus Windows media play/pause hotkey.
4. Say that playback was started/attempted.

### Important Playback Rule

Opening a music page is not enough. The scenario must return a `play_music_search` action with `playback_attempted = true` when the backend sends the playback attempt. If browser autoplay policy, focus, or login state prevents real playback, the action must say so honestly instead of pretending the track played.

The initial Windows implementation opens the KION/MTS Music search page, waits for browser load, sends Enter, then sends the system media play/pause key. This is the strongest safe local action available without browser credentials or unsupported private APIs.

## location

### Triggers

- `найди локацию`
- `покажи локацию`
- `где находится`

### Actions

1. Parse location query.
2. Open configured map/search provider.
3. Emit location event for Command Center.
4. Ask clarification if location text is missing.

## Scenario Matching Rules

- Normalize case.
- Strip punctuation.
- Remove optional prefix `джарвис`.
- Prefer exact trigger match.
- Then use simple phrase contains matching.
- If multiple scenarios match, choose highest confidence.
- If confidence is low, continue to custom/local command matching.
