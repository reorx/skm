from pathlib import Path

import click

from skm.lock import load_lock
from skm.types import AgentSpec, InstalledSkill
from skm.utils import compact_path


def _agent_name_from_link(link: str, known_agents: dict[str, AgentSpec]) -> str | None:
    """Derive the agent name from an install path by matching against known agents."""
    expanded_parent = str(Path(link).expanduser().parent)
    for name, spec in known_agents.items():
        expanded = str(Path(spec.path).expanduser())
        if expanded_parent == expanded:
            return name
    return None


def _format_skill(skill: InstalledSkill, known_agents: dict[str, AgentSpec], verbose: bool) -> None:
    """Print a single skill entry."""
    click.echo(skill.name)

    gray = dict(fg='bright_black')
    source = skill.repo or skill.local_path or 'unknown'
    click.echo(click.style(f'  repo: {source}', **gray))
    if skill.commit:
        click.echo(click.style(f'  commit: {skill.commit[:8]}', **gray))

    # Derive agent names from linked paths
    agents = []
    for link in skill.linked_to:
        agent = _agent_name_from_link(link, known_agents)
        if agent:
            agents.append(agent)
    if agents:
        click.echo(click.style(f'  agents: {", ".join(sorted(agents))}', **gray))

    if verbose:
        click.echo(click.style(f'  skill_path: {skill.skill_path}', **gray))
        for link in skill.linked_to:
            click.echo(click.style(f'  -> {compact_path(link)}', **gray))


def run_list(
    lock_path: Path,
    known_agents: dict[str, AgentSpec],
    verbose: bool = False,
    skill_name: str | None = None,
) -> None:
    lock = load_lock(lock_path)

    if not lock.skills:
        click.echo('No skills installed.')
        return

    if skill_name:
        matched = [s for s in lock.skills if s.name == skill_name]
        if not matched:
            click.echo(f"Skill '{skill_name}' not found.")
            return
        for skill in matched:
            _format_skill(skill, known_agents, verbose)
        return

    for i, skill in enumerate(lock.skills):
        if i > 0:
            click.echo()
        _format_skill(skill, known_agents, verbose)

    click.echo()
    click.echo(f'Total skills: {len(lock.skills)}')


def run_list_all(lock_path: Path, known_agents: dict[str, AgentSpec]) -> None:
    lock = load_lock(lock_path)

    # Build a map of managed install paths for quick lookup.
    managed_links: dict[str, InstalledSkill] = {}
    for skill in lock.skills:
        for link in skill.linked_to:
            managed_links[link] = skill

    for agent_name, agent_spec in sorted(known_agents.items()):
        agent_path = Path(agent_spec.path)
        if not agent_path.is_dir():
            continue

        entries = sorted(agent_path.iterdir(), key=lambda p: p.name)
        if not entries:
            continue

        click.echo(f'[{agent_name}] {compact_path(agent_spec.path)}')
        for entry in entries:
            link_str = compact_path(str(entry))
            if link_str in managed_links:
                skill = managed_links[link_str]
                marker = click.style('skm', fg='green')
                source = skill.repo or skill.local_path or 'unknown'
                click.echo(f'  {entry.name}  ({marker}, {source})')
            else:
                click.echo(f'  {entry.name}')
        click.echo()
