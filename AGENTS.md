# SKM - Skill Manager

A CLI tool that manages AI agent skills by cloning GitHub repos, detecting skills via `SKILL.md`, and symlinking them to agent directories based on a central YAML config.

## Tech Stack

- Python 3.12+, uv, click, pyyaml, pydantic
- Git operations via subprocess (unified `run_cmd` helper raises `click.ClickException` on failure)
- Tests: pytest

## Project Structure

```
src/skm/
├── cli.py              # Click CLI entry point (group + subcommands)
├── types.py            # Pydantic data models + constants
├── agents.py           # Runtime agent path/mode resolution shared by install, update, list
├── config.py           # Load skills.yaml → SkmConfig
├── lock.py             # Read/write skills-lock.yaml
├── detect.py           # Walk cloned repos for SKILL.md files; select_skill_dirs() applies the same rules to a git tree listing
├── git.py              # Sparse clone (no-checkout + ls-tree + sparse-checkout), pull, fetch, commit SHA helpers (unified run_cmd error handling)
├── utils.py            # Utility functions (compact_path)
├── linker.py           # Symlink skills to agent dirs, resolve includes/excludes
├── local_sources.py    # Device-local sources: symlinks in <config dir>/local_sources/
└── commands/
    ├── install.py      # Clone repos, detect skills, link to agents, update lock
    ├── list_cmd.py     # Print installed skills from lock file
    ├── check_updates.py # Fetch remotes, compare commits, show available updates
    └── update.py       # Pull latest for a skill's repo, re-link, update lock
tests/
├── test_types.py        # Pydantic model validation
├── test_config.py       # Config loading, error handling
├── test_lock.py         # Lock file I/O
├── test_detect.py       # Skill detection logic (local + network tests against real repos); select_skill_dirs() path-list rules
├── test_git.py          # Git operations (sparse clone command sequence, real local-repo sparse checkout, pull re-sparsing, clone failure handling)
├── test_linker.py       # Symlink creation, agent filtering
├── test_install.py      # Install command unit tests
├── test_local_sources.py # `install --local`, local_sources scanning, remove of local-source skills
└── test_cli_e2e.py      # End-to-end CLI tests for all commands
```

## Key Paths

- **Config:** `~/.config/skm/skills.yaml` — YAML dict with `packages` (repo list) and optional `agents.default` / `agents.override`
- **Lock:** `~/.config/skm/skills-lock.yaml` — tracks installed skills, commits, symlink paths
- **Local sources:** `~/.config/skm/local_sources/` — always `skills.yaml`'s parent dir (so `--config` isolates it too); holds a self-ignoring `.gitignore` (`*`)
- **Store:** `~/.local/share/skm/skills/` — cloned repos cached here
- **Agent dirs:** Skills are symlinked into each agent's skill directory (e.g. `~/.claude/skills/`, `~/.codex/skills/`)

## Architecture

Config-driven: parse `skills.yaml` → sparse-clone repos to store → detect skills by walking for `SKILL.md` → symlink to agent dirs → write lock file.

## Sparse Clone

`clone_or_pull()` in `git.py` never checks out a whole repo. It clones with `--filter=blob:none --no-checkout`, lists HEAD's tree via `git ls-tree -r -z HEAD` (tree objects are always fetched, so this is offline), feeds the path list to `select_skill_dirs()` in `detect.py`, and runs `git sparse-checkout set --cone <dirs>` before `git checkout`. After every `git pull` the sparse set is recomputed so skills added upstream get materialized. A root-level `SKILL.md` (singleton) or a repo with no skills disables sparse checkout and checks out everything. `select_skill_dirs()` must stay in sync with `detect_skills()`; both share the rules listed under Skill Detection.

Each command function (`run_install`, `run_list`, etc.) accepts explicit paths and agent dicts as parameters, making them testable with `tmp_path` fixtures without touching real filesystem locations.

## Error Handling

All git subprocess calls go through `run_cmd()` in `git.py`, which captures stdout/stderr and raises `click.ClickException` on non-zero exit codes. This produces user-friendly error messages instead of raw `CalledProcessError` tracebacks.

