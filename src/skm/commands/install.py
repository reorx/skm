import shutil
import sys
from pathlib import Path

import click

from skm.detect import detect_skills
from skm.git import clone_or_pull, get_head_commit, repo_url_to_dirname
from skm.linker import link_skill, unlink_skill, resolve_target_agents
from skm.lock import load_lock, save_lock
from skm.types import InstalledSkill, LockFile, SkillRepoConfig, SkmConfig
from skm.utils import compact_path


STATUS_COLORS = {
    'new': 'green',
    'exists': None,  # dim
    'replaced': 'magenta',
}


def _progress(msg: str) -> None:
    """Write a single refreshing progress line to stderr."""
    sys.stderr.write(f'\r\033[K{msg}')
    sys.stderr.flush()


def _clear_progress() -> None:
    """Clear the progress line."""
    sys.stderr.write('\r\033[K')
    sys.stderr.flush()


def _confirm_override(message: str) -> bool:
    """Prompt user with a y/n question, returns on single keypress."""
    _clear_progress()
    click.echo(f'{message} [y/N] ', nl=False)
    c = click.getchar()
    click.echo()  # newline after keypress
    return c in ('y', 'Y')


def _format_link_status(status: str) -> str:
    """Format a status annotation for verbose mode."""
    color = STATUS_COLORS.get(status)
    text = f'({status})'
    if color:
        return click.style(text, fg=color)
    return click.style(text, dim=True)


def _dedup_skills(skills, source_label, verbose=False):
    """Deduplicate skills by name, warning about duplicates."""
    seen = {}
    result = []
    for skill in skills:
        if skill.name in seen:
            prev = seen[skill.name]
            if verbose:
                click.echo(
                    click.style(
                        f'  Warning: duplicate skill name "{skill.name}" '
                        f'(from {skill.relative_path}, already seen from {prev.relative_path}), skipping',
                        fg='red',
                    )
                )
            else:
                _clear_progress()
                click.echo(
                    click.style(
                        f'  Warning: duplicate skill name "{skill.name}" '
                        f'(from {skill.relative_path}, already seen from {prev.relative_path}), skipping',
                        fg='red',
                    )
                )
            continue
        seen[skill.name] = skill
        result.append(skill)
    return result


def run_install(
    config: SkmConfig,
    lock_path: Path,
    store_dir: Path,
    known_agents: dict[str, str],
    force: bool = False,
    verbose: bool = False,
) -> None:
    lock = load_lock(lock_path)
    new_lock_skills: list[InstalledSkill] = []

    # Track which skills are configured (for removal detection)
    # Key: (skill_name, source_key)
    configured_skill_keys: set[tuple[str, str]] = set()

    added_count = 0
    all_deferred_lines: list[str] = []

    for repo_config in config.packages:
        if repo_config.is_local:
            count, lines = _install_local(
                repo_config, new_lock_skills, configured_skill_keys, known_agents, force, verbose
            )
        else:
            count, lines = _install_repo(
                repo_config, store_dir, new_lock_skills, configured_skill_keys, known_agents, force, verbose
            )

        added_count += count
        all_deferred_lines.extend(lines)

        if verbose:
            click.echo()

    if not verbose:
        _clear_progress()
        # Print deferred output for changed skills
        for line in all_deferred_lines:
            click.echo(line)

    # Build set of all new linked paths for comparison
    new_linked_paths: set[str] = set()
    for skill in new_lock_skills:
        for lp in skill.linked_to:
            new_linked_paths.add(lp)

    # Remove stale links: any old linked_to path not present in new state
    stale_header_printed = False
    removed_count = 0
    for old_skill in lock.skills:
        old_source = old_skill.repo or old_skill.local_path or ''
        skill_still_configured = (old_skill.name, old_source) in configured_skill_keys

        for link_path_str in old_skill.linked_to:
            if link_path_str not in new_linked_paths:
                p = Path(link_path_str).expanduser()
                if skill_still_configured:
                    reason = 'agent config changed'
                else:
                    reason = 'no longer in config'
                if p.is_symlink() or p.is_dir():
                    if not stale_header_printed:
                        click.echo()
                        click.echo(click.style('Removing stale links', fg='red', bold=True))
                        stale_header_printed = True
                    if p.is_symlink():
                        p.unlink()
                    else:
                        shutil.rmtree(p)
                    click.echo(
                        click.style(f'  {compact_path(link_path_str)} for {old_skill.name} ({reason})', fg='red')
                    )
                    removed_count += 1

    # Summary line
    if not verbose:
        if added_count == 0 and removed_count == 0:
            click.echo('up to date')
        else:
            parts = []
            if added_count > 0:
                parts.append(f'added {added_count} skill{"s" if added_count != 1 else ""}')
            if removed_count > 0:
                parts.append(f'removed {removed_count} skill{"s" if removed_count != 1 else ""}')
            click.echo()
            click.echo(', '.join(parts))

    new_lock = LockFile(skills=new_lock_skills)
    save_lock(new_lock, lock_path)
    click.echo(f'Lock file updated: {lock_path}')


