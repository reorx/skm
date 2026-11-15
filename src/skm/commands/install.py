import shutil
import sys
from pathlib import Path

import click
from pydantic import BaseModel

from skm.detect import detect_skills
from skm.dynamic import SOURCE_CMD_ERRORS, dynamic_skill_dir, generate_dynamic_skill, load_dynamic_skill
from skm.git import clone_or_pull, get_head_commit, repo_url_to_dirname
from skm.linker import find_ignored_includes, link_skill, unlink_skill, resolve_target_agents
from skm.lock import load_lock, save_lock
from skm.types import ResolvedAgent, InstalledSkill, LockFile, SkillRepoConfig, SkmConfig
from skm.utils import compact_path, same_install_location


class LocalOverrides(BaseModel):
    """Skills that local sources install, plus the overrides seen while installing."""

    owners: dict[str, SkillRepoConfig] = {}  # skill name -> local source that installs it
    notes: list[tuple[str, str, str]] = []  # (skill name, winner label, overridden source label)


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


def _source_label(repo_config: SkillRepoConfig) -> str:
    return compact_path(repo_config.source_key)


def _collect_local_overrides(local_sources: list[SkillRepoConfig]) -> LocalOverrides:
    """Local sources outrank skills.yaml packages; between local sources the first entry wins."""
    owners: dict[str, SkillRepoConfig] = {}
    for source in local_sources:
        try:
            detected = detect_skills(Path(source.local_path).expanduser())
        except ValueError as e:
            raise click.ClickException(str(e))
        for skill in detected:
            owners.setdefault(skill.name, source)
    return LocalOverrides(owners=owners)


def _drop_overridden(skills, repo_config: SkillRepoConfig, overrides: LocalOverrides):
    """Leave out skills that another local source installs, noting each override."""
    kept = []
    for skill in skills:
        owner = overrides.owners.get(skill.name)
        if owner is None or owner.source_key == repo_config.source_key:
            kept.append(skill)
        else:
            overrides.notes.append((skill.name, _source_label(owner), _source_label(repo_config)))
    return kept


def _print_overrides(overrides: LocalOverrides) -> None:
    if not overrides.notes:
        return
    click.echo()
    click.secho('Local source overrides', fg='cyan', bold=True)
    for skill_name, winner, overridden in overrides.notes:
        click.secho(f'  {skill_name}: {winner} overrides {overridden}', fg='cyan')


def run_install(
    config: SkmConfig,
    lock_path: Path,
    store_dir: Path,
    known_agents: dict[str, ResolvedAgent],
    force: bool = False,
    verbose: bool = False,
    local_sources: list[SkillRepoConfig] | None = None,
) -> None:
    """Sync config packages plus device-local sources (never saved to config).

    A skill provided by a local source is skipped in every other package.
    """
    lock = load_lock(lock_path)
    new_lock_skills: list[InstalledSkill] = []
    skipped_paths: set[str] = set()
    overrides = _collect_local_overrides(local_sources or [])

    # Track which skills are configured (for removal detection)
    # Key: (skill_name, source_key)
    configured_skill_keys: set[tuple[str, str]] = set()

    added_count = 0
    all_deferred_lines: list[str] = []

    try:
        for repo_config in [*config.packages, *(local_sources or [])]:
            count, lines = _install_package(
                repo_config,
                store_dir,
                new_lock_skills,
                configured_skill_keys,
                known_agents,
                skipped_paths,
                force,
                verbose,
                overrides,
            )
            added_count += count
            all_deferred_lines.extend(lines)

            if verbose:
                click.echo()
    except BaseException:
        # Clear the refreshing progress line so the error message is not
        # appended to a stale progress line from a previous package
        if not verbose:
            _clear_progress()
        raise

    if not verbose:
        _clear_progress()
        # Print deferred output for changed skills
        for line in all_deferred_lines:
            click.echo(line)

    _print_overrides(overrides)
    removed_count = _remove_stale_links(lock.skills, new_lock_skills, configured_skill_keys, skipped_paths)

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