## Path Handling

Paths stored in `skills-lock.yaml` (e.g. `linked_to`) use `compact_path()` from `utils.py` to replace the home directory with `~`, avoiding exposure of usernames. It only compacts at a path-separator boundary, so a sibling such as `/Users/x2/...` stays absolute (`~2/...` would make `expanduser()` raise). When reading these paths back for filesystem operations, `Path.expanduser()` is used.

## CLI Commands

- `skm install` — Sparse-clone repos (idempotent: skips pull if already cloned), detect skills, create symlinks, remove stale links, update lock. Treats `skills.yaml` as declarative state: removes links for skills dropped from config or agents changed by includes/excludes. Only removes links tracked in the lock file — manually created files in agent dirs are never touched.
- `skm install --local <dir>` — Symlink `<dir>` (resolved absolute) into `local_sources/` and install just that source; never writes `skills.yaml`. See Local Sources.
- `skm list` — Show installed skills and their linked paths from lock file
- `skm check-updates` — Fetch remotes, compare against locked commits, show changelog
- `skm update <skill_name>` — Pull latest for a skill's repo, re-link, update lock

## Local Sources

Lets one `skills.yaml` be shared across devices (config dir in git) while each device installs extra skills. Full `skm install` turns every usable entry into `SkillRepoConfig(local_path=<entry path>)` (all skills, default agents) and passes them via `run_install(local_sources=...)` — they must never be written to `skills.yaml`. Local sources win same-name conflicts: `install.LocalOverrides` maps each skill name to the owning local source (first entry name wins among local sources); every other package skips it and `run_install_package` drops other sources' lock entries for skills its local source takes over, so `update` never re-links an overridden skill. The lock's `local_path` is the entry path, not the resolved target, which is how `skm remove` recognises a local-source skill (`is_local_source_path`); remove only ever unlinks the entry, never its target.

## Config Format (skills.yaml)

Top-level YAML dict with `packages` and optional `agents`:

```yaml
agents:
  default:                   # optional: select which BUILTIN_AGENTS are active (omit = all)
    - claude
    - standard
  override:
    standard:
      install_mode: materialize
    claude:
      path: ~/custom-claude/skills

packages:
  - repo: https://github.com/vercel-labs/agent-skills
    skills:                  # optional: filter to specific skills (omit = all)
      - react-best-practices
    agents:                  # optional: further filter agents for this package
      excludes:
        - standard
  - local_path: ~/Code/devblocks
    skills_excludes:         # optional: install all skills EXCEPT these (mutually exclusive with skills)
      - team-squad
  - repo: https://github.com/blader/humanizer   # installs all detected skills to default agents
```

`agents.default` selects which agents from `BUILTIN_AGENTS` are used as the base set. Per-package `agents.includes/excludes` then filters from that base set.

## Skill Detection

A skill is a directory containing a `SKILL.md` file with YAML frontmatter including a `name` field. Detection order:
1. Root `SKILL.md` → singleton skill (the repo itself is the skill)
2. `./skills/` subdirectory exists → walk its children
3. Otherwise → walk all subdirectories from repo root
4. Stop descending once `SKILL.md` is found (no nested skill-in-skill)

During traversal, `.git` and directories whose names start with `_` are skipped.

## Known Agents

Defined in `src/skm/types.py` as `BUILTIN_AGENTS`:
- `standard` → `~/.agents/skills`
- `claude` → `~/.claude/skills`
- `codex` → `~/.codex/skills`
- `openclaw` → `~/.openclaw/skills`
- `pi` → `~/.pi/agent/skills`

