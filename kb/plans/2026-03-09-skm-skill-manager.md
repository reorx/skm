# SKM (Skill Manager) Implementation Plan


**Goal:** Build a CLI tool that manages agent skills by cloning GitHub repos, detecting skills via SKILL.md, and symlinking them to agent directories based on a central YAML config.

**Architecture:** Config-driven approach: parse `~/.config/skm/skills.yaml` to know which repos/skills to install, clone repos to `~/.local/share/skm/skills/`, detect skills by walking for SKILL.md files, then symlink to agent dirs. A lock file tracks installed state. Click CLI with subcommands: install, check-updates, update, list.

**Tech Stack:** Python 3.12+, uv, click, pyyaml, pydantic, git (subprocess)

---

## Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/skm/__init__.py`
- Create: `src/skm/cli.py`
- Create: `src/skm/types.py`

**Step 1: Initialize the project with uv**

Run:
```bash
cd /Users/reorx/Code/skm
uv init --lib --package
```

**Step 2: Edit pyproject.toml**

Set up the project metadata and dependencies:

```toml
[project]
name = "skm"
version = "0.1.0"
description = "Skill Manager - manage agent skills from GitHub repos"
requires-python = ">=3.12"
dependencies = [
    "click>=8.1",
    "pyyaml>=6.0",
    "pydantic>=2.0",
]

[project.scripts]
skm = "skm.cli:cli"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/skm"]
```

**Step 3: Create minimal CLI entry point**

`src/skm/cli.py`:
```python
import click


@click.group()
def cli():
    """SKM - Skill Manager for AI coding agents."""
    pass


@cli.command()
def install():
    """Install/remove skills based on config."""
    click.echo("install: not yet implemented")


@cli.command()
def check_updates():
    """Check for skill updates."""
    click.echo("check-updates: not yet implemented")


@cli.command()
@click.argument("skill_name")
def update(skill_name: str):
    """Update a specific skill."""
    click.echo(f"update {skill_name}: not yet implemented")


@cli.command(name="list")
def list_skills():
    """List installed skills and their linked paths."""
    click.echo("list: not yet implemented")
```

**Step 4: Create `__init__.py`**

`src/skm/__init__.py`:
```python
```

**Step 5: Install the project in dev mode and verify**

Run:
```bash
uv sync
uv run skm --help
```
Expected: Help text showing install, check-updates, update, list commands.

**Step 6: Commit**

```bash
git init
git add pyproject.toml src/ uv.lock
git commit -m "feat: scaffold skm project with click CLI"
```

---

## Task 2: Data Models (types.py)

**Files:**
- Create: `src/skm/types.py`
- Create: `tests/test_types.py`

**Step 1: Write tests for config parsing**

`tests/test_types.py`:
```python
import pytest
from skm.types import SkillRepoConfig, AgentsConfig


def test_skill_repo_config_minimal():
    """Repo with no skills listed and no agents config."""
    cfg = SkillRepoConfig(repo="https://github.com/blader/humanizer")
    assert cfg.repo == "https://github.com/blader/humanizer"
    assert cfg.skills is None
    assert cfg.agents is None


def test_skill_repo_config_with_skills():
    cfg = SkillRepoConfig(
        repo="https://github.com/vercel-labs/agent-skills",
        skills=["react-best-practices", "react-native-skills"],
    )
    assert cfg.skills == ["react-best-practices", "react-native-skills"]


def test_agents_config_excludes():
    agents = AgentsConfig(excludes=["openclaw"])
    assert agents.excludes == ["openclaw"]
    assert agents.includes is None


def test_agents_config_includes():
    agents = AgentsConfig(includes=["claude", "codex"])
    assert agents.includes == ["claude", "codex"]
    assert agents.excludes is None


def test_skill_repo_config_with_agents():
    cfg = SkillRepoConfig(
        repo="https://github.com/vercel-labs/agent-skills",
        skills=["react-best-practices"],
        agents=AgentsConfig(excludes=["openclaw"]),
    )
    assert cfg.agents.excludes == ["openclaw"]
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_types.py -v`
Expected: FAIL - cannot import `skm.types`

**Step 3: Implement data models**

