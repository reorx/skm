import re
from pathlib import Path

from skm.types import DetectedSkill


def parse_skill_name(skill_md_path: Path) -> str:
    """Extract 'name' from SKILL.md YAML frontmatter."""
    return parse_skill_name_text(skill_md_path.read_text(encoding='utf-8'), str(skill_md_path))


def parse_skill_name_text(text: str, origin: str) -> str:
    """Extract 'name' from SKILL.md text; origin only labels error messages."""
    match = re.match(r'^---\s*\n(.*?)\n---', text, re.DOTALL)
    if not match:
        raise ValueError(f'No frontmatter found in {origin}')
    for line in match.group(1).splitlines():
        if line.startswith('name:'):
            return line.split(':', 1)[1].strip().strip('\'"')
    raise ValueError(f"No 'name' field in frontmatter of {origin}")


def detect_skills(repo_path: Path, skills_dir: str | None = None) -> list[DetectedSkill]:
    """Detect skills in a cloned repo by walking for SKILL.md files."""
    if skills_dir is not None:
        walk_root = repo_path / skills_dir
        if not walk_root.is_dir():
            raise ValueError(f"skills_dir does not exist or is not a directory: {skills_dir} (repo: {repo_path})")

        root_skill = walk_root / 'SKILL.md'
        if root_skill.exists():
            name = parse_skill_name(root_skill)
            return [DetectedSkill(name=name, path=walk_root, relative_path=str(walk_root.relative_to(repo_path)))]

        return _walk_for_skills(walk_root, repo_path)

    # Case 1: Root has SKILL.md → singleton skill
    root_skill = repo_path / 'SKILL.md'
    if root_skill.exists():
        name = parse_skill_name(root_skill)
        return [DetectedSkill(name=name, path=repo_path, relative_path='.')]

    # Determine walk root
    skills_dir = repo_path / 'skills'
    walk_root = skills_dir if skills_dir.is_dir() else repo_path

    return _walk_for_skills(walk_root, repo_path)


def _walk_for_skills(walk_root: Path, repo_path: Path) -> list[DetectedSkill]:
    """Walk subdirectories looking for SKILL.md. Stop descending once found."""
    results = []
    for child in sorted(walk_root.iterdir()):
        if not child.is_dir() or child.is_symlink():
            continue
        if child.name == '.git' or child.name.startswith('_'):
            continue
        skill_md = child / 'SKILL.md'
        if skill_md.exists():
            name = parse_skill_name(skill_md)
            relative = str(child.relative_to(repo_path))
            results.append(DetectedSkill(name=name, path=child, relative_path=relative))
        else:
            # Recurse deeper
            results.extend(_walk_for_skills(child, repo_path))
    return results


def select_skill_dirs(paths: list[str], skills_dir: str | None = None) -> list[str] | None:
    """Pick skill directories from a list of repo-relative file paths.

    Mirrors detect_skills() but works on a path listing (e.g. `git ls-tree`)
    instead of the filesystem, so it can run before anything is checked out.
    Returns None when the repo root itself is a skill (full checkout needed),
    otherwise a sorted list of skill directories relative to the repo root.
    """
    skill_md_dirs = {
        p.rsplit('/', 1)[0] if '/' in p else ''
        for p in paths
        if p.rsplit('/', 1)[-1] == 'SKILL.md'
    }

    if skills_dir is not None:
        walk_root = skills_dir.strip('/')
        if walk_root in skill_md_dirs:
            return [walk_root]
        return _select_under(walk_root, skill_md_dirs)

    if '' in skill_md_dirs:
        return None

    has_skills_dir = any(p.startswith('skills/') for p in paths)
    return _select_under('skills' if has_skills_dir else '', skill_md_dirs)


def _select_under(walk_root: str, skill_md_dirs: set[str]) -> list[str]:
    """Skill dirs strictly below walk_root, skipping `_*` dirs and nested skills."""
    prefix = f'{walk_root}/' if walk_root else ''
    results = []
    for d in sorted(skill_md_dirs):
        if not d.startswith(prefix) or d == walk_root:
            continue
        parts = d[len(prefix):].split('/')
        if any(part == '.git' or part.startswith('_') for part in parts):
            continue
        ancestors = (prefix + '/'.join(parts[:i]) for i in range(1, len(parts)))
        if any(a in skill_md_dirs for a in ancestors):
            continue
        results.append(d)
    return results
