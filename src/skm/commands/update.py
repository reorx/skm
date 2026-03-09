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
        raise SystemExit(1)

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

    if repo_config is None:
        click.echo(f"  Error: repo '{old_skill.repo}' not found in config. Cannot determine target agents.")
        raise SystemExit(1)

    target_agents = resolve_target_agents(
        repo_config.agents,
        known_agents,
    )

    # Update all skills from this repo in the lock
    stale_indices = []
    for i, locked_skill in enumerate(lock.skills):
        if locked_skill.repo != old_skill.repo:
            continue
        # Find matching detected skill
        matching = [d for d in detected if d.name == locked_skill.name]
        if not matching:
            click.echo(f"  Warning: skill '{locked_skill.name}' no longer found in repo, removing")
            for link_path in locked_skill.linked_to:
                p = Path(link_path)
                if p.is_symlink():
                    p.unlink()
            stale_indices.append(i)
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

    # Remove stale entries (iterate in reverse to preserve indices)
    for i in reversed(stale_indices):
        lock.skills.pop(i)

    save_lock(lock, lock_path)
    click.echo(f"Lock file updated.")