`src/skm/types.py`:
```python
from pathlib import Path
from pydantic import BaseModel


# --- Config models (parsed from skills.yaml) ---

class AgentsConfig(BaseModel):
    includes: list[str] | None = None
    excludes: list[str] | None = None


class SkillRepoConfig(BaseModel):
    repo: str
    skills: list[str] | None = None
    agents: AgentsConfig | None = None


# --- Lock file models ---

class InstalledSkill(BaseModel):
    name: str
    repo: str
    commit: str
    skill_path: str  # relative path within repo to the skill dir
    linked_to: list[str]  # list of absolute symlink paths


class LockFile(BaseModel):
    skills: list[InstalledSkill] = []


# --- Runtime models ---

class DetectedSkill(BaseModel):
    """A skill detected by walking a cloned repo."""
    name: str  # from SKILL.md frontmatter
    path: Path  # absolute path to the skill directory
    relative_path: str  # relative path within the repo


# --- Constants ---

KNOWN_AGENTS: dict[str, str] = {
    "standard": "~/.agents/skills",
    "claude": "~/.claude/skills",
    "codex": "~/.codex/skills",
    "openclaw": "~/.openclaw/skills",
}

CONFIG_DIR = Path("~/.config/skm").expanduser()
CONFIG_PATH = CONFIG_DIR / "skills.yaml"
LOCK_PATH = CONFIG_DIR / "skills-lock.yaml"
STORE_DIR = Path("~/.local/share/skm/skills").expanduser()
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_types.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/skm/types.py tests/
git commit -m "feat: add data models for config, lock file, and skill detection"
```

---

## Task 3: Config Loading

**Files:**
- Create: `src/skm/config.py`
- Create: `tests/test_config.py`

**Step 1: Write tests for loading config from YAML**

`tests/test_config.py`:
```python
import pytest
from pathlib import Path
from skm.config import load_config


EXAMPLE_YAML = """\
- repo: https://github.com/vercel-labs/agent-skills
  skills:
    - react-best-practices
    - web-design-guidelines
  agents:
    excludes:
      - openclaw
- repo: https://github.com/blader/humanizer
"""


def test_load_config(tmp_path):
    config_file = tmp_path / "skills.yaml"
    config_file.write_text(EXAMPLE_YAML)
    configs = load_config(config_file)
    assert len(configs) == 2
    assert configs[0].repo == "https://github.com/vercel-labs/agent-skills"
    assert configs[0].skills == ["react-best-practices", "web-design-guidelines"]
    assert configs[0].agents.excludes == ["openclaw"]
    assert configs[1].repo == "https://github.com/blader/humanizer"
    assert configs[1].skills is None
    assert configs[1].agents is None


def test_load_config_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nonexistent.yaml")


def test_load_config_empty_file(tmp_path):
    config_file = tmp_path / "skills.yaml"
    config_file.write_text("")
    with pytest.raises(ValueError, match="empty"):
        load_config(config_file)
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL

**Step 3: Implement config loading**

`src/skm/config.py`:
```python
from pathlib import Path

import yaml

from skm.types import SkillRepoConfig


def load_config(config_path: Path) -> list[SkillRepoConfig]:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    text = config_path.read_text()
    data = yaml.safe_load(text)

    if not data:
        raise ValueError(f"Config file is empty: {config_path}")

    return [SkillRepoConfig(**item) for item in data]
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_config.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/skm/config.py tests/test_config.py
git commit -m "feat: add config loading from YAML"
```

---

## Task 4: Lock File Read/Write

**Files:**
- Create: `src/skm/lock.py`
- Create: `tests/test_lock.py`

**Step 1: Write tests for lock file operations**

`tests/test_lock.py`:
```python
from skm.lock import load_lock, save_lock
from skm.types import LockFile, InstalledSkill


def test_load_lock_missing_file(tmp_path):
    lock = load_lock(tmp_path / "nonexistent.yaml")
    assert lock.skills == []


def test_save_and_load_lock(tmp_path):
    lock_path = tmp_path / "skills-lock.yaml"
    lock = LockFile(skills=[
        InstalledSkill(
            name="react-best-practices",
            repo="https://github.com/vercel-labs/agent-skills",
            commit="abc1234",
            skill_path="skills/react-best-practices",
            linked_to=["/Users/test/.claude/skills/react-best-practices"],
        )
    ])
    save_lock(lock, lock_path)
    loaded = load_lock(lock_path)
    assert len(loaded.skills) == 1
    assert loaded.skills[0].name == "react-best-practices"
    assert loaded.skills[0].commit == "abc1234"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_lock.py -v`
Expected: FAIL

**Step 3: Implement lock file operations**

`src/skm/lock.py`:
```python
from pathlib import Path

import yaml

from skm.types import LockFile, InstalledSkill


def load_lock(lock_path: Path) -> LockFile:
    if not lock_path.exists():
        return LockFile()

    data = yaml.safe_load(lock_path.read_text())
    if not data or "skills" not in data:
        return LockFile()

    return LockFile(skills=[InstalledSkill(**s) for s in data["skills"]])


