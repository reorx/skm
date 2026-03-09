# SKM - Skill Manager

A CLI tool that manages AI agent skills from GitHub repos. Clone repos, detect skills via `SKILL.md`, and symlink them into agent directories — all driven by a single YAML config.

## Install

```bash
uv tool install git+https://github.com/reorx/skm
```

## Quick Start

1. Create `~/.config/skm/skills.yaml`:

```yaml
packages:
  - repo: https://github.com/vercel-labs/agent-skills
    skills:
      - vercel-react-best-practices
      - vercel-react-native-skills
  - repo: https://github.com/blader/humanizer
```

2. Run install:

```bash
skm install
```

Skills are cloned and symlinked into your agent directories (`~/.claude/skills/`, `~/.codex/skills/`, etc.).

## Commands

| Command | Description |
|---|---|
| `skm install` | Clone repos, detect skills, symlink to agents, write lock file. Idempotent — won't pull if repo is already cloned. |
| `skm list` | Show installed skills and their linked paths. |
| `skm list --all` | Show all skills across all agent directories, marking which are managed by skm. |
| `skm check-updates` | Fetch remotes and show available updates without changing local repos. |
| `skm update <skill>` | Pull latest for a skill's repo, re-detect, re-link, update lock. |

## Config Format

`~/.config/skm/skills.yaml`:

```yaml
agents:
  default:                   # optional: select which agents are active (omit = all)
    - claude
    - standard

packages:
  - repo: https://github.com/vercel-labs/agent-skills
    skills:                  # optional: install only these skills (omit = all)
      - vercel-react-best-practices
    agents:                  # optional: further filter agents for this package
      excludes:
        - standard

  - repo: https://github.com/blader/humanizer   # installs all detected skills to default agents
```

## Skill Detection

A skill is a directory containing a `SKILL.md` file with YAML frontmatter (`name` field required). Detection order:

1. Root `SKILL.md` — the repo itself is a singleton skill
2. `./skills/` subdirectory exists — scan its children
3. Otherwise — walk all subdirectories from repo root
4. Stop descending once `SKILL.md` is found (no nested skills)

## Known Agents

Skills are symlinked into these directories by default:

| Agent | Path |
|---|---|
| `standard` | `~/.agents/skills/` |
| `claude` | `~/.claude/skills/` |
| `codex` | `~/.codex/skills/` |
| `openclaw` | `~/.openclaw/skills/` |

## CLI Path Overrides

Override default paths for testing or custom setups:

```bash
skm --config /tmp/test.yaml \
    --store /tmp/store \
    --lock /tmp/lock.yaml \
    --agents-dir /tmp/agents \
    install
```

## Key Paths

- **Config:** `~/.config/skm/skills.yaml`
- **Lock:** `~/.config/skm/skills-lock.yaml`
- **Store:** `~/.local/share/skm/skills/`

## Development

```bash
uv sync
uv run pytest -v      # run tests
uv run skm --help     # run CLI
```
