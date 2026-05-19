# JARVIS PC V2 - Safety Rules

## Goal

The assistant must be useful for local PC control while preventing destructive or surprising actions.

## Action Categories

### Allowed Without Confirmation

- `open_url`
- `open_app` from allowlist
- `play_music_search`
- `read_news`
- `location_search`
- `volume_up`
- `volume_down`
- `screenshot`
- `open_folder` from allowlist

### Requires Confirmation

- `shutdown`
- `restart`
- `close_process`
- `run_shell`
- `install_package`
- `move_file`
- `edit_settings`

### Forbidden Without Dev Mode

- `delete_file`
- `format_disk`
- `registry_edit`
- `disable_defender`
- launching unknown `.exe` files
- shell commands containing dangerous tokens such as:
  - `del`
  - `rm`
  - `format`
  - `reg`
  - `Remove-Item`
  - `rmdir`

## Allowlist Examples

### Apps

Initial allowlist candidates:

- VS Code
- Telegram
- browser
- terminal if configured

Unknown executables require either confirmation or Dev Mode depending on risk.

### Folders

Initial allowlist candidates:

- configured project folder;
- configured user workspace folders.

## Confirmation Flow

When an action requires confirmation:

1. Router returns `requires_confirmation = true`.
2. Response includes `confirmation_id`.
3. UI asks user to approve.
4. `/assistant/confirm` executes only if approved.
5. Denial returns a calm text response.

## AI Planner Safety

AI planner may propose actions but cannot bypass safety. Every planner action must be validated by `core/safety.py`.

Planner outputs must be treated as untrusted input.

## Logging

Safety decisions must be logged:

- action type;
- risk level;
- allow/confirm/deny decision;
- sanitized reason.

Do not log full secrets, tokens, or sensitive command payloads.

## License Rule

V2 has no active license gate. Safety must not be implemented as a license restriction. No feature is blocked by license state.

