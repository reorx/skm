import re
from pathlib import Path

from skm.types import DetectedSkill


def parse_skill_name(skill_md_path: Path) -> str:
    """Extract 'name' from SKILL.md YAML frontmatter."""
    text = skill_md_path.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not match:
        raise ValueError(f"No frontmatter found in {skill_md_path}")
    for line in match.group(1).splitlines():
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip()
    raise ValueError(f"No 'name' field in frontmatter of {skill_md_path}")


def detect_skills(repo_path: Path) -> list[DetectedSkill]:
    """Detect skills in a cloned repo by walking for SKILL.md files."""
    # Case 1: Root has SKILL.md → singleton skill
    root_skill = repo_path / "SKILL.md"
    if root_skill.exists():
        name = parse_skill_name(root_skill)
        return [DetectedSkill(name=name, path=repo_path, relative_path=".")]

    # Determine walk root
    skills_dir = repo_path / "skills"
    walk_root = skills_dir if skills_dir.is_dir() else repo_path

    return _walk_for_skills(walk_root, repo_path)


def _walk_for_skills(walk_root: Path, repo_path: Path) -> list[DetectedSkill]:
    """Walk subdirectories looking for SKILL.md. Stop descending once found."""
    results = []
    for child in sorted(walk_root.iterdir()):
        if not child.is_dir() or child.is_symlink():
            continue
        if child.name.startswith("."):
            continue
        skill_md = child / "SKILL.md"
        if skill_md.exists():
            name = parse_skill_name(skill_md)
            relative = str(child.relative_to(repo_path))
            results.append(DetectedSkill(name=name, path=child, relative_path=relative))
        else:
            # Recurse deeper
            results.extend(_walk_for_skills(child, repo_path))
    return results
