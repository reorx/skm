import os
import shutil
from pathlib import Path
from typing import Literal

import click

from skm.clonefile import clone_file, is_reflink_unsupported, reflink_supported
from skm.types import AgentSpec, AgentsConfig

MaterializationMode = Literal['hardlink', 'reflink', 'copy']


def resolve_target_agents(
    agents_config: AgentsConfig | None,
    known_agents: dict[str, AgentSpec],
) -> dict[str, AgentSpec]:
    """Determine which agents to install to based on includes/excludes."""
    if agents_config is None:
        return dict(known_agents)

    if agents_config.includes is not None:
        return {k: v for k, v in known_agents.items() if k in agents_config.includes}

    if agents_config.excludes is not None:
        return {k: v for k, v in known_agents.items() if k not in agents_config.excludes}

    return dict(known_agents)


def _clone_file_reflink(src: Path, dst: Path) -> None:
    """Clone a file using the platform's COW mechanism (see skm.clonefile)."""
    clone_file(src, dst)


def _copy_file(src: Path, dst: Path) -> None:
    """Copy a file with metadata."""
    shutil.copy2(src, dst)


def _remove_path(path: Path) -> None:
    """Remove a file or directory."""
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def _get_materialized_entries(path: Path) -> dict[str, Path]:
    """Return managed candidate entries, excluding hidden files and symlinks."""
    return {item.name: item for item in path.iterdir() if not item.name.startswith('.') and not item.is_symlink()}


def _supports_copy_fallback(exc: OSError) -> bool:
    """Return True when a reflink failure should fall back to plain copy."""
    return is_reflink_unsupported(exc)


def _materialize_file(
    src: Path,
    dst: Path,
    mode: MaterializationMode,
) -> MaterializationMode:
    """Materialize a file and return the mode to keep using."""
    if mode == 'hardlink':
        os.link(src, dst)
        return 'hardlink'

    if mode == 'copy':
        _copy_file(src, dst)
        return 'copy'

    try:
        _clone_file_reflink(src, dst)
    except OSError as exc:
        if not _supports_copy_fallback(exc):
            raise
        _copy_file(src, dst)
        return 'copy'
    return 'reflink'


def _materialize_tree(
    src: Path,
    dst: Path,
    mode: MaterializationMode,
) -> MaterializationMode:
    """Recreate directory structure from src at dst using a materialization mode."""
    dst.mkdir(parents=True, exist_ok=True)
    current_mode = mode
    source_entries = _get_materialized_entries(src)

    for name, item in source_entries.items():
        target = dst / name
        if item.is_dir():
            if target.exists() and not target.is_dir():
                _remove_path(target)
            current_mode = _materialize_tree(item, target, current_mode)
        else:
            if target.exists():
                _remove_path(target)
            current_mode = _materialize_file(item, target, current_mode)
    return current_mode


def _has_stale_materialized_entries(link_path: Path, skill_src: Path) -> bool:
    """Return True when materialized target contains managed entries not present in the source."""
    source_entries = _get_materialized_entries(skill_src)
    target_entries = _get_materialized_entries(link_path)

    for name, target_item in target_entries.items():
        if name not in source_entries:
            return True
        source_item = source_entries[name]
        if target_item.is_dir() and source_item.is_dir() and _has_stale_materialized_entries(target_item, source_item):
            return True
    return False


def _is_managed_materialized_dir(link_path: Path, skill_src: Path) -> bool:
    """Check whether link_path looks like a managed materialized copy."""
    if not link_path.is_dir() or link_path.is_symlink():
        return False

    source_entries = _get_materialized_entries(skill_src)
    target_entries = _get_materialized_entries(link_path)

    compared_any = False
    for name, target_item in target_entries.items():
        if name not in source_entries:
            continue
        source_item = source_entries[name]
        compared_any = True
        if source_item.is_dir():
            if not target_item.is_dir():
                return False
            if not _is_managed_materialized_dir(target_item, source_item):
                return False
            continue
        if not target_item.is_file():
            return False
    return compared_any or not target_entries


def _select_materialization_mode(skill_src: Path, target_dir: Path) -> MaterializationMode:
    """Pick hardlink on the same device, otherwise use reflink or plain copy."""
    src_dev = skill_src.stat().st_dev
    dst_dev = target_dir.stat().st_dev
    if src_dev == dst_dev:
        return 'hardlink'

    if not reflink_supported():
        return 'copy'
    return 'reflink'


def link_skill(
    skill_src: Path, skill_name: str, agent_spec: AgentSpec, force: bool = False
) -> tuple[Path, str]:
    """Create a symlink or materialized tree from agent_spec.path/skill_name -> skill_src.

    Returns (link_path, status) where status is "new", "exists", or "replaced".
    """
    target_dir = Path(agent_spec.path)
    target_dir.mkdir(parents=True, exist_ok=True)
    link_path = target_dir / skill_name

    if agent_spec.install_mode == 'materialize':
        # Materialized mode: prefer hardlink, fall back to reflink when devices differ.
        mode = _select_materialization_mode(skill_src, target_dir)
        if link_path.exists() and not link_path.is_symlink():
            if _is_managed_materialized_dir(link_path, skill_src):
                # Already managed, refresh to pick up any changes.
                if _has_stale_materialized_entries(link_path, skill_src):
                    click.echo(
                        click.style(
                            f'  Warning: materialized copy at {link_path} contains stale files that were not removed',
                            fg='yellow',
                        )
                    )
                _materialize_tree(skill_src, link_path, mode)
                return (link_path, 'exists')
            if not force:
                raise FileExistsError(f'{link_path} exists and is not a managed copy')
            _remove_path(link_path)
            _materialize_tree(skill_src, link_path, mode)
            return (link_path, 'replaced')
        elif link_path.is_symlink():
            # Switching from symlink to a materialized copy.
            link_path.unlink()

        _materialize_tree(skill_src, link_path, mode)
        return (link_path, 'new')

    # Symlink mode (default)
    if link_path.is_symlink():
        if link_path.resolve() == skill_src.resolve():
            return (link_path, 'exists')
        link_path.unlink()
        link_path.symlink_to(skill_src)
        return (link_path, 'replaced')

    if link_path.exists():
        if force:
            if link_path.is_dir():
                shutil.rmtree(link_path)
            else:
                link_path.unlink()
        else:
            raise FileExistsError(f'{link_path} exists and is not a symlink')

    link_path.symlink_to(skill_src)
    return (link_path, 'new')


def unlink_skill(skill_name: str, agent_skills_dir: str) -> None:
    """Remove symlink or materialized dir for a skill from an agent dir."""
    link_path = Path(agent_skills_dir) / skill_name
    if link_path.is_symlink():
        link_path.unlink()
    elif link_path.is_dir():
        shutil.rmtree(link_path)
