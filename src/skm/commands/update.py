import shutil
from pathlib import Path

import click

from skm.detect import detect_skills
from skm.git import clone_or_pull, get_head_commit, get_log_between, repo_url_to_dirname
from skm.linker import link_skill, resolve_target_agents
from skm.lock import load_lock, save_lock
from skm.types import InstalledSkill, SkmConfig
from skm.utils import compact_path


def run_update(
    skill_names: tuple[str, ...],
    update_all: bool,
    config: SkmConfig,
    lock_path: Path,
    store_dir: Path,
    known_agents: dict[str, str],
) -> None:
    lock = load_lock(lock_path)

    # Determine which repos to update
    if update_all:
        repos_to_update: dict[str, list[InstalledSkill]] = {}
        for s in lock.skills:
            if s.repo is None:
                continue
            repos_to_update.setdefault(s.repo, []).append(s)
    else:
        # Find requested skills and collect their repos
        repos_to_update = {}
        for name in skill_names:
            found = None
            for s in lock.skills:
                if s.name == name:
                    found = s
                    break
            if found is None:
                click.echo(f"Skill '{name}' is not installed.")
                raise SystemExit(1)
            if found.repo is None:
                click.echo(f"Skill '{name}' is from a local path, skipping update.")
                continue
            repos_to_update.setdefault(found.repo, []).append(found)

    if not repos_to_update:
        click.echo("Nothing to update.")
        return

    for repo_url, skills in repos_to_update.items():
        _update_repo(repo_url, config, lock, store_dir, known_agents)

    save_lock(lock, lock_path)
    click.echo('Lock file updated.')


def _update_repo(
    repo_url: str,
    config: SkmConfig,
    lock,
    store_dir: Path,
    known_agents: dict[str, str],
) -> None:
    repo_dir_name = repo_url_to_dirname(repo_url)
    repo_path = store_dir / repo_dir_name

    # Get old commit from any skill in this repo
    old_commit = None
    for s in lock.skills:
        if s.repo == repo_url:
            old_commit = s.commit
            break

    # Pull latest
    click.echo(f'Pulling {click.style(repo_url, fg="cyan")}...')
    clone_or_pull(repo_url, repo_path)
    new_commit = get_head_commit(repo_path)

    if old_commit == new_commit:
        click.echo(click.style(f'  ✔ Already up to date ({old_commit[:8]})', fg='green'))
        return

    # Show changes
    log = get_log_between(repo_path, old_commit, new_commit)
    click.echo(f'  Updated {click.style(old_commit[:8], fg="red")} → {click.style(new_commit[:8], fg="green")}')
    if log:
        for line in log.splitlines():
            click.echo(click.style(f'    {line}', dim=True))

    repo_config = None
    for c in config.packages:
        if c.repo == repo_url:
            repo_config = c
            break

    if repo_config is None:
        click.echo(f"  Error: repo '{repo_url}' not found in config. Cannot determine target agents.")
        raise SystemExit(1)

    # Re-detect and re-link
    try:
        detected = detect_skills(repo_path, repo_config.skills_dir)
    except ValueError as e:
        raise click.ClickException(str(e))

    target_agents = resolve_target_agents(
        repo_config.agents,
        known_agents,
    )

    # Update all skills from this repo in the lock
    stale_indices = []
    for i, locked_skill in enumerate(lock.skills):
        if locked_skill.repo != repo_url:
            continue
        # Find matching detected skill
        matching = [d for d in detected if d.name == locked_skill.name]
        if not matching:
            click.echo(
                click.style(f"  Warning: skill '{locked_skill.name}' no longer found in repo, removing", fg='red')
            )
            for link_path in locked_skill.linked_to:
                p = Path(link_path).expanduser()
                if p.is_symlink():
                    p.unlink()
                elif p.is_dir():
                    shutil.rmtree(p)
            stale_indices.append(i)
            continue
        skill = matching[0]
        linked_paths = []
        for agent_name, agent_dir in target_agents.items():
            link, _status = link_skill(skill.path, skill.name, agent_dir, force=True, agent_name=agent_name)
            linked_paths.append(compact_path(str(link)))

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
