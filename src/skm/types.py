import os
from pathlib import Path, PurePosixPath
from pydantic import BaseModel, field_validator, model_validator


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
    agents: AgentsConfig | None = None

    @model_validator(mode='after')
    def check_source(self):
        if self.repo and self.local_path:
            raise ValueError("Cannot specify both 'repo' and 'local_path'; exactly one must be set")
        if not self.repo and not self.local_path:
            raise ValueError("Must specify exactly one of 'repo' or 'local_path'")
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


class DefaultAgentsConfig(BaseModel):
    default: list[str] | None = None

    @field_validator('default')
    @classmethod
    def check_known_agents(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            unknown = [a for a in v if a not in KNOWN_AGENTS]
            if unknown:
                raise ValueError(f'Unknown agents: {unknown}. Known agents: {list(KNOWN_AGENTS.keys())}')
        return v


class SkmConfig(BaseModel):
    packages: list[SkillRepoConfig]
    agents: DefaultAgentsConfig | None = None


# --- Lock file models ---


class InstalledSkill(BaseModel):
    name: str
    repo: str | None = None
    local_path: str | None = None
    commit: str | None = None
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

_KNOWN_AGENTS_DEFAULTS: dict[str, str] = {
    'standard': '~/.agents/skills',
    'claude': '~/.claude/skills',
    'codex': '~/.codex/skills',
    'openclaw': '~/.openclaw/skills',
    'pi': '~/.pi/agent/skills',
}

# Env vars that override per-agent skill directory base.
# If set, the agent's skill dir becomes $ENV_VAR/skills.
_AGENT_ENV_OVERRIDES: dict[str, str] = {
    'claude': 'CLAUDE_CONFIG_DIR',
    'codex': 'CODEX_HOME',
}


def _get_known_agents() -> dict[str, str]:
    """Return known agents dict, applying env-var overrides where set."""

    result = dict(_KNOWN_AGENTS_DEFAULTS)
    for agent, env_var in _AGENT_ENV_OVERRIDES.items():
        val = os.environ.get(env_var)
        if val:
            result[agent] = str(Path(val).expanduser() / 'skills')
    return result


KNOWN_AGENTS: dict[str, str] = _get_known_agents()

# Per-agent install options. Agents not listed here use defaults (symlink).
# Options:
#   use_hardlink: bool - use hard links instead of symlinks for skill installation
AGENT_OPTIONS: dict[str, dict] = {
    'standard': {
        'use_hardlink': True,
    },
    'openclaw': {
        'use_hardlink': True,
    },
}

CONFIG_DIR = Path('~/.config/skm').expanduser()
CONFIG_PATH = CONFIG_DIR / 'skills.yaml'
LOCK_PATH = CONFIG_DIR / 'skills-lock.yaml'
STORE_DIR = Path('~/.local/share/skm/skills').expanduser()
