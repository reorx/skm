from typing import Literal
from pathlib import Path, PurePosixPath
from pydantic import BaseModel, ConfigDict, field_validator, model_validator


AgentInstallMode = Literal['symlink', 'materialize']


class AgentSpec(BaseModel):
    path: str
    env_var: str | None = None
    install_mode: AgentInstallMode = 'symlink'


class ResolvedAgent(BaseModel):
    path: str
    install_mode: AgentInstallMode = 'symlink'


class AgentOverride(BaseModel):
    model_config = ConfigDict(extra='forbid')
    path: str | None = None
    install_mode: AgentInstallMode | None = None

    @field_validator('path')
    @classmethod
    def check_path(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("'path' cannot be empty")
        return value


# OpenClaw skips symlinks outside its skill roots. Standard stays symlink-based:
# Codex and Hermes follow those links, and source edits can replace hardlink inodes.
BUILTIN_AGENTS: dict[str, AgentSpec] = {
    'standard': AgentSpec(path='~/.agents/skills'),
    'claude': AgentSpec(path='~/.claude/skills', env_var='CLAUDE_CONFIG_DIR'),
    'codex': AgentSpec(path='~/.codex/skills', env_var='CODEX_HOME'),
    'openclaw': AgentSpec(path='~/.openclaw/skills', install_mode='materialize'),
    'pi': AgentSpec(path='~/.pi/agent/skills', env_var='PI_CODING_AGENT_DIR'),
}


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
    clone_strategy: str | None = None
    skills_dir: str | None = None
    skills: list[str] | None = None
    skills_excludes: list[str] | None = None
    agents: AgentsConfig | None = None

    @model_validator(mode='after')
    def check_source(self):
        if self.repo and self.local_path:
            raise ValueError("Cannot specify both 'repo' and 'local_path'; exactly one must be set")
        if not self.repo and not self.local_path:
            raise ValueError("Must specify exactly one of 'repo' or 'local_path'")
        return self

    @model_validator(mode='after')
    def check_skills_mutual_exclusion(self):
        if self.skills is not None and self.skills_excludes is not None:
            raise ValueError("Cannot specify both 'skills' and 'skills_excludes' in a package")
        return self

    @field_validator('skills_dir')
    @classmethod
    def check_skills_dir(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not v.strip():
            raise ValueError("'skills_dir' cannot be empty")
        path = PurePosixPath(v)
        if path.is_absolute() or '..' in path.parts:
            raise ValueError("'skills_dir' must be a relative path within the package")
        return v.rstrip('/')

    @property
    def is_local(self) -> bool:
        return self.local_path is not None

    @property
    def source_key(self) -> str:
        if self.local_path:
            return str(Path(self.local_path).expanduser())
        return self.repo


class GlobalAgentsConfig(BaseModel):
    default: list[str] | None = None
    override: dict[str, AgentOverride] | None = None

    @field_validator('default', 'override')
    @classmethod
    def check_known_agents(cls, v):
        if v is not None:
            unknown = [a for a in v if a not in BUILTIN_AGENTS]
            if unknown:
                raise ValueError(f'Unknown agents: {unknown}. Known agents: {list(BUILTIN_AGENTS.keys())}')
        return v


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
    linked_to: list[str]  # installation paths (home compacted to ~)


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
