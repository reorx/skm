import shutil
from pathlib import Path

import click

from skm.config import load_config, save_config
from skm.lock import load_lock, save_lock
from skm.utils import compact_path


def run_remove(
    skill_name: str,
    config_path: Path,
    lock_path: Path,
) -> None:
    lock = load_lock(lock_path)

    # Find the skill in the lock file
    skill_entry = None
    for s in lock.skills:
        if s.name == skill_name:
            skill_entry = s
            break

    if skill_entry is None:
        raise click.ClickException(f'Skill "{skill_name}" is not installed.')

    # Remove all linked paths (symlinks/hardlink dirs)
    for link_path_str in skill_entry.linked_to:
        p = Path(link_path_str).expanduser()
        if p.is_symlink():
            p.unlink()
            click.echo(f'  Removed symlink {compact_path(str(p))}')
        elif p.is_dir():
            shutil.rmtree(p)
            click.echo(f'  Removed directory {compact_path(str(p))}')
        else:
            click.echo(click.style(f'  Link not found: {compact_path(str(p))}', dim=True))

    # Remove the skill from lock file
    source_key = skill_entry.repo or skill_entry.local_path or ''
    lock.skills = [s for s in lock.skills if s.name != skill_name]
    save_lock(lock, lock_path)
    click.echo(f'Lock file updated: {lock_path}')

    # Update config if it exists
    if not config_path.exists():
        return

    config = load_config(config_path)
    config_modified = False

    # Find the package that contains this skill
    pkg_index = None
    for i, pkg in enumerate(config.packages):
        if pkg.source_key == source_key or (
            pkg.local_path and str(Path(pkg.local_path).expanduser()) == str(Path(source_key).expanduser())
        ):
            pkg_index = i
            break

    if pkg_index is None:
        return

    pkg = config.packages[pkg_index]

    if pkg.skills is not None:
        # Explicit skills list: remove this skill name
        if skill_name in pkg.skills:
            pkg.skills.remove(skill_name)
            config_modified = True

        if not pkg.skills:
            # No skills left in the list, remove the entire package
            config.packages.pop(pkg_index)
            config_modified = True
            click.echo(f'  Removed package from config (no skills remaining)')
    else:
        # skills is None (all skills) — check if any other lock entries still reference this source
        has_remaining = any((s.repo or s.local_path or '') == source_key for s in lock.skills)
        if not has_remaining:
            config.packages.pop(pkg_index)
            config_modified = True
            click.echo(f'  Removed package from config (no skills remaining)')

    if config_modified:
        save_config(config, config_path)
        click.echo(f'Config updated: {config_path}')

    click.echo(click.style(f'Skill "{skill_name}" removed.', fg='green'))