def _remove_stale_links(old_skills, new_lock_skills, configured_skill_keys, skipped_paths) -> int:
    # Build set of all new linked paths for comparison
    new_linked_paths: set[str] = set()
    for skill in new_lock_skills:
        for lp in skill.linked_to:
            new_linked_paths.add(lp)

    # Remove stale links: any old linked_to path not present in new state
    stale_header_printed = False
    removed_count = 0
    for old_skill in old_skills:
        skill_still_configured = (old_skill.name, old_skill.source) in configured_skill_keys

        for link_path_str in old_skill.linked_to:
            # Unchanged installs and declined targets need no filesystem comparison.
            if link_path_str in new_linked_paths or link_path_str in skipped_paths:
                continue
            # Declined targets belong to the user now; neither remove nor track them.
            if any(same_install_location(link_path_str, skipped) for skipped in skipped_paths):
                continue
            if not any(same_install_location(link_path_str, new_path) for new_path in new_linked_paths):
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

    return removed_count


def _install_package(
    repo_config: SkillRepoConfig,
    store_dir: Path,
    new_lock_skills,
    configured_skill_keys,
    known_agents,
    skipped_paths,
    force=False,
    verbose=False,
    overrides: LocalOverrides | None = None,
):
    """Install one package of any source type. Returns (added_count, deferred_lines)."""
    if repo_config.is_dynamic:
        return _install_dynamic(
            repo_config, store_dir, new_lock_skills, configured_skill_keys, known_agents, skipped_paths, force, verbose,
            overrides,
        )
    if repo_config.is_local:
        return _install_local(
            repo_config, new_lock_skills, configured_skill_keys, known_agents, skipped_paths, force, verbose, overrides
        )
    return _install_repo(
        repo_config, store_dir, new_lock_skills, configured_skill_keys, known_agents, skipped_paths, force, verbose,
        overrides,
    )


def _target_agents(repo_config: SkillRepoConfig, known_agents, verbose=False) -> dict[str, ResolvedAgent]:
    """Agents this package installs to, warning about includes outside agents.default."""
    target_agents = resolve_target_agents(repo_config.agents, known_agents)
    ignored = find_ignored_includes(repo_config.agents, known_agents)
    if ignored:
        if not verbose:
            _clear_progress()
        click.secho(
            f'  Warning: package {_source_label(repo_config)} includes agents not in agents.default, '
            f'ignored: {", ".join(ignored)}',
            fg='yellow',
        )
    return target_agents


def _link_skills(
    skills,
    target_agents: dict[str, ResolvedAgent],
    lock_source: dict,
    source_label: str,
    new_lock_skills,
    configured_skill_keys,
    skipped_paths,
    force=False,
    verbose=False,
):
    """Link each skill into every target agent and record it in the new lock.

    lock_source holds the InstalledSkill source fields (repo/commit, local_path or
    source_cmd). Returns (added_count, deferred_lines).
    """
    added_count = 0
    deferred_lines: list[str] = []

    for skill in skills:
        linked_paths = []
        skill_changed = False
        skill_lines: list[str] = []

        if not verbose:
            _progress(f'  {skill.name}')

        if verbose:
            click.echo(click.style(f'  Install skill {skill.name}', fg='yellow'))

        for agent_name, agent in target_agents.items():
            try:
                link, status = link_skill(skill.path, skill.name, agent.path, install_mode=agent.install_mode)
            except FileExistsError as e:
                if force or _confirm_override(f'  {e}. Override?'):
                    if verbose:
                        click.echo(click.style(f'  Overriding existing skill {skill.name}', fg='magenta'))
                    link, status = link_skill(
                        skill.path, skill.name, agent.path, force=True, install_mode=agent.install_mode
                    )
                else:
                    skipped_paths.add(compact_path(str(Path(agent.path).expanduser() / skill.name)))
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

        entry = InstalledSkill(
            name=skill.name, skill_path=skill.relative_path, linked_to=linked_paths, **lock_source
        )
        configured_skill_keys.add((skill.name, entry.source))
        new_lock_skills.append(entry)

    return added_count, deferred_lines


