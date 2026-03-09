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