def _install_local(repo_config, new_lock_skills, configured_skill_keys, known_agents, force=False, verbose=False):
    """Install skills from a local path. Returns (added_count, deferred_lines)."""
    local_path = Path(repo_config.local_path).expanduser()
    source_label = compact_path(str(local_path))

    if verbose:
        click.echo(click.style(f'Using local path {source_label}', fg='blue', bold=True))

    try:
        detected = detect_skills(local_path, repo_config.skills_dir)
    except ValueError as e:
        raise click.ClickException(str(e))
    if verbose:
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

    skills_to_install = _dedup_skills(skills_to_install, source_label, verbose)

    added_count = 0
    deferred_lines: list[str] = []

    for skill in skills_to_install:
        configured_skill_keys.add((skill.name, compact_path(str(local_path))))
        linked_paths = []
        skill_changed = False
        skill_lines: list[str] = []

        if not verbose:
            _progress(f'  {skill.name}')

        if verbose:
            click.echo(click.style(f'  Install skill {skill.name}', fg='yellow'))

        for agent_name, agent_dir in target_agents.items():
            try:
                link, status = link_skill(skill.path, skill.name, agent_dir, agent_name=agent_name)
            except FileExistsError as e:
                if force or _confirm_override(f'  {e}. Override?'):
                    if verbose:
                        click.echo(click.style(f'  Overriding existing skill {skill.name}', fg='magenta'))
                    link, status = link_skill(skill.path, skill.name, agent_dir, force=True, agent_name=agent_name)
                else:
                    if verbose:
                        click.echo(click.style(f'  Skipped {skill.name} for [{agent_name}]', dim=True))
                    continue

            linked_paths.append(compact_path(str(link)))
            link_line = f'    {skill.name} -> [{agent_name}] {compact_path(str(link))}'

            if verbose:
                click.echo(f'  {link_line} {_format_link_status(status)}')
            else:
                if status != 'exists':
                    skill_changed = True
                    skill_lines.append(link_line)

        if not verbose and skill_changed:
            added_count += 1
            deferred_lines.append(click.style(f'  {skill.name}', fg='yellow') + f' from {source_label}')
            deferred_lines.extend(skill_lines)

        new_lock_skills.append(
            InstalledSkill(
                name=skill.name,
                local_path=compact_path(str(local_path)),
                commit=None,
                skill_path=skill.relative_path,
                linked_to=linked_paths,
            )
        )

    return added_count, deferred_lines