def save_lock(lock: LockFile, lock_path: Path) -> None:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    data = {"skills": [s.model_dump() for s in lock.skills]}
    lock_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_lock.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/skm/lock.py tests/test_lock.py
git commit -m "feat: add lock file read/write"
```

---

## Task 5: Skill Detection (walk repo for SKILL.md)

**Files:**
- Create: `src/skm/detect.py`
- Create: `tests/test_detect.py`

**Step 1: Write tests for skill detection**

`tests/test_detect.py`:
```python
from skm.detect import detect_skills


def _write_skill_md(path, name):
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text(f"---\nname: {name}\ndescription: test\n---\nContent\n")


def test_detect_singleton_skill(tmp_path):
    """Repo root has SKILL.md - it's a singleton skill."""
    _write_skill_md(tmp_path, "my-skill")
    skills = detect_skills(tmp_path)
    assert len(skills) == 1
    assert skills[0].name == "my-skill"
    assert skills[0].path == tmp_path
    assert skills[0].relative_path == "."


def test_detect_skills_in_skills_dir(tmp_path):
    """Repo has ./skills/ dir with sub-skills."""
    skills_dir = tmp_path / "skills"
    _write_skill_md(skills_dir / "skill-a", "skill-a")
    _write_skill_md(skills_dir / "skill-b", "skill-b")
    # Also create a non-skill dir
    (skills_dir / "not-a-skill").mkdir(parents=True)
    (skills_dir / "not-a-skill" / "README.md").write_text("nope")

    skills = detect_skills(tmp_path)
    names = {s.name for s in skills}
    assert names == {"skill-a", "skill-b"}


def test_detect_skills_no_skills_dir(tmp_path):
    """No ./skills/ dir, walk from root."""
    _write_skill_md(tmp_path / "foo", "foo-skill")
    _write_skill_md(tmp_path / "bar", "bar-skill")
    skills = detect_skills(tmp_path)
    names = {s.name for s in skills}
    assert names == {"foo-skill", "bar-skill"}


def test_detect_skills_nested_stop_at_skill(tmp_path):
    """Once SKILL.md is found, don't dig deeper."""
    _write_skill_md(tmp_path / "outer", "outer-skill")
    # Nested SKILL.md should NOT be found separately
    _write_skill_md(tmp_path / "outer" / "inner", "inner-skill")
    skills = detect_skills(tmp_path)
    assert len(skills) == 1
    assert skills[0].name == "outer-skill"


def test_detect_skills_empty_repo(tmp_path):
    """No SKILL.md anywhere."""
    (tmp_path / "src").mkdir()
    (tmp_path / "README.md").write_text("hello")
    skills = detect_skills(tmp_path)
    assert skills == []
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_detect.py -v`
Expected: FAIL

**Step 3: Implement skill detection**

`src/skm/detect.py`:
```python
import re
from pathlib import Path

from skm.types import DetectedSkill


def parse_skill_name(skill_md_path: Path) -> str:
    """Extract 'name' from SKILL.md YAML frontmatter."""
    text = skill_md_path.read_text()
    match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not match:
        raise ValueError(f"No frontmatter found in {skill_md_path}")
    for line in match.group(1).splitlines():
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip()
    raise ValueError(f"No 'name' field in frontmatter of {skill_md_path}")


def detect_skills(repo_path: Path) -> list[DetectedSkill]:
    """Detect skills in a cloned repo by walking for SKILL.md files."""
    # Case 1: Root has SKILL.md → singleton skill
    root_skill = repo_path / "SKILL.md"
    if root_skill.exists():
        name = parse_skill_name(root_skill)
        return [DetectedSkill(name=name, path=repo_path, relative_path=".")]

    # Determine walk root
    skills_dir = repo_path / "skills"
    walk_root = skills_dir if skills_dir.is_dir() else repo_path

    return _walk_for_skills(walk_root, repo_path)


