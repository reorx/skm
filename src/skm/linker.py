import filecmp
import os
import shutil
from pathlib import Path
from typing import Literal

from skm.clonefile import clone_file, is_reflink_unsupported, reflink_supported
from skm.types import AGENT_OPTIONS, AgentsConfig

MaterializationMode = Literal['hardlink', 'reflink', 'copy']


def _get_agent_option(agent_name: str, option: str, default=None):
    """Look up a per-agent option from AGENT_OPTIONS."""
    return AGENT_OPTIONS.get(agent_name, {}).get(option, default)


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


def _clone_file_reflink(src: Path, dst: Path) -> None:
    """Clone a file using the platform's COW mechanism (see skm.clonefile)."""
    clone_file(src, dst)


def _copy_file(src: Path, dst: Path) -> None:
    """Copy a file with metadata."""
    shutil.copy2(src, dst)


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
    for item in src.iterdir():
        if item.name.startswith('.') or item.is_symlink():
            continue
        target = dst / item.name
        if item.is_dir():
            current_mode = _materialize_tree(item, target, current_mode)
        else:
            if not target.exists():
                current_mode = _materialize_file(item, target, current_mode)
    return current_mode


def _is_managed_materialized_dir(link_path: Path, skill_src: Path) -> bool:
    """Check whether link_path looks like a managed hardlink/reflink materialized copy."""
    if not link_path.is_dir() or link_path.is_symlink():
        return False

    source_entries = _get_materialized_entries(skill_src)
    target_entries = _get_materialized_entries(link_path)
    if not target_entries.keys() <= source_entries.keys():
        return False

    for name, target_item in target_entries.items():
        source_item = source_entries[name]
        if source_item.is_dir():
            if not _is_managed_materialized_dir(target_item, source_item):
                return False
            continue
        if not target_item.is_file():
            return False
        if source_item.stat().st_ino == target_item.stat().st_ino:
            continue
        if not filecmp.cmp(source_item, target_item, shallow=False):
            return False
    return True


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
    skill_src: Path, skill_name: str, agent_skills_dir: str, force: bool = False, agent_name: str = ''
) -> tuple[Path, str]:
    """Create a symlink (or hardlink tree) from agent_skills_dir/skill_name -> skill_src.

    Returns (link_path, status) where status is "new", "exists", or "replaced".
    """
    use_hardlink = _get_agent_option(agent_name, 'use_hardlink', False)
    target_dir = Path(agent_skills_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    link_path = target_dir / skill_name

    if use_hardlink:
        # Materialized mode: prefer hardlink, fall back to reflink when devices differ.
        mode = _select_materialization_mode(skill_src, target_dir)
        if link_path.exists() and not link_path.is_symlink():
            if _is_managed_materialized_dir(link_path, skill_src):
                # Already managed, refresh to pick up any changes.
                _materialize_tree(skill_src, link_path, mode)
                return (link_path, 'exists')
            if not force:
                raise FileExistsError(f'{link_path} exists and is not a managed copy')
            shutil.rmtree(link_path)
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
    """Remove symlink or hardlinked dir for a skill from an agent dir."""
    link_path = Path(agent_skills_dir) / skill_name
    if link_path.is_symlink():
        link_path.unlink()
    elif link_path.is_dir():
        shutil.rmtree(link_path)