def _install_repo(
    repo_config, store_dir, new_lock_skills, configured_skill_keys, known_agents, force=False, verbose=False
):
    """Install skills from a git repo. Returns (added_count, deferred_lines)."""
    repo_dir_name = repo_url_to_dirname(repo_config.repo)
    repo_path = store_dir / repo_dir_name

    was_existing = repo_path.exists() and (repo_path / '.git').exists()
    if was_existing:
        if verbose:
            click.echo(click.style(f'Using existing {repo_config.repo}', fg='blue', bold=True))
    else:
        if not verbose:
            _progress(f'  Cloning {repo_config.repo}...')
        else:
            click.echo(click.style(f'Cloning {repo_config.repo}...', fg='blue', bold=True))
        clone_or_pull(repo_config.repo, repo_path, clone_strategy=repo_config.clone_strategy)

    commit = get_head_commit(repo_path)
    try:
        detected = detect_skills(repo_path, repo_config.skills_dir)
    except ValueError as e:
        raise click.ClickException(str(e))
    if verbose:
        click.echo(click.style(f'  Found skills: {", ".join(s.name for s in detected) or "(none)"}', dim=True))

    target_agents = resolve_target_agents(repo_config.agents, known_agents)

    if repo_config.skills is not None:
        requested = set(repo_config.skills)
        skills_to_install = [s for s in detected if s.name in requested]
        missing = requested - {s.name for s in skills_to_install}
        if missing and was_existing:
            # Repo was already cloned but requested skills are missing — pull and retry
            if not verbose:
                _progress(f'  Pulling {repo_config.repo} (missing skills: {", ".join(sorted(missing))})...')
            else:
                click.echo(click.style(f'  Pulling {repo_config.repo} (missing skills: {", ".join(sorted(missing))})...', fg='blue'))
            clone_or_pull(repo_config.repo, repo_path, clone_strategy=repo_config.clone_strategy)
            commit = get_head_commit(repo_path)
            try:
                detected = detect_skills(repo_path, repo_config.skills_dir)
            except ValueError as e:
                raise click.ClickException(str(e))
            if verbose:
                click.echo(click.style(f'  Found skills after pull: {", ".join(s.name for s in detected) or "(none)"}', dim=True))
            skills_to_install = [s for s in detected if s.name in requested]
            still_missing = requested - {s.name for s in skills_to_install}
            if still_missing:
                click.echo(click.style(f'  Warning: skills not found in repo: {still_missing}', fg='red'))
        elif missing:
            click.echo(click.style(f'  Warning: skills not found in repo: {missing}', fg='red'))
    else:
        skills_to_install = detected

    skills_to_install = _dedup_skills(skills_to_install, repo_config.repo, verbose)

    added_count = 0
    deferred_lines: list[str] = []

    for skill in skills_to_install:
        configured_skill_keys.add((skill.name, repo_config.repo))
        linked_paths = []
        skill_changed = False
        skill_lines: list[str] = []

        if not verbose:
            _progress(f'  {skill.name}')

        if verbose:
            click.echo(click.style(f'  Install skill {skill.name}', fg='yellow'))

        for agent_name, agent_dir in target_agents.items():
            try:
                link, status = link_skill(skill.path, skill.name, agent_dir, agent_name=agent_name)
            except FileExistsError as e:
                if force or _confirm_override(f'  {e}. Override?'):
                    if verbose:
                        click.echo(click.style(f'  Overriding existing skill {skill.name}', fg='magenta'))
                    link, status = link_skill(skill.path, skill.name, agent_dir, force=True, agent_name=agent_name)
                else:
                    if verbose:
                        click.echo(click.style(f'  Skipped {skill.name} for [{agent_name}]', dim=True))
                    continue

            linked_paths.append(compact_path(str(link)))
            link_line = f'    {skill.name} -> [{agent_name}] {compact_path(str(link))}'

            if verbose:
                click.echo(f'  {link_line} {_format_link_status(status)}')
            else:
                if status != 'exists':
                    skill_changed = True
                    skill_lines.append(link_line)

        if not verbose and skill_changed:
            added_count += 1
            deferred_lines.append(click.style(f'  {skill.name}', fg='yellow') + f' from {repo_config.repo}')
            deferred_lines.extend(skill_lines)

        new_lock_skills.append(
            InstalledSkill(
                name=skill.name,
                repo=repo_config.repo,
                commit=commit,
                skill_path=skill.relative_path,
                linked_to=linked_paths,
            )
        )

    return added_count, deferred_lines


def run_install_package(
    repo_config: SkillRepoConfig,
    lock_path: Path,
    store_dir: Path,
    known_agents: dict[str, str],
    force: bool = False,
    verbose: bool = False,
) -> None:
    """Install a single package and merge results into the existing lock file."""
    lock = load_lock(lock_path)
    new_lock_skills: list[InstalledSkill] = []
    configured_skill_keys: set[tuple[str, str]] = set()

    if repo_config.is_local:
        added_count, deferred_lines = _install_local(
            repo_config, new_lock_skills, configured_skill_keys, known_agents, force, verbose
        )
    else:
        added_count, deferred_lines = _install_repo(
            repo_config, store_dir, new_lock_skills, configured_skill_keys, known_agents, force, verbose
        )

    if not verbose:
        _clear_progress()
        for line in deferred_lines:
            click.echo(line)

    if verbose:
        click.echo()
    else:
        if added_count == 0:
            click.echo('up to date')
        else:
            click.echo()
            click.echo(f'added {added_count} skill{"s" if added_count != 1 else ""}')

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
