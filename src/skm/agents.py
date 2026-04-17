import os
from pathlib import Path

from skm.types import AgentSpec, GlobalAgentsConfig


DEFAULT_AGENT_SPECS: dict[str, AgentSpec] = {
    # Temporary workaround for openclaw loading: keep standard materialized too.
    'standard': AgentSpec(path='~/.agents/skills', install_mode='materialize'),
    'claude': AgentSpec(path='~/.claude/skills', parent_env_var='CLAUDE_CONFIG_DIR'),
    'codex': AgentSpec(path='~/.codex/skills', parent_env_var='CODEX_HOME'),
    'openclaw': AgentSpec(path='~/.openclaw/skills', install_mode='materialize'),
    'pi': AgentSpec(path='~/.pi/agent/skills', parent_env_var='PI_CODING_AGENT_DIR'),
}


def get_all_agent_specs(config_agents: GlobalAgentsConfig | None) -> dict[str, AgentSpec]:
    specs = {name: spec.model_copy(deep=True) for name, spec in DEFAULT_AGENT_SPECS.items()}

    overrides = config_agents.override if config_agents else None
    if overrides is None:
        return specs

    for name, override in overrides.items():
        if name not in specs:
            raise ValueError(f"Unknown agent '{name}' in agents.override")

        spec = specs[name].model_copy(deep=True)
        if override.path is not None:
            spec.path = override.path
            spec.parent_env_var = None
        if override.install_mode is not None:
            spec.install_mode = override.install_mode
        specs[name] = spec

    return specs


def validate_agent_names(names: list[str], agent_specs: dict[str, AgentSpec], field_name: str) -> None:
    unknown = [name for name in names if name not in agent_specs]
    if unknown:
        raise ValueError(f'Unknown agents in {field_name}: {unknown}. Known agents: {list(agent_specs.keys())}')


def get_default_agent_names(config_agents: GlobalAgentsConfig | None, agent_specs: dict[str, AgentSpec]) -> list[str]:
    default_agents = config_agents.default if config_agents else None
    if default_agents is None:
        return list(agent_specs.keys())

    validate_agent_names(default_agents, agent_specs, 'agents.default')
    return list(default_agents)


def _resolve_agent_path(name: str, spec: AgentSpec, agents_dir: str | None) -> str:
    if agents_dir:
        return str((Path(agents_dir).expanduser() / name))

    if spec.parent_env_var:
        env_value = os.environ.get(spec.parent_env_var)
        if env_value:
            return str(Path(env_value).expanduser() / 'skills')

    return str(Path(spec.path).expanduser())


def resolve_agent_specs(
    config_agents: GlobalAgentsConfig | None,
    agents_dir: str | None = None,
    selected_names: list[str] | None = None,
) -> dict[str, AgentSpec]:
    agent_specs = get_all_agent_specs(config_agents)
    if selected_names is None:
        names = get_default_agent_names(config_agents, agent_specs)
    else:
        names = selected_names
        validate_agent_names(names, agent_specs, 'selected agents')

    resolved: dict[str, AgentSpec] = {}
    for name in names:
        spec = agent_specs[name].model_copy(deep=True)
        spec.path = _resolve_agent_path(name, spec, agents_dir)
        resolved[name] = spec

    return resolved
