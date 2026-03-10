import os
import shutil
from pathlib import Path

from skm.types import AGENT_OPTIONS, AgentsConfig


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


def _hardlink_tree(src: Path, dst: Path) -> None:
    """Recreate directory structure from src at dst, hard-linking all files."""
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir():
            _hardlink_tree(item, target)
        else:
            if target.exists():
                target.unlink()
            os.link(item, target)


def _is_hardlinked_dir(link_path: Path, skill_src: Path) -> bool:
    """Check if link_path is a hardlinked copy of skill_src by comparing inodes of files."""
    if not link_path.is_dir() or link_path.is_symlink():
        return False
    # Check if any file in the dir shares an inode with the source
    for item in skill_src.iterdir():
        if item.is_file():
            target = link_path / item.name
            if target.exists() and target.stat().st_ino == item.stat().st_ino:
                return True
    return False


def link_skill(
    skill_src: Path, skill_name: str, agent_skills_dir: str, force: bool = False, agent_name: str = ''
) -> Path:
    """Create a symlink (or hardlink tree) from agent_skills_dir/skill_name -> skill_src."""
    use_hardlink = _get_agent_option(agent_name, 'use_hardlink', False)
    target_dir = Path(agent_skills_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    link_path = target_dir / skill_name

    if use_hardlink:
        # Hard-link mode: recreate dir structure with hardlinked files
        if link_path.exists() and not link_path.is_symlink():
            if _is_hardlinked_dir(link_path, skill_src):
                # Already hardlinked, refresh to pick up any changes
                _hardlink_tree(skill_src, link_path)
                return link_path
            if not force:
                raise FileExistsError(f'{link_path} exists and is not a hardlinked copy')
            shutil.rmtree(link_path)
        elif link_path.is_symlink():
            # Switching from symlink to hardlink
            link_path.unlink()

        _hardlink_tree(skill_src, link_path)
        return link_path

    # Symlink mode (default)
    if link_path.is_symlink():
        if link_path.resolve() == skill_src.resolve():
            return link_path
        link_path.unlink()

    if link_path.exists():
        if force:
            if link_path.is_dir():
                shutil.rmtree(link_path)
            else:
                link_path.unlink()
        else:
            raise FileExistsError(f'{link_path} exists and is not a symlink')

    link_path.symlink_to(skill_src)
    return link_path


def unlink_skill(skill_name: str, agent_skills_dir: str) -> None:
    """Remove symlink or hardlinked dir for a skill from an agent dir."""
    link_path = Path(agent_skills_dir) / skill_name
    if link_path.is_symlink():
        link_path.unlink()
    elif link_path.is_dir():
        shutil.rmtree(link_path)