`BUILTIN_AGENTS` stores `AgentSpec` definitions; `agents.resolve_agents()` returns runtime `ResolvedAgent` paths and modes. Priority: `--agents-dir` → override path → non-empty agent environment variable (`CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `PI_CODING_AGENT_DIR`, each with `/skills`) → built-in path. Only openclaw defaults to `materialize`; other agents default to `symlink`, and `agents.override` can change either field for built-in names only. `override.path` must be absolute or start with `~`; relative paths are rejected at config validation because cleanup would resolve them against whatever cwd the next command runs in.

Pass resolved agents into install/update/list; linker receives only the path and `install_mode`. List compares exact parent directories and falls back with a warning on unreadable config; normal list recognizes all built-ins, while `--all` scans defaults. Install, direct package reinstall, and updates with new commits clean tracked obsolete paths; unchanged updates retain old installs and lock paths. Cleanup never compares lock paths as plain strings only: an old path that is the same location as a new one (`utils.same_install_location`, same name and `samefile` parent) is kept, so symlinked or case-different agent dirs do not lose fresh installs. A target the user declined to overwrite is kept and dropped from the lock.

## Testing

### Running Tests

```bash
uv sync
uv run pytest -v              # all tests
uv run pytest tests/test_cli_e2e.py -v   # e2e only
uv run pytest -k "install" -v            # filter by name
```

### Test Isolation

All tests run entirely within pytest's `tmp_path` — no real agent directories, config files, or git repos are touched. This is achieved two ways:

- **Unit tests** (`test_install.py`, `test_linker.py`, etc.): call `run_*` functions directly with explicit `config`/`lock_path`/`store_dir`/`known_agents` parameters pointing to `tmp_path` subdirectories.
- **E2E tests** (`test_cli_e2e.py`): invoke the CLI through Click's `CliRunner` with `--config`, `--store`, `--lock`, and `--agents-dir` flags to redirect all I/O into `tmp_path`.

Git repos used in tests are local repos created via `git init` inside `tmp_path` — no network access required. Tests marked with `@pytest.mark.network` clone real GitHub repos and require internet access.

### CLI Path Overrides

The CLI group accepts four flags to override default paths, useful for both testing and safe manual experimentation:

```bash
skm --config /tmp/test.yaml \
    --store /tmp/store \
    --lock /tmp/lock.yaml \
    --agents-dir /tmp/agents \
    install
```

- `--config` — path to `skills.yaml` (default: `~/.config/skm/skills.yaml`)
- `--lock` — path to `skills-lock.yaml` (default: `~/.config/skm/skills-lock.yaml`)
- `--store` — directory for cloned repos (default: `~/.local/share/skm/skills/`)
- `--agents-dir` — base directory for agent installs; creates subdirs per agent name (overrides `BUILTIN_AGENTS` paths)

### E2E Test Helpers

`test_cli_e2e.py` provides reusable helpers for writing new tests:

- `_make_skill_repo(base, repo_name, skills)` — creates a local git repo with specified skills. Each skill is `{"name": str, "subdir": bool}` where `subdir=True` (default) puts it under `skills/<name>/`, `False` makes it a singleton at repo root.
- `_cli_args(tmp_path)` — returns the common `--config/--store/--lock/--agents-dir` flags for full isolation.
- `_write_config(tmp_path, repos, agents=None)` — writes a `skills.yaml` with `{"packages": repos}` format, optionally including `agents` config.
- `_load_lock(tmp_path)` — loads the lock file as a plain dict for assertions.

### Writing New Tests

To add a new e2e test, follow this pattern:

```python
def test_my_scenario(self, tmp_path):
    repo = _make_skill_repo(tmp_path, "my-repo", [{"name": "my-skill"}])
    _write_config(tmp_path, [{"repo": str(repo)}])  # wraps in {"packages": ...}

    runner = CliRunner()
    result = runner.invoke(cli, [*_cli_args(tmp_path), "install"])

    assert result.exit_code == 0, result.output
    # assert on symlinks, lock contents, output text, etc.
```

## Development

```bash
uv sync
uv run pytest -v      # run tests
uv run skm --help     # run CLI
```

Do not run formatters or style linters on the code.

## Publishing

The PyPI package is `skm-cli`. Use `uv version --bump minor` (or the appropriate bump) to update both `pyproject.toml` and `uv.lock`; run the test suite and build with `uv build --out-dir tmp/<date>-release-<version>/dist`. Publish only that version's wheel and sdist with `uv publish <wheel> <sdist>` to avoid uploading old artifacts, then push the release commit and its `v<version>` tag.