def _walk_for_skills(walk_root: Path, repo_path: Path) -> list[DetectedSkill]:
    """Walk subdirectories looking for SKILL.md. Stop descending once found."""
    results = []
    for child in sorted(walk_root.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith("."):
            continue
        skill_md = child / "SKILL.md"
        if skill_md.exists():
            name = parse_skill_name(skill_md)
            relative = str(child.relative_to(repo_path))
            results.append(DetectedSkill(name=name, path=child, relative_path=relative))
        else:
            # Recurse deeper
            results.extend(_walk_for_skills(child, repo_path))
    return results
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_detect.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/skm/detect.py tests/test_detect.py
git commit -m "feat: add skill detection by walking repos for SKILL.md"
```

---

## Task 6: Git Operations

**Files:**
- Create: `src/skm/git.py`
- Create: `tests/test_git.py`

**Step 1: Write tests for git helpers**

`tests/test_git.py`:
```python
import subprocess
from skm.git import clone_or_pull, get_head_commit, repo_url_to_dirname


def test_repo_url_to_dirname():
    assert repo_url_to_dirname("https://github.com/vercel-labs/agent-skills") == "github.com_vercel-labs_agent-skills"
    assert repo_url_to_dirname("http://github.com/better-auth/skills") == "github.com_better-auth_skills"


def test_clone_and_get_commit(tmp_path):
    """Create a local git repo, clone it, and check commit."""
    # Set up a source repo
    src = tmp_path / "source"
    src.mkdir()
    subprocess.run(["git", "init"], cwd=src, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=src, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=src, capture_output=True)
    (src / "README.md").write_text("hello")
    subprocess.run(["git", "add", "."], cwd=src, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=src, capture_output=True)

    # Clone it
    dest = tmp_path / "dest"
    clone_or_pull(str(src), dest)
    assert (dest / "README.md").exists()

    commit = get_head_commit(dest)
    assert len(commit) == 40  # full SHA

    # Pull again (should not error)
    clone_or_pull(str(src), dest)
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_git.py -v`
Expected: FAIL

**Step 3: Implement git operations**

`src/skm/git.py`:
```python
import subprocess
from pathlib import Path
from urllib.parse import urlparse


def repo_url_to_dirname(repo_url: str) -> str:
    """Convert a repo URL to a filesystem-safe directory name."""
    parsed = urlparse(repo_url)
    # e.g. "github.com/vercel-labs/agent-skills" -> "github.com_vercel-labs_agent-skills"
    path = parsed.path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    return f"{parsed.hostname}_{path.replace('/', '_')}"


def clone_or_pull(repo_url: str, dest: Path) -> None:
    """Clone repo if not present, otherwise pull latest."""
    if dest.exists() and (dest / ".git").exists():
        subprocess.run(
            ["git", "pull", "--ff-only"],
            cwd=dest,
            capture_output=True,
            check=True,
        )
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", repo_url, str(dest)],
            capture_output=True,
            check=True,
        )


