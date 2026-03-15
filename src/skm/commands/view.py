import shutil
import subprocess
from pathlib import Path

import click

from skm.detect import detect_skills
from skm.git import clone_or_pull, repo_url_to_dirname
from skm.tui import interactive_select


def _find_viewer() -> str | None:
    """Find bat or less on the system."""
    for cmd in ('bat', 'less'):
        if shutil.which(cmd):
            return cmd
    return None


def _open_viewer(skill_md: Path, viewer: str | None) -> None:
    """Open a SKILL.md file for reading."""
    if viewer == 'bat':
        subprocess.run(['bat', '--style=plain', '--paging=always', str(skill_md)])
    elif viewer == 'less':
        subprocess.run(['less', str(skill_md)])
    else:
        click.echo_via_pager(skill_md.read_text(encoding="utf-8"))


def run_view(source: str, store_dir: Path) -> None:
    # Resolve source
    source_path = Path(source).expanduser()
    if source_path.is_dir():
        repo_path = source_path
    else:
        dest = store_dir / repo_url_to_dirname(source)
        clone_or_pull(source, dest)
        repo_path = dest

    skills = detect_skills(repo_path)
    if not skills:
        click.echo('No skills found.')
        return

    viewer = _find_viewer()
    labels = [f'{s.name}  ({s.relative_path})' for s in skills]

    last_idx = 0
    while True:
        idx = interactive_select(labels, header=f'Skills in {source}', initial=last_idx)
        if idx is None:
            break
        last_idx = idx
        _open_viewer(skills[idx].path / 'SKILL.md', viewer)
