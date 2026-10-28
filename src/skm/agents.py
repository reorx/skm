"""Resolve agent paths and installation modes once per command invocation."""
import os
from pathlib import Path

from skm.types import BUILTIN_AGENTS, AgentOverride, GlobalAgentsConfig, ResolvedAgent


def resolve_agents(
    agents_config: GlobalAgentsConfig | None,
    agents_dir: str | None = None,
    default_only: bool = True,
) -> dict[str, ResolvedAgent]:
    defaults = agents_config.default if agents_config else None
    overrides = (agents_config.override or {}) if agents_config else {}
    result = {}
    for name, spec in BUILTIN_AGENTS.items():
        if default_only and defaults is not None and name not in defaults:
            continue
        override = overrides.get(name) or AgentOverride()
        env_path = os.environ.get(spec.env_var) if spec.env_var else None
        if agents_dir is not None:
            path = Path(agents_dir).expanduser() / name
        elif override.path is not None:
            path = Path(override.path).expanduser()
        elif env_path:
            path = Path(env_path).expanduser() / 'skills'
        else:
            path = Path(spec.path).expanduser()
        result[name] = ResolvedAgent(path=str(path), install_mode=override.install_mode or spec.install_mode)
    return result
