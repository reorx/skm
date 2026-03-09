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
