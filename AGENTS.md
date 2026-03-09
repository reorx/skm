# SKM - Skill Manager

A CLI tool that manages AI agent skills by cloning GitHub repos, detecting skills via `SKILL.md`, and symlinking them to agent directories based on a central YAML config.

## Tech Stack

- Python 3.12+, uv, click, pyyaml, pydantic
- Git operations via subprocess
- Tests: pytest

## Project Structure

```
src/skm/
├── cli.py              # Click CLI entry point (group + subcommands)
├── types.py            # Pydantic data models + constants
├── config.py           # Load skills.yaml → list[SkillRepoConfig]
├── lock.py             # Read/write skills-lock.yaml
├── detect.py           # Walk cloned repos for SKILL.md files
├── git.py              # Clone, pull, fetch, commit SHA helpers
├── linker.py           # Symlink skills to agent dirs, resolve includes/excludes
└── commands/
    ├── install.py      # Clone repos, detect skills, link to agents, update lock
    ├── list_cmd.py     # Print installed skills from lock file
    ├── check_updates.py # Fetch remotes, compare commits, show available updates
    └── update.py       # Pull latest for a skill's repo, re-link, update lock
tests/
├── test_types.py
├── test_config.py
├── test_lock.py
├── test_detect.py
├── test_git.py
├── test_linker.py
└── test_install.py
```

## Key Paths

- **Config:** `~/.config/skm/skills.yaml` — user-defined list of repos and skills to install
- **Lock:** `~/.config/skm/skills-lock.yaml` — tracks installed skills, commits, symlink paths
- **Store:** `~/.local/share/skm/skills/` — cloned repos cached here
- **Agent dirs:** Skills are symlinked into each agent's skill directory (e.g. `~/.claude/skills/`, `~/.codex/skills/`)

## Architecture

Config-driven: parse `skills.yaml` → clone repos to store → detect skills by walking for `SKILL.md` → symlink to agent dirs → write lock file.

Each command function (`run_install`, `run_list`, etc.) accepts explicit paths and agent dicts as parameters, making them testable with `tmp_path` fixtures without touching real filesystem locations.

## CLI Commands

- `skm install` — Clone repos, detect skills, create symlinks, update lock
- `skm list` — Show installed skills and their linked paths from lock file
- `skm check-updates` — Fetch remotes, compare against locked commits, show changelog
- `skm update <skill_name>` — Pull latest for a skill's repo, re-link, update lock

## Config Format (skills.yaml)

```yaml
- repo: https://github.com/vercel-labs/agent-skills
  skills:                    # optional: filter to specific skills (omit = all)
    - react-best-practices
  agents:                    # optional: control which agents get this skill
    excludes:
      - openclaw
- repo: https://github.com/blader/humanizer   # installs all detected skills to all agents
```

## Skill Detection

A skill is a directory containing a `SKILL.md` file with YAML frontmatter including a `name` field. Detection order:
1. Root `SKILL.md` → singleton skill (the repo itself is the skill)
2. `./skills/` subdirectory exists → walk its children
3. Otherwise → walk all subdirectories from repo root
4. Stop descending once `SKILL.md` is found (no nested skill-in-skill)

## Known Agents

Defined in `src/skm/types.py` as `KNOWN_AGENTS`:
- `standard` → `~/.agents/skills`
- `claude` → `~/.claude/skills`
- `codex` → `~/.codex/skills`
- `openclaw` → `~/.openclaw/skills`

## Development

```bash
uv sync
uv run pytest -v      # run tests
uv run skm --help     # run CLI
```

Do not run formatters or style linters on the code.
