import shutil
from pathlib import Path

import click

from skm.detect import detect_skills
from skm.git import clone_or_pull, get_head_commit, repo_url_to_dirname
from skm.linker import link_skill, unlink_skill, resolve_target_agents
from skm.lock import load_lock, save_lock
from skm.types import InstalledSkill, LockFile, SkillRepoConfig, SkmConfig
from skm.utils import compact_path


def _confirm_override(message: str) -> bool:
    """Prompt user with a y/n question, returns on single keypress."""
    click.echo(f'{message} [y/N] ', nl=False)
    c = click.getchar()
    click.echo()  # newline after keypress
    return c in ('y', 'Y')


def run_install(
    config: SkmConfig,
    lock_path: Path,
    store_dir: Path,
    known_agents: dict[str, str],
    force: bool = False,
) -> None:
    lock = load_lock(lock_path)
    new_lock_skills: list[InstalledSkill] = []

    # Track which skills are configured (for removal detection)
    # Key: (skill_name, source_key)
    configured_skill_keys: set[tuple[str, str]] = set()

    for repo_config in config.packages:
        if repo_config.is_local:
            _install_local(repo_config, new_lock_skills, configured_skill_keys, known_agents, force)
        else:
            _install_repo(repo_config, store_dir, new_lock_skills, configured_skill_keys, known_agents, force)

        click.echo()

    # Remove skills that were in old lock but no longer in config
    for old_skill in lock.skills:
        old_source = old_skill.repo or old_skill.local_path or ''
        if (old_skill.name, old_source) not in configured_skill_keys:
            click.echo(f'  Removing {old_skill.name} (no longer in config)')
            for link_path in old_skill.linked_to:
                p = Path(link_path).expanduser()
                if p.is_symlink():
                    p.unlink()
                elif p.is_dir():
                    shutil.rmtree(p)

    new_lock = LockFile(skills=new_lock_skills)
    save_lock(new_lock, lock_path)
    click.echo(f'Lock file updated: {lock_path}')


def _install_local(repo_config, new_lock_skills, configured_skill_keys, known_agents, force=False):
    local_path = Path(repo_config.local_path).expanduser()
    click.echo(click.style(f'Using local path {compact_path(str(local_path))}', fg='blue', bold=True))

    detected = detect_skills(local_path)
    click.echo(click.style(f'  Found skills: {", ".join(s.name for s in detected) or "(none)"}', dim=True))
    target_agents = resolve_target_agents(repo_config.agents, known_agents)

    if repo_config.skills is not None:
        requested = set(repo_config.skills)
        skills_to_install = [s for s in detected if s.name in requested]
        missing = requested - {s.name for s in skills_to_install}
        if missing:
            click.echo(click.style(f'  Warning: skills not found: {missing}', fg='red'))
    else:
        skills_to_install = detected

    source_key = repo_config.source_key
    for skill in skills_to_install:
        configured_skill_keys.add((skill.name, compact_path(str(local_path))))
        linked_paths = []
        click.echo(click.style(f'  Install skill {skill.name}', fg='yellow'))

        for agent_name, agent_dir in target_agents.items():
            try:
                link = link_skill(skill.path, skill.name, agent_dir, agent_name=agent_name)
            except FileExistsError as e:
                if force or _confirm_override(f'  {e}. Override?'):
                    click.echo(click.style(f'  Overriding existing skill {skill.name}', fg='magenta'))
                    link = link_skill(skill.path, skill.name, agent_dir, force=True, agent_name=agent_name)
                else:
                    click.echo(click.style(f'  Skipped {skill.name} for [{agent_name}]', dim=True))
                    continue
            linked_paths.append(compact_path(str(link)))
            click.echo(f'  Linked {skill.name} -> [{agent_name}] {compact_path(str(link))}')

        new_lock_skills.append(
            InstalledSkill(
                name=skill.name,
                local_path=compact_path(str(local_path)),
                commit=None,
                skill_path=skill.relative_path,
                linked_to=linked_paths,
            )
        )


def _install_repo(repo_config, store_dir, new_lock_skills, configured_skill_keys, known_agents, force=False):
    repo_dir_name = repo_url_to_dirname(repo_config.repo)
    repo_path = store_dir / repo_dir_name

    if repo_path.exists() and (repo_path / '.git').exists():
        click.echo(click.style(f'Using existing {repo_config.repo}', fg='blue', bold=True))
    else:
        click.echo(click.style(f'Cloning {repo_config.repo}...', fg='blue', bold=True))
        clone_or_pull(repo_config.repo, repo_path)

    commit = get_head_commit(repo_path)
    detected = detect_skills(repo_path)
    click.echo(click.style(f'  Found skills: {", ".join(s.name for s in detected) or "(none)"}', dim=True))
    target_agents = resolve_target_agents(repo_config.agents, known_agents)

    if repo_config.skills is not None:
        requested = set(repo_config.skills)
        skills_to_install = [s for s in detected if s.name in requested]
        missing = requested - {s.name for s in skills_to_install}
        if missing:
            click.echo(click.style(f'  Warning: skills not found in repo: {missing}', fg='red'))
    else:
        skills_to_install = detected

    for skill in skills_to_install:
        configured_skill_keys.add((skill.name, repo_config.repo))
        linked_paths = []
        click.echo(click.style(f'  Install skill {skill.name}', fg='yellow'))

        for agent_name, agent_dir in target_agents.items():
            try:
                link = link_skill(skill.path, skill.name, agent_dir, agent_name=agent_name)
            except FileExistsError as e:
                if force or _confirm_override(f'  {e}. Override?'):
                    click.echo(click.style(f'  Overriding existing skill {skill.name}', fg='magenta'))
                    link = link_skill(skill.path, skill.name, agent_dir, force=True, agent_name=agent_name)
                else:
                    click.echo(click.style(f'  Skipped {skill.name} for [{agent_name}]', dim=True))
                    continue
            linked_paths.append(compact_path(str(link)))
            click.echo(f'  Linked {skill.name} -> [{agent_name}] {compact_path(str(link))}')

        new_lock_skills.append(
            InstalledSkill(
                name=skill.name,
                repo=repo_config.repo,
                commit=commit,
                skill_path=skill.relative_path,
                linked_to=linked_paths,
            )
        )


def run_install_package(
    repo_config: SkillRepoConfig,
    lock_path: Path,
    store_dir: Path,
    known_agents: dict[str, str],
    force: bool = False,
) -> None:
    """Install a single package and merge results into the existing lock file."""
    lock = load_lock(lock_path)
    new_lock_skills: list[InstalledSkill] = []
    configured_skill_keys: set[tuple[str, str]] = set()

    if repo_config.is_local:
        _install_local(repo_config, new_lock_skills, configured_skill_keys, known_agents, force)
    else:
        _install_repo(repo_config, store_dir, new_lock_skills, configured_skill_keys, known_agents, force)

    click.echo()

    # Merge: keep existing lock entries from other sources, replace entries from this source
    source_key = repo_config.source_key
    merged_skills = []
    for existing in lock.skills:
        existing_source = existing.repo or existing.local_path or ''
        # Keep entries not from this source
        if existing_source != source_key:
            # Also check expanded local_path
            if not (
                repo_config.is_local
                and existing.local_path
                and str(Path(existing.local_path).expanduser()) == str(Path(source_key).expanduser())
            ):
                merged_skills.append(existing)
    merged_skills.extend(new_lock_skills)

    new_lock = LockFile(skills=merged_skills)
    save_lock(new_lock, lock_path)
    click.echo(f'Lock file updated: {lock_path}')
