import pytest
from skm.detect import detect_skills
from skm.git import clone_or_pull


def _write_skill_md(path, name):
    path.mkdir(parents=True, exist_ok=True)
    (path / 'SKILL.md').write_text(f'---\nname: {name}\ndescription: test\n---\nContent\n')


def test_detect_singleton_skill(tmp_path):
    """Repo root has SKILL.md - it's a singleton skill."""
    _write_skill_md(tmp_path, 'my-skill')
    skills = detect_skills(tmp_path)
    assert len(skills) == 1
    assert skills[0].name == 'my-skill'
    assert skills[0].path == tmp_path
    assert skills[0].relative_path == '.'


def test_detect_skills_in_skills_dir(tmp_path):
    """Repo has ./skills/ dir with sub-skills."""
    skills_dir = tmp_path / 'skills'
    _write_skill_md(skills_dir / 'skill-a', 'skill-a')
    _write_skill_md(skills_dir / 'skill-b', 'skill-b')
    # Also create a non-skill dir
    (skills_dir / 'not-a-skill').mkdir(parents=True)
    (skills_dir / 'not-a-skill' / 'README.md').write_text('nope')

    skills = detect_skills(tmp_path)
    names = {s.name for s in skills}
    assert names == {'skill-a', 'skill-b'}


def test_detect_skills_no_skills_dir(tmp_path):
    """No ./skills/ dir, walk from root."""
    _write_skill_md(tmp_path / 'foo', 'foo-skill')
    _write_skill_md(tmp_path / 'bar', 'bar-skill')
    skills = detect_skills(tmp_path)
    names = {s.name for s in skills}
    assert names == {'foo-skill', 'bar-skill'}


def test_detect_skills_nested_stop_at_skill(tmp_path):
    """Once SKILL.md is found, don't dig deeper."""
    _write_skill_md(tmp_path / 'outer', 'outer-skill')
    # Nested SKILL.md should NOT be found separately
    _write_skill_md(tmp_path / 'outer' / 'inner', 'inner-skill')
    skills = detect_skills(tmp_path)
    assert len(skills) == 1
    assert skills[0].name == 'outer-skill'


def test_detect_skills_empty_repo(tmp_path):
    """No SKILL.md anywhere."""
    (tmp_path / 'src').mkdir()
    (tmp_path / 'README.md').write_text('hello')
    skills = detect_skills(tmp_path)
    assert skills == []


def test_detect_skills_in_dot_prefixed_dir(tmp_path):
    """Skills inside dot-prefixed directories like .curated should be found."""
    skills_dir = tmp_path / 'skills'
    _write_skill_md(skills_dir / '.curated' / 'frontend-skill', 'frontend-skill')
    _write_skill_md(skills_dir / '.curated' / 'backend-skill', 'backend-skill')
    _write_skill_md(skills_dir / 'normal-skill', 'normal-skill')
    skills = detect_skills(tmp_path)
    names = {s.name for s in skills}
    assert names == {'frontend-skill', 'backend-skill', 'normal-skill'}


def test_detect_skills_skips_git_dir(tmp_path):
    """.git directory should still be skipped."""
    (tmp_path / '.git').mkdir()
    (tmp_path / '.git' / 'SKILL.md').write_text('---\nname: fake\n---\n')
    _write_skill_md(tmp_path / 'real-skill', 'real-skill')
    skills = detect_skills(tmp_path)
    assert len(skills) == 1
    assert skills[0].name == 'real-skill'


def test_detect_skills_in_explicit_skills_dir(tmp_path):
    """Explicit skills_dir limits discovery to that directory."""
    _write_skill_md(tmp_path / 'skills' / 'ignored', 'ignored')
    _write_skill_md(tmp_path / 'certain' / 'relative' / 'path' / 'skill-a', 'skill-a')
    _write_skill_md(tmp_path / 'certain' / 'relative' / 'path' / 'nested' / 'skill-b', 'skill-b')

    skills = detect_skills(tmp_path, skills_dir='certain/relative/path')
    names = {s.name for s in skills}
    assert names == {'skill-a', 'skill-b'}
    assert {s.relative_path for s in skills} == {
        'certain/relative/path/skill-a',
        'certain/relative/path/nested/skill-b',
    }


def test_detect_explicit_skills_dir_can_be_singleton(tmp_path):
    """skills_dir may point directly at one skill directory."""
    _write_skill_md(tmp_path / 'packages' / 'one-skill', 'one-skill')

    skills = detect_skills(tmp_path, skills_dir='packages/one-skill')
    assert len(skills) == 1
    assert skills[0].name == 'one-skill'
    assert skills[0].relative_path == 'packages/one-skill'


def test_detect_missing_explicit_skills_dir_raises(tmp_path):
    with pytest.raises(ValueError, match='skills_dir does not exist'):
        detect_skills(tmp_path, skills_dir='missing')


def test_parse_skill_name_strips_quotes(tmp_path):
    """Quoted name values in frontmatter should have quotes stripped."""
    from skm.detect import parse_skill_name

    # Double-quoted
    dq = tmp_path / 'dq'
    dq.mkdir()
    (dq / 'SKILL.md').write_text('---\nname: "my-skill"\ndescription: test\n---\nContent\n')
    assert parse_skill_name(dq / 'SKILL.md') == 'my-skill'

    # Single-quoted
    sq = tmp_path / 'sq'
    sq.mkdir()
    (sq / 'SKILL.md').write_text("---\nname: 'my-skill'\ndescription: test\n---\nContent\n")
    assert parse_skill_name(sq / 'SKILL.md') == 'my-skill'

    # Unquoted (should still work)
    uq = tmp_path / 'uq'
    uq.mkdir()
    (uq / 'SKILL.md').write_text('---\nname: my-skill\ndescription: test\n---\nContent\n')
    assert parse_skill_name(uq / 'SKILL.md') == 'my-skill'


@pytest.mark.network
def test_detect_taste_skill_repo(tmp_path):
    """Detect skills from Leonxlnx/taste-skill repo."""
    dest = tmp_path / 'taste-skill'
    clone_or_pull('https://github.com/Leonxlnx/taste-skill', dest)
    skills = detect_skills(dest)
    names = {s.name for s in skills}
    assert 'design-taste-frontend' in names
    assert 'redesign-existing-projects' in names


@pytest.mark.network
def test_detect_vercel_agent_skills_repo(tmp_path):
    """Detect skills from vercel-labs/agent-skills repo."""
    dest = tmp_path / 'agent-skills'
    clone_or_pull('https://github.com/vercel-labs/agent-skills', dest)
    skills = detect_skills(dest)
    names = {s.name for s in skills}
    assert 'vercel-react-best-practices' in names
    assert 'vercel-react-native-skills' in names