def _install_dynamic(
    repo_config,
    store_dir,
    new_lock_skills,
    configured_skill_keys,
    known_agents,
    skipped_paths,
    force=False,
    verbose=False,
    overrides: LocalOverrides | None = None,
):
    """Install the skill a source_cmd generates. Returns (added_count, deferred_lines).

    A failing command only warns: the package stays out of the lock so a shared
    skills.yaml still installs on devices without that CLI, and the next
    install retries it.
    """
    cmd = repo_config.source_cmd
    try:
        skill = _prepare_dynamic_skill(cmd, store_dir, verbose)
    except SOURCE_CMD_ERRORS as e:
        if not verbose:
            _clear_progress()
        reason = str(e).replace('\n', '\n    ')
        click.secho(f'  Warning: skipping dynamic skill from `{cmd}`:\n    {reason}', fg='yellow')
        return 0, []

    target_agents = _target_agents(repo_config, known_agents, verbose)
    skills = [skill]
    if overrides is not None:
        skills = _drop_overridden(skills, repo_config, overrides)
    return _link_skills(
        skills,
        target_agents,
        {'source_cmd': cmd},
        f'`{cmd}`',
        new_lock_skills,
        configured_skill_keys,
        skipped_paths,
        force,
        verbose,
    )


def _prepare_dynamic_skill(cmd: str, store_dir: Path, verbose: bool):
    """Generate the skill on first install; later installs reuse it (`skm update` reruns cmd)."""
    dest = dynamic_skill_dir(store_dir, cmd)
    if (dest / 'SKILL.md').is_file():
        if verbose:
            click.echo(click.style(f'Using generated skill from `{cmd}`', fg='blue', bold=True))
    else:
        if verbose:
            click.echo(click.style(f'Running `{cmd}`...', fg='blue', bold=True))
        else:
            _progress(f'  Running `{cmd}`...')
        generate_dynamic_skill(cmd, dest)
    return load_dynamic_skill(dest)


def _install_local(
    repo_config,
    new_lock_skills,
    configured_skill_keys,
    known_agents,
    skipped_paths,
    force=False,
    verbose=False,
    overrides: LocalOverrides | None = None,
):
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

    target_agents = _target_agents(repo_config, known_agents, verbose)

    if repo_config.skills is not None:
        requested = set(repo_config.skills)
        skills_to_install = [s for s in detected if s.name in requested]
        missing = requested - {s.name for s in skills_to_install}
        if missing:
            click.echo(click.style(f'  Warning: skills not found: {missing}', fg='red'))
    elif repo_config.skills_excludes is not None:
        excluded = set(repo_config.skills_excludes)
        skills_to_install = [s for s in detected if s.name not in excluded]
    else:
        skills_to_install = detected

    skills_to_install = _dedup_skills(skills_to_install, source_label, verbose)
    if overrides is not None:
        skills_to_install = _drop_overridden(skills_to_install, repo_config, overrides)

    return _link_skills(
        skills_to_install,
        target_agents,
        {'local_path': compact_path(str(local_path))},
        source_label,
        new_lock_skills,
        configured_skill_keys,
        skipped_paths,
        force,
        verbose,
    )


