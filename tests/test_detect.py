import pytest
from skm.detect import detect_skills
from skm.git import clone_or_pull


def _write_skill_md(path, name):
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text(f"---\nname: {name}\ndescription: test\n---\nContent\n")


def test_detect_singleton_skill(tmp_path):
    """Repo root has SKILL.md - it's a singleton skill."""
    _write_skill_md(tmp_path, "my-skill")
    skills = detect_skills(tmp_path)
    assert len(skills) == 1
    assert skills[0].name == "my-skill"
    assert skills[0].path == tmp_path
    assert skills[0].relative_path == "."


def test_detect_skills_in_skills_dir(tmp_path):
    """Repo has ./skills/ dir with sub-skills."""
    skills_dir = tmp_path / "skills"
    _write_skill_md(skills_dir / "skill-a", "skill-a")
    _write_skill_md(skills_dir / "skill-b", "skill-b")
    # Also create a non-skill dir
    (skills_dir / "not-a-skill").mkdir(parents=True)
    (skills_dir / "not-a-skill" / "README.md").write_text("nope")

    skills = detect_skills(tmp_path)
    names = {s.name for s in skills}
    assert names == {"skill-a", "skill-b"}


def test_detect_skills_no_skills_dir(tmp_path):
    """No ./skills/ dir, walk from root."""
    _write_skill_md(tmp_path / "foo", "foo-skill")
    _write_skill_md(tmp_path / "bar", "bar-skill")
    skills = detect_skills(tmp_path)
    names = {s.name for s in skills}
    assert names == {"foo-skill", "bar-skill"}


def test_detect_skills_nested_stop_at_skill(tmp_path):
    """Once SKILL.md is found, don't dig deeper."""
    _write_skill_md(tmp_path / "outer", "outer-skill")
    # Nested SKILL.md should NOT be found separately
    _write_skill_md(tmp_path / "outer" / "inner", "inner-skill")
    skills = detect_skills(tmp_path)
    assert len(skills) == 1
    assert skills[0].name == "outer-skill"


def test_detect_skills_empty_repo(tmp_path):
    """No SKILL.md anywhere."""
    (tmp_path / "src").mkdir()
    (tmp_path / "README.md").write_text("hello")
    skills = detect_skills(tmp_path)
    assert skills == []


@pytest.mark.network
def test_detect_taste_skill_repo(tmp_path):
    """Detect skills from Leonxlnx/taste-skill repo."""
    dest = tmp_path / "taste-skill"
    clone_or_pull("https://github.com/Leonxlnx/taste-skill", dest)
    skills = detect_skills(dest)
    names = {s.name for s in skills}
    assert "design-taste-frontend" in names
    assert "redesign-existing-projects" in names


@pytest.mark.network
def test_detect_vercel_agent_skills_repo(tmp_path):
    """Detect skills from vercel-labs/agent-skills repo."""
    dest = tmp_path / "agent-skills"
    clone_or_pull("https://github.com/vercel-labs/agent-skills", dest)
    skills = detect_skills(dest)
    names = {s.name for s in skills}
    assert "vercel-react-best-practices" in names
    assert "vercel-react-native-skills" in names
