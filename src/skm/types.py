from pathlib import Path
from typing import Literal

from pydantic import BaseModel, model_validator


# --- Config models (parsed from skills.yaml) ---


class AgentsConfig(BaseModel):
    includes: list[str] | None = None
    excludes: list[str] | None = None

    @model_validator(mode='after')
    def check_mutual_exclusion(self):
        if self.includes is not None and self.excludes is not None:
            raise ValueError("Cannot specify both 'includes' and 'excludes' in agents config")
        return self


class SkillRepoConfig(BaseModel):
    repo: str | None = None
    local_path: str | None = None
    skills: list[str] | None = None
    agents: AgentsConfig | None = None

    @model_validator(mode='after')
    def check_source(self):
        if self.repo and self.local_path:
            raise ValueError("Cannot specify both 'repo' and 'local_path'; exactly one must be set")
        if not self.repo and not self.local_path:
            raise ValueError("Must specify exactly one of 'repo' or 'local_path'")
        return self

    @property
    def is_local(self) -> bool:
        return self.local_path is not None

    @property
    def source_key(self) -> str:
        if self.local_path:
            return str(Path(self.local_path).expanduser())
        return self.repo


AgentInstallMode = Literal['symlink', 'materialize']


class AgentSpec(BaseModel):
    path: str
    parent_env_var: str | None = None
    install_mode: AgentInstallMode = 'symlink'


class AgentOverride(BaseModel):
    path: str | None = None
    install_mode: AgentInstallMode | None = None


class GlobalAgentsConfig(BaseModel):
    default: list[str] | None = None
    override: dict[str, AgentOverride] | None = None


class SkmConfig(BaseModel):
    packages: list[SkillRepoConfig]
    agents: GlobalAgentsConfig | None = None


# --- Lock file models ---


class InstalledSkill(BaseModel):
    name: str
    repo: str | None = None
    local_path: str | None = None
    commit: str | None = None
    skill_path: str  # relative path within repo to the skill dir
    linked_to: list[str]  # list of managed install paths


class LockFile(BaseModel):
    skills: list[InstalledSkill] = []


# --- Runtime models ---


class DetectedSkill(BaseModel):
    """A skill detected by walking a cloned repo."""

    name: str  # from SKILL.md frontmatter
    path: Path  # absolute path to the skill directory
    relative_path: str  # relative path within the repo


# --- Constants ---

CONFIG_DIR = Path('~/.config/skm').expanduser()
CONFIG_PATH = CONFIG_DIR / 'skills.yaml'
LOCK_PATH = CONFIG_DIR / 'skills-lock.yaml'
STORE_DIR = Path('~/.local/share/skm/skills').expanduser()