def _install_repo(
    repo_config,
    store_dir,
    new_lock_skills,
    configured_skill_keys,
    known_agents,
    skipped_paths,
    force=False,
    verbose=False,
    overrides: LocalOverrides | None = None,
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
        clone_or_pull(
            repo_config.repo, repo_path, clone_strategy=repo_config.clone_strategy, skills_dir=repo_config.skills_dir
        )

    commit = get_head_commit(repo_path)
    try:
        detected = detect_skills(repo_path, repo_config.skills_dir)
    except ValueError as e:
        raise click.ClickException(str(e))
    if verbose:
        click.echo(click.style(f'  Found skills: {", ".join(s.name for s in detected) or "(none)"}', dim=True))

    target_agents = _target_agents(repo_config, known_agents, verbose)

    if repo_config.skills is not None:
        requested = set(repo_config.skills)
        skills_to_install = [s for s in detected if s.name in requested]
        missing = requested - {s.name for s in skills_to_install}
        if missing and was_existing:
            # Repo was already cloned but requested skills are missing — pull and retry
            if not verbose:
                _progress(f'  Pulling {repo_config.repo} (missing skills: {", ".join(sorted(missing))})...')
            else:
                click.echo(
                    click.style(
                        f'  Pulling {repo_config.repo} (missing skills: {", ".join(sorted(missing))})...', fg='blue'
                    )
                )
            clone_or_pull(
                repo_config.repo,
                repo_path,
                clone_strategy=repo_config.clone_strategy,
                skills_dir=repo_config.skills_dir,
            )
            commit = get_head_commit(repo_path)
            try:
                detected = detect_skills(repo_path, repo_config.skills_dir)
            except ValueError as e:
                raise click.ClickException(str(e))
            if verbose:
                click.echo(
                    click.style(
                        f'  Found skills after pull: {", ".join(s.name for s in detected) or "(none)"}', dim=True
                    )
                )
            skills_to_install = [s for s in detected if s.name in requested]
            still_missing = requested - {s.name for s in skills_to_install}
            if still_missing:
                click.echo(click.style(f'  Warning: skills not found in repo: {still_missing}', fg='red'))
        elif missing:
            click.echo(click.style(f'  Warning: skills not found in repo: {missing}', fg='red'))
    elif repo_config.skills_excludes is not None:
        excluded = set(repo_config.skills_excludes)
        skills_to_install = [s for s in detected if s.name not in excluded]
    else:
        skills_to_install = detected

    skills_to_install = _dedup_skills(skills_to_install, repo_config.repo, verbose)
    if overrides is not None:
        skills_to_install = _drop_overridden(skills_to_install, repo_config, overrides)

    return _link_skills(
        skills_to_install,
        target_agents,
        {'repo': repo_config.repo, 'commit': commit},
        repo_config.repo,
        new_lock_skills,
        configured_skill_keys,
        skipped_paths,
        force,
        verbose,
    )


def run_install_package(
    repo_config: SkillRepoConfig,
    lock_path: Path,
    store_dir: Path,
    known_agents: dict[str, ResolvedAgent],
    force: bool = False,
    verbose: bool = False,
    local_sources: list[SkillRepoConfig] | None = None,
) -> None:
    """Install a single package and merge results into the existing lock file.

    local_sources decide precedence: skills they provide are skipped here unless
    this package is the winning local source, which then takes over other
    sources' lock entries for those skills.
    """
    lock = load_lock(lock_path)
    new_lock_skills: list[InstalledSkill] = []
    configured_skill_keys: set[tuple[str, str]] = set()
    overrides = _collect_local_overrides(local_sources or [])

    skipped_paths: set[str] = set()
    try:
        added_count, deferred_lines = _install_package(
            repo_config,
            store_dir,
            new_lock_skills,
            configured_skill_keys,
            known_agents,
            skipped_paths,
            force,
            verbose,
            overrides,
        )
    except BaseException:
        if not verbose:
            _clear_progress()
        raise

    if not verbose:
        _clear_progress()
        for line in deferred_lines:
            click.echo(line)

    # Merge: keep existing lock entries from other sources, replace entries from this source
    # and entries of skills this package now overrides as the winning local source.
    source_key = repo_config.source_key
    taken_over = {
        s.name
        for s in new_lock_skills
        if (owner := overrides.owners.get(s.name)) is not None and owner.source_key == source_key
    }
    merged_skills = []
    replaced = []
    for existing in lock.skills:
        existing_source = existing.source
        # Keep entries not from this source
        if existing_source != source_key:
            # Also check expanded local_path
            if not (
                repo_config.is_local
                and existing.local_path
                and str(Path(existing.local_path).expanduser()) == str(Path(source_key).expanduser())
            ):
                if existing.name in taken_over:
                    overrides.notes.append((existing.name, _source_label(repo_config), existing_source))
                    replaced.append(existing)
                    continue
                merged_skills.append(existing)
                continue
        replaced.append(existing)
    merged_skills.extend(new_lock_skills)
    _print_overrides(overrides)
    removed_count = _remove_stale_links(replaced, merged_skills, configured_skill_keys, skipped_paths)
    if not verbose:
        parts = []
        if added_count:
            parts.append(f'added {added_count} skill{"s" if added_count != 1 else ""}')
        if removed_count:
            parts.append(f'removed {removed_count} skill{"s" if removed_count != 1 else ""}')
        click.echo(', '.join(parts) if parts else 'up to date')

    new_lock = LockFile(skills=merged_skills)
    save_lock(new_lock, lock_path)
    click.echo(f'Lock file updated: {lock_path}')