def get_head_commit(repo_path: Path) -> str:
    """Get the HEAD commit SHA of a repo."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def get_log_since(repo_path: Path, since_commit: str, max_count: int = 20) -> str:
    """Get git log from a commit to HEAD."""
    result = subprocess.run(
        ["git", "log", f"{since_commit}..HEAD", "--oneline", f"--max-count={max_count}"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def fetch(repo_path: Path) -> None:
    """Fetch latest from remote without merging."""
    subprocess.run(
        ["git", "fetch"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )


def get_remote_head_commit(repo_path: Path) -> str:
    """Get the remote HEAD commit after fetch."""
    result = subprocess.run(
        ["git", "rev-parse", "origin/HEAD"],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # fallback: try origin/main or origin/master
        for branch in ["origin/main", "origin/master"]:
            result = subprocess.run(
                ["git", "rev-parse", branch],
                cwd=repo_path,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        raise RuntimeError(f"Cannot determine remote HEAD for {repo_path}")
    return result.stdout.strip()


def get_log_between(repo_path: Path, old_commit: str, new_commit: str, max_count: int = 20) -> str:
    """Get git log between two commits."""
    result = subprocess.run(
        ["git", "log", f"{old_commit}..{new_commit}", "--oneline", f"--max-count={max_count}"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_git.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/skm/git.py tests/test_git.py
git commit -m "feat: add git operations (clone, pull, commit tracking)"
```

---

## Task 7: Linking Logic

**Files:**
- Create: `src/skm/linker.py`
- Create: `tests/test_linker.py`

**Step 1: Write tests for linking skills to agent dirs**

`tests/test_linker.py`:
```python
from skm.linker import resolve_target_agents, link_skill, unlink_skill


def test_resolve_target_agents_all(tmp_path):
    """No includes/excludes → all agents."""
    agents = {"claude": str(tmp_path / "claude"), "codex": str(tmp_path / "codex")}
    result = resolve_target_agents(None, agents)
    assert set(result.keys()) == {"claude", "codex"}


def test_resolve_target_agents_excludes(tmp_path):
    agents = {"claude": str(tmp_path / "claude"), "codex": str(tmp_path / "codex"), "openclaw": str(tmp_path / "openclaw")}
    from skm.types import AgentsConfig
    cfg = AgentsConfig(excludes=["openclaw"])
    result = resolve_target_agents(cfg, agents)
    assert "openclaw" not in result
    assert "claude" in result


def test_resolve_target_agents_includes(tmp_path):
    agents = {"claude": str(tmp_path / "claude"), "codex": str(tmp_path / "codex"), "openclaw": str(tmp_path / "openclaw")}
    from skm.types import AgentsConfig
    cfg = AgentsConfig(includes=["claude"])
    result = resolve_target_agents(cfg, agents)
    assert set(result.keys()) == {"claude"}


def test_link_skill(tmp_path):
    """Link a skill dir to an agent skill dir."""
    skill_src = tmp_path / "store" / "my-skill"
    skill_src.mkdir(parents=True)
    (skill_src / "SKILL.md").write_text("---\nname: my-skill\n---\n")

    agent_dir = tmp_path / "agent" / "skills"
    agent_dir.mkdir(parents=True)

    linked = link_skill(skill_src, "my-skill", str(agent_dir))
    assert linked.is_symlink()
    assert linked.resolve() == skill_src.resolve()
    assert linked.name == "my-skill"


def test_link_skill_already_linked(tmp_path):
    """Re-linking same source is idempotent."""
    skill_src = tmp_path / "store" / "my-skill"
    skill_src.mkdir(parents=True)
    agent_dir = tmp_path / "agent" / "skills"
    agent_dir.mkdir(parents=True)

    link_skill(skill_src, "my-skill", str(agent_dir))
    linked = link_skill(skill_src, "my-skill", str(agent_dir))
    assert linked.is_symlink()


def test_unlink_skill(tmp_path):
    """Unlink removes the symlink."""
    skill_src = tmp_path / "store" / "my-skill"
    skill_src.mkdir(parents=True)
    agent_dir = tmp_path / "agent" / "skills"
    agent_dir.mkdir(parents=True)

    link_skill(skill_src, "my-skill", str(agent_dir))
    target = agent_dir / "my-skill"
    assert target.is_symlink()

    unlink_skill("my-skill", str(agent_dir))
    assert not target.exists()
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_linker.py -v`
Expected: FAIL

**Step 3: Implement linking**

`src/skm/linker.py`:
```python
from pathlib import Path

from skm.types import AgentsConfig


def resolve_target_agents(
    agents_config: AgentsConfig | None,
    known_agents: dict[str, str],
) -> dict[str, str]:
    """Determine which agents to install to based on includes/excludes."""
    if agents_config is None:
        return dict(known_agents)

    if agents_config.includes is not None:
        return {k: v for k, v in known_agents.items() if k in agents_config.includes}

    if agents_config.excludes is not None:
        return {k: v for k, v in known_agents.items() if k not in agents_config.excludes}

    return dict(known_agents)


def link_skill(skill_src: Path, skill_name: str, agent_skills_dir: str) -> Path:
    """Create a symlink from agent_skills_dir/skill_name -> skill_src."""
    target_dir = Path(agent_skills_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    link_path = target_dir / skill_name

    if link_path.is_symlink():
        if link_path.resolve() == skill_src.resolve():
            return link_path
        link_path.unlink()

    if link_path.exists():
        raise FileExistsError(f"{link_path} exists and is not a symlink")

    link_path.symlink_to(skill_src)
    return link_path


def unlink_skill(skill_name: str, agent_skills_dir: str) -> None:
    """Remove symlink for a skill from an agent dir."""
    link_path = Path(agent_skills_dir) / skill_name
    if link_path.is_symlink():
        link_path.unlink()
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_linker.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/skm/linker.py tests/test_linker.py
git commit -m "feat: add skill linking/unlinking to agent directories"
```

---

## Task 8: Install Command

**Files:**
- Modify: `src/skm/cli.py`
- Create: `src/skm/commands/install.py`
- Create: `tests/test_install.py`

This is the core command that ties everything together.

**Step 1: Write integration test for install**

`tests/test_install.py`:
```python
import subprocess
from pathlib import Path
from skm.commands.install import run_install
from skm.types import KNOWN_AGENTS


def _make_skill_repo(tmp_path, name, skills_subdir=True):
    """Create a minimal local git repo with a skill."""
    repo = tmp_path / f"repo-{name}"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, capture_output=True)

    if skills_subdir:
        skill_dir = repo / "skills" / name
    else:
        skill_dir = repo

    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(f"---\nname: {name}\ndescription: test\n---\nContent\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True)
    return repo


def test_install_basic(tmp_path):
    """Install a skill from a local repo, verify symlinks and lock file."""
    repo = _make_skill_repo(tmp_path, "test-skill")

    config_path = tmp_path / "config" / "skills.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(f"- repo: {repo}\n  skills:\n    - test-skill\n")

    lock_path = tmp_path / "config" / "skills-lock.yaml"
    store_dir = tmp_path / "store"

    # Use tmp dirs as agent targets
    agents = {
        "claude": str(tmp_path / "agents" / "claude" / "skills"),
        "codex": str(tmp_path / "agents" / "codex" / "skills"),
    }

    run_install(
        config_path=config_path,
        lock_path=lock_path,
        store_dir=store_dir,
        known_agents=agents,
    )

    # Check symlinks exist
    assert (tmp_path / "agents" / "claude" / "skills" / "test-skill").is_symlink()
    assert (tmp_path / "agents" / "codex" / "skills" / "test-skill").is_symlink()

    # Check lock file
    assert lock_path.exists()


def test_install_singleton_skill(tmp_path):
    """Install a singleton skill (SKILL.md at repo root)."""
    repo = _make_skill_repo(tmp_path, "singleton", skills_subdir=False)

    config_path = tmp_path / "config" / "skills.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(f"- repo: {repo}\n")

    lock_path = tmp_path / "config" / "skills-lock.yaml"
    store_dir = tmp_path / "store"
    agents = {"claude": str(tmp_path / "agents" / "claude" / "skills")}

    run_install(
        config_path=config_path,
        lock_path=lock_path,
        store_dir=store_dir,
        known_agents=agents,
    )

    assert (tmp_path / "agents" / "claude" / "skills" / "singleton").is_symlink()
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_install.py -v`
Expected: FAIL

**Step 3: Create commands package and implement install**

`src/skm/commands/__init__.py`:
```python
```

`src/skm/commands/install.py`:
```python
from pathlib import Path

import click

from skm.config import load_config
from skm.detect import detect_skills
from skm.git import clone_or_pull, get_head_commit, repo_url_to_dirname
from skm.linker import link_skill, unlink_skill, resolve_target_agents
from skm.lock import load_lock, save_lock
from skm.types import InstalledSkill, LockFile


def run_install(
    config_path: Path,
    lock_path: Path,
    store_dir: Path,
    known_agents: dict[str, str],
) -> None:
    configs = load_config(config_path)
    lock = load_lock(lock_path)
    new_lock_skills: list[InstalledSkill] = []

    # Track which skills are configured (for removal detection)
    configured_skill_names: set[str] = set()

    for repo_config in configs:
        repo_dir_name = repo_url_to_dirname(repo_config.repo)
        repo_path = store_dir / repo_dir_name

        # Clone if not already cloned
        if not repo_path.exists():
            click.echo(f"Cloning {repo_config.repo}...")
            clone_or_pull(repo_config.repo, repo_path)
        else:
            click.echo(f"Already cloned: {repo_config.repo}")

        commit = get_head_commit(repo_path)
        detected = detect_skills(repo_path)
        target_agents = resolve_target_agents(repo_config.agents, known_agents)

        # Filter to requested skills (if specified)
        if repo_config.skills is not None:
            requested = set(repo_config.skills)
            skills_to_install = [s for s in detected if s.name in requested]
            missing = requested - {s.name for s in skills_to_install}
            if missing:
                click.echo(f"  Warning: skills not found in repo: {missing}")
        else:
            # No filter → install all detected skills
            skills_to_install = detected

        for skill in skills_to_install:
            configured_skill_names.add(skill.name)
            linked_paths = []

            for agent_name, agent_dir in target_agents.items():
                link = link_skill(skill.path, skill.name, agent_dir)
                linked_paths.append(str(link))
                click.echo(f"  Linked {skill.name} -> [{agent_name}] {link}")

            new_lock_skills.append(InstalledSkill(
                name=skill.name,
                repo=repo_config.repo,
                commit=commit,
                skill_path=skill.relative_path,
                linked_to=linked_paths,
            ))

    # Remove skills that were in old lock but no longer in config
    for old_skill in lock.skills:
        if old_skill.name not in configured_skill_names:
            click.echo(f"  Removing {old_skill.name} (no longer in config)")
            for link_path in old_skill.linked_to:
                p = Path(link_path)
                if p.is_symlink():
                    p.unlink()

    new_lock = LockFile(skills=new_lock_skills)
    save_lock(new_lock, lock_path)
    click.echo(f"Lock file updated: {lock_path}")
```

**Step 4: Wire up the CLI command**

Update `src/skm/cli.py`:
```python
import click

from skm.types import CONFIG_PATH, LOCK_PATH, STORE_DIR, KNOWN_AGENTS
from skm.commands.install import run_install


@click.group()
def cli():
    """SKM - Skill Manager for AI coding agents."""
    pass


@cli.command()
def install():
    """Install/remove skills based on config."""
    agents = {name: str(path) for name, path in _expand_agents().items()}
    run_install(
        config_path=CONFIG_PATH,
        lock_path=LOCK_PATH,
        store_dir=STORE_DIR,
        known_agents=agents,
    )


def _expand_agents() -> dict[str, str]:
    from pathlib import Path
    return {name: str(Path(path).expanduser()) for name, path in KNOWN_AGENTS.items()}


@cli.command()
def check_updates():
    """Check for skill updates."""
    click.echo("check-updates: not yet implemented")


@cli.command()
@click.argument("skill_name")
def update(skill_name: str):
    """Update a specific skill."""
    click.echo(f"update {skill_name}: not yet implemented")


@cli.command(name="list")
def list_skills():
    """List installed skills and their linked paths."""
    click.echo("list: not yet implemented")
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_install.py -v`
Expected: All PASS

**Step 6: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS

**Step 7: Commit**

```bash
git add src/skm/commands/ src/skm/cli.py tests/test_install.py
git commit -m "feat: implement install command with clone, detect, and link"
```

---

## Task 9: List Command

**Files:**
- Create: `src/skm/commands/list_cmd.py`
- Modify: `src/skm/cli.py`

**Step 1: Implement list command**

`src/skm/commands/list_cmd.py`:
```python
from pathlib import Path

import click

from skm.lock import load_lock


def run_list(lock_path: Path) -> None:
    lock = load_lock(lock_path)

    if not lock.skills:
        click.echo("No skills installed.")
        return

    for skill in lock.skills:
        click.echo(f"{skill.name}  ({skill.repo})")
        click.echo(f"  commit: {skill.commit[:8]}")
        for link in skill.linked_to:
            click.echo(f"  -> {link}")
```

**Step 2: Wire up in cli.py**

Replace the `list_skills` placeholder:
```python
@cli.command(name="list")
def list_skills():
    """List installed skills and their linked paths."""
    from skm.commands.list_cmd import run_list
    run_list(LOCK_PATH)
```

**Step 3: Commit**

```bash
git add src/skm/commands/list_cmd.py src/skm/cli.py
git commit -m "feat: implement list command"
```

---

## Task 10: Check-Updates Command

**Files:**
- Create: `src/skm/commands/check_updates.py`
- Modify: `src/skm/cli.py`

**Step 1: Implement check-updates**

`src/skm/commands/check_updates.py`:
```python
from pathlib import Path

import click

from skm.git import fetch, get_head_commit, get_remote_head_commit, get_log_between, repo_url_to_dirname
from skm.lock import load_lock


def run_check_updates(lock_path: Path, store_dir: Path) -> None:
    lock = load_lock(lock_path)

    if not lock.skills:
        click.echo("No skills installed.")
        return

    # Group by repo
    repos: dict[str, list] = {}
    for skill in lock.skills:
        repos.setdefault(skill.repo, []).append(skill)

    has_updates = False

    for repo_url, skills in repos.items():
        repo_dir_name = repo_url_to_dirname(repo_url)
        repo_path = store_dir / repo_dir_name

        if not repo_path.exists():
            click.echo(f"⚠ Repo not found locally: {repo_url}")
            continue

        click.echo(f"Fetching {repo_url}...")
        fetch(repo_path)

        local_commit = skills[0].commit  # all skills from same repo share commit
        remote_commit = get_remote_head_commit(repo_path)

        if local_commit == remote_commit:
            click.echo(f"  ✓ Up to date")
            continue

        has_updates = True
        log = get_log_between(repo_path, local_commit, remote_commit)
        skill_names = ", ".join(s.name for s in skills)
        click.echo(f"  Updates available for: {skill_names}")
        click.echo(f"  {local_commit[:8]} -> {remote_commit[:8]}")
        if log:
            for line in log.splitlines():
                click.echo(f"    {line}")

    if not has_updates:
        click.echo("\nAll skills are up to date.")
```

**Step 2: Wire up in cli.py**

Replace the `check_updates` placeholder:
```python
@cli.command(name="check-updates")
def check_updates():
    """Check for skill updates."""
    from skm.commands.check_updates import run_check_updates
    run_check_updates(LOCK_PATH, STORE_DIR)
```

**Step 3: Commit**

```bash
git add src/skm/commands/check_updates.py src/skm/cli.py
git commit -m "feat: implement check-updates command"
```

---

## Task 11: Update Command

**Files:**
- Create: `src/skm/commands/update.py`
- Modify: `src/skm/cli.py`

**Step 1: Implement update command**

`src/skm/commands/update.py`:
```python
from pathlib import Path

import click

from skm.config import load_config
from skm.detect import detect_skills
from skm.git import clone_or_pull, get_head_commit, get_log_between, repo_url_to_dirname
from skm.linker import link_skill, resolve_target_agents
from skm.lock import load_lock, save_lock
from skm.types import InstalledSkill


def run_update(
    skill_name: str,
    config_path: Path,
    lock_path: Path,
    store_dir: Path,
    known_agents: dict[str, str],
) -> None:
    lock = load_lock(lock_path)

    # Find skill in lock
    old_skill = None
    for s in lock.skills:
        if s.name == skill_name:
            old_skill = s
            break

    if old_skill is None:
        click.echo(f"Skill '{skill_name}' is not installed.")
        return

    repo_dir_name = repo_url_to_dirname(old_skill.repo)
    repo_path = store_dir / repo_dir_name

    old_commit = old_skill.commit

    # Pull latest
    click.echo(f"Pulling {old_skill.repo}...")
    clone_or_pull(old_skill.repo, repo_path)
    new_commit = get_head_commit(repo_path)

    if old_commit == new_commit:
        click.echo(f"  Already up to date ({old_commit[:8]})")
        return

    # Show changes
    log = get_log_between(repo_path, old_commit, new_commit)
    click.echo(f"  Updated {old_commit[:8]} -> {new_commit[:8]}")
    if log:
        for line in log.splitlines():
            click.echo(f"    {line}")

    # Re-detect and re-link
    detected = detect_skills(repo_path)
    configs = load_config(config_path)
    repo_config = None
    for c in configs:
        if c.repo == old_skill.repo:
            repo_config = c
            break

    target_agents = resolve_target_agents(
        repo_config.agents if repo_config else None,
        known_agents,
    )

    # Update all skills from this repo in the lock
    for i, locked_skill in enumerate(lock.skills):
        if locked_skill.repo != old_skill.repo:
            continue
        # Find matching detected skill
        matching = [d for d in detected if d.name == locked_skill.name]
        if not matching:
            continue
        skill = matching[0]
        linked_paths = []
        for agent_name, agent_dir in target_agents.items():
            link = link_skill(skill.path, skill.name, agent_dir)
            linked_paths.append(str(link))

        lock.skills[i] = InstalledSkill(
            name=skill.name,
            repo=locked_skill.repo,
            commit=new_commit,
            skill_path=skill.relative_path,
            linked_to=linked_paths,
        )

    save_lock(lock, lock_path)
    click.echo(f"Lock file updated.")
```

**Step 2: Wire up in cli.py**

Replace the `update` placeholder:
```python
@cli.command()
@click.argument("skill_name")
def update(skill_name: str):
    """Update a specific skill."""
    from skm.commands.update import run_update
    agents = {name: str(path) for name, path in _expand_agents().items()}
    run_update(
        skill_name=skill_name,
        config_path=CONFIG_PATH,
        lock_path=LOCK_PATH,
        store_dir=STORE_DIR,
        known_agents=agents,
    )
```

**Step 3: Commit**

```bash
git add src/skm/commands/update.py src/skm/cli.py
git commit -m "feat: implement update command"
```

---

## Task 12: Final CLI Integration & Manual Test

**Step 1: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS

**Step 2: Manual smoke test**

```bash
# Create config dir
mkdir -p ~/.config/skm

# Copy example config (or create a test one)
cp skills.example.yaml ~/.config/skm/skills.yaml

# Run install
uv run skm install

# List installed skills
uv run skm list

# Check for updates
uv run skm check-updates
```

**Step 3: Final commit**

```bash
git add -A
git commit -m "chore: finalize skm v0.1.0"
```

---

## Summary

| Task | Component | Key Files |
|------|-----------|-----------|
| 1 | Project scaffolding | `pyproject.toml`, `cli.py` |
| 2 | Data models | `types.py` |
| 3 | Config loading | `config.py` |
| 4 | Lock file I/O | `lock.py` |
| 5 | Skill detection | `detect.py` |
| 6 | Git operations | `git.py` |
| 7 | Linking logic | `linker.py` |
| 8 | Install command | `commands/install.py` |
| 9 | List command | `commands/list_cmd.py` |
| 10 | Check-updates command | `commands/check_updates.py` |
| 11 | Update command | `commands/update.py` |
| 12 | Integration & smoke test | - |
