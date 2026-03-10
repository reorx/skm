---
created: 2026-03-10
tags:
  - feature
  - view-command
  - tui
---

# Implement `skm view` command

## What was done

Implemented the `skm view` command that lets users browse and preview skills from a repo URL or local path without installing them.

### Files created
- **`src/skm/tui.py`** — Custom `interactive_select()` widget using ANSI escape codes and `click.getchar()`. Supports arrow keys, j/k navigation, enter to select, q/Ctrl+C to quit. Clears its own output on return so the menu doesn't stack when re-drawn.
- **`src/skm/commands/view.py`** — `run_view()` resolves the source (local dir or git clone), detects skills, loops an interactive menu, and opens SKILL.md with bat/less/pager fallback.

### Files modified
- **`src/skm/cli.py`** — Registered the `view` command (was already done before session started).
- **`pyproject.toml`** — Removed `simple-term-menu` dependency since the custom TUI replaces it.
- **`uv.lock`** — Updated via `uv lock`.

### Bugs fixed during session
1. **Menu stacking** — After closing a skill viewer, the menu was re-drawn below the old one instead of overwriting it. Fixed by clearing all menu lines in `interactive_select` before returning.
2. **Selection state reset** — Cursor always reset to the first item after returning from viewer. Fixed by adding an `initial` parameter to `interactive_select` and tracking `last_idx` in the view loop.

## Key decisions
- No new dependencies — everything built with click + ANSI codes
- Replaced `simple-term-menu` entirely with custom `tui.py`
