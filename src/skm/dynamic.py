"""Dynamic skills: a `source_cmd` package whose SKILL.md is a shell command's stdout.

The output is validated in memory, then written to a directory under the store
named after the command, so `--store` isolates it and a changed command
starts from a fresh directory.
"""

import hashlib
import re
import subprocess
from pathlib import Path

import click

from skm.detect import parse_skill_name_text
from skm.git import run_cmd
from skm.types import DetectedSkill

DYNAMIC_DIRNAME = '_dynamic'  # repo dirs look like `host_path`, so never collide with this
SOURCE_CMD_TIMEOUT = 60  # seconds
SLUG_MAX_LEN = 40
# The name becomes a path under each agent dir; `../x` would escape it.
SAFE_SKILL_NAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]*$')

# What running or validating a source_cmd can raise; callers decide whether it is fatal.
SOURCE_CMD_ERRORS = (click.ClickException, ValueError, subprocess.TimeoutExpired)


def dynamic_skill_dir(store_dir: Path, cmd: str) -> Path:
    slug = '-'.join(re.findall(r'[a-z0-9]+', cmd.lower()))[:SLUG_MAX_LEN].strip('-') or 'cmd'
    digest = hashlib.sha256(cmd.encode()).hexdigest()[:8]
    return store_dir / DYNAMIC_DIRNAME / f'{slug}-{digest}'


def render_source_cmd(cmd: str) -> str:
    """Run cmd and return its stdout as validated SKILL.md text.

    No stdin, so the command cannot block on a prompt; cwd is home so the
    output does not depend on where skm was run.
    """
    result = run_cmd(
        ['sh', '-c', cmd],
        encoding='utf-8',
        stdin=subprocess.DEVNULL,
        cwd=Path.home(),
        timeout=SOURCE_CMD_TIMEOUT,
    )
    text = result.stdout.lstrip()
    _skill_name(text, f'output of `{cmd}`')
    return text


def generate_dynamic_skill(cmd: str, dest_dir: Path) -> bool:
    """Write cmd's output to dest_dir/SKILL.md. Returns whether the content changed.

    Rewrites in place (same inode), so hardlinked copies in materialize agents
    pick up the new content.
    """
    text = render_source_cmd(cmd)
    skill_md = dest_dir / 'SKILL.md'
    if skill_md.is_file() and skill_md.read_text(encoding='utf-8') == text:
        return False
    dest_dir.mkdir(parents=True, exist_ok=True)
    skill_md.write_text(text, encoding='utf-8')
    return True


def load_dynamic_skill(dest_dir: Path) -> DetectedSkill:
    skill_md = dest_dir / 'SKILL.md'
    name = _skill_name(skill_md.read_text(encoding='utf-8'), str(skill_md))
    return DetectedSkill(name=name, path=dest_dir, relative_path='.')


def _skill_name(text: str, origin: str) -> str:
    name = parse_skill_name_text(text, origin)
    if not SAFE_SKILL_NAME_RE.match(name):
        raise ValueError(
            f'Invalid skill name {name!r} in {origin}: use letters, digits, ".", "_" or "-", '
            'starting with a letter or digit'
        )
    return name
