from skm.lock import load_lock, save_lock
from skm.types import LockFile, InstalledSkill


def test_load_lock_missing_file(tmp_path):
    lock = load_lock(tmp_path / "nonexistent.yaml")
    assert lock.skills == []


def test_save_and_load_lock(tmp_path):
    lock_path = tmp_path / "skills-lock.yaml"
    lock = LockFile(skills=[
        InstalledSkill(
            name="react-best-practices",
            repo="https://github.com/vercel-labs/agent-skills",
            commit="abc1234",
            skill_path="skills/react-best-practices",
            linked_to=["/Users/test/.claude/skills/react-best-practices"],
        )
    ])
    save_lock(lock, lock_path)
    loaded = load_lock(lock_path)
    assert len(loaded.skills) == 1
    assert loaded.skills[0].name == "react-best-practices"
    assert loaded.skills[0].commit == "abc1234"
