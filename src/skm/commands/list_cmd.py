from pathlib import Path

import click

from skm.lock import load_lock
from skm.types import InstalledSkill
from skm.utils import compact_path


def run_list(lock_path: Path) -> None:
    lock = load_lock(lock_path)

    if not lock.skills:
        click.echo("No skills installed.")
        return

    for skill in lock.skills:
        click.echo(f"{skill.name}  ({skill.repo})")
        click.echo(f"  commit: {skill.commit[:8]}")
        for link in skill.linked_to:
            click.echo(f"  -> {compact_path(link)}")


def run_list_all(lock_path: Path, known_agents: dict[str, str]) -> None:
    lock = load_lock(lock_path)

    # Build a set of managed symlink paths for quick lookup
    # Also build a map: symlink_path -> InstalledSkill for metadata
    managed_links: dict[str, InstalledSkill] = {}
    for skill in lock.skills:
        for link in skill.linked_to:
            managed_links[link] = skill

    for agent_name, agent_dir in sorted(known_agents.items()):
        agent_path = Path(agent_dir)
        if not agent_path.is_dir():
            continue

        entries = sorted(agent_path.iterdir(), key=lambda p: p.name)
        if not entries:
            continue

        click.echo(f"[{agent_name}] {compact_path(agent_dir)}")
        for entry in entries:
            link_str = compact_path(str(entry))
            if link_str in managed_links:
                skill = managed_links[link_str]
                marker = click.style("skm", fg="green")
                click.echo(f"  {entry.name}  ({marker}, {skill.repo})")
            else:
                click.echo(f"  {entry.name}")
        click.echo()
