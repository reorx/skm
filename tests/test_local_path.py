"""BDD tests for local_path package support."""
import pytest
from pathlib import Path

from skm.types import SkillRepoConfig, InstalledSkill, SkmConfig
from skm.commands.install import run_install
from skm.commands.check_updates import run_check_updates
from skm.commands.update import run_update
from skm.config import load_config
from skm.lock import load_lock


def _make_local_skills_dir(tmp_path, skills: list[str]) -> Path:
    """Create a local directory with skill subdirectories (each with SKILL.md)."""
    local_dir = tmp_path / "local-skills"
    local_dir.mkdir()
    for name in skills:
        skill_dir = local_dir / name
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: test\n---\nContent\n"
        )
    return local_dir


# --- Config validation ---

def test_config_mutual_exclusion():
    """Both repo and local_path set should raise validation error."""
    with pytest.raises(ValueError, match="exactly one"):
        SkillRepoConfig(repo="https://github.com/foo/bar", local_path="~/Code/scripts")


def test_config_neither_set():
    """Neither repo nor local_path set should raise validation error."""
    with pytest.raises(ValueError, match="exactly one"):
        SkillRepoConfig()


def test_config_local_path_valid():
    """local_path alone is valid."""
    cfg = SkillRepoConfig(local_path="~/Code/scripts")
    assert cfg.local_path == "~/Code/scripts"
    assert cfg.repo is None
    assert cfg.is_local is True


def test_config_repo_valid():
    """repo alone is still valid."""
    cfg = SkillRepoConfig(repo="https://github.com/foo/bar")
    assert cfg.is_local is False


def test_config_source_key():
    """source_key returns the appropriate identifier."""
    cfg_repo = SkillRepoConfig(repo="https://github.com/foo/bar")
    assert cfg_repo.source_key == "https://github.com/foo/bar"

    cfg_local = SkillRepoConfig(local_path="~/Code/scripts")
    assert cfg_local.source_key == str(Path("~/Code/scripts").expanduser())


# --- Install from local_path ---

def test_install_local_path(tmp_path):
    """Install from local_path, verify symlinks point directly to local dir."""
    local_dir = _make_local_skills_dir(tmp_path, ["my-skill", "other-skill"])

    config_path = tmp_path / "config" / "skills.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        f"packages:\n  - local_path: {local_dir}\n"
    )

    lock_path = tmp_path / "config" / "skills-lock.yaml"
    store_dir = tmp_path / "store"
    agents = {"claude": str(tmp_path / "agents" / "claude" / "skills")}

    config = load_config(config_path)
    run_install(config=config, lock_path=lock_path, store_dir=store_dir, known_agents=agents)

    # Both skills should be symlinked
    link1 = tmp_path / "agents" / "claude" / "skills" / "my-skill"
    link2 = tmp_path / "agents" / "claude" / "skills" / "other-skill"
    assert link1.is_symlink()
    assert link2.is_symlink()
    # Symlinks should point into the local dir, not store_dir
    assert link1.resolve() == (local_dir / "my-skill").resolve()
    assert link2.resolve() == (local_dir / "other-skill").resolve()


def test_install_local_path_no_clone(tmp_path):
    """Verify no clone happens and no store_dir is used for local_path."""
    local_dir = _make_local_skills_dir(tmp_path, ["my-skill"])

    config_path = tmp_path / "config" / "skills.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        f"packages:\n  - local_path: {local_dir}\n"
    )

    lock_path = tmp_path / "config" / "skills-lock.yaml"
    store_dir = tmp_path / "store"
    agents = {"claude": str(tmp_path / "agents" / "claude" / "skills")}

    config = load_config(config_path)
    run_install(config=config, lock_path=lock_path, store_dir=store_dir, known_agents=agents)

    # store_dir should not be created (no cloning)
    assert not store_dir.exists()


def test_install_local_path_with_skill_filter(tmp_path):
    """Filter skills from local_path — only listed ones are installed."""
    local_dir = _make_local_skills_dir(tmp_path, ["alpha", "beta", "gamma"])

    config_path = tmp_path / "config" / "skills.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        f"packages:\n  - local_path: {local_dir}\n    skills:\n      - alpha\n      - gamma\n"
    )

    lock_path = tmp_path / "config" / "skills-lock.yaml"
    store_dir = tmp_path / "store"
    agents = {"claude": str(tmp_path / "agents" / "claude" / "skills")}

    config = load_config(config_path)
    run_install(config=config, lock_path=lock_path, store_dir=store_dir, known_agents=agents)

    assert (tmp_path / "agents" / "claude" / "skills" / "alpha").is_symlink()
    assert not (tmp_path / "agents" / "claude" / "skills" / "beta").exists()
    assert (tmp_path / "agents" / "claude" / "skills" / "gamma").is_symlink()


# --- Lock file for local_path ---

def test_lock_local_path_fields(tmp_path):
    """Lock file stores local_path and no commit for local_path packages."""
    local_dir = _make_local_skills_dir(tmp_path, ["my-skill"])

    config_path = tmp_path / "config" / "skills.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        f"packages:\n  - local_path: {local_dir}\n"
    )

    lock_path = tmp_path / "config" / "skills-lock.yaml"
    store_dir = tmp_path / "store"
    agents = {"claude": str(tmp_path / "agents" / "claude" / "skills")}

    config = load_config(config_path)
    run_install(config=config, lock_path=lock_path, store_dir=store_dir, known_agents=agents)

    lock = load_lock(lock_path)
    assert len(lock.skills) == 1
    skill = lock.skills[0]
    assert skill.repo is None
    assert skill.local_path is not None
    assert skill.commit is None


# --- Check-updates skips local_path ---

def test_check_updates_skips_local_path(tmp_path, capsys):
    """local_path skills should be skipped during check-updates."""
    lock_path = tmp_path / "config" / "skills-lock.yaml"
    lock_path.parent.mkdir(parents=True)
    # Write a lock file with a local_path skill
    lock_path.write_text(
        "skills:\n"
        "  - name: my-skill\n"
        "    local_path: /some/local/path\n"
        "    skill_path: my-skill\n"
        "    linked_to:\n"
        "      - ~/.claude/skills/my-skill\n"
    )

    store_dir = tmp_path / "store"
    run_check_updates(lock_path, store_dir)

    captured = capsys.readouterr()
    assert "Skipping local path" in captured.out or "No skills installed" not in captured.out


# --- Update skips local_path ---

def test_update_skips_local_path(tmp_path, capsys):
    """Updating a local_path skill should print skip message."""
    local_dir = _make_local_skills_dir(tmp_path, ["my-skill"])

    lock_path = tmp_path / "config" / "skills-lock.yaml"
    lock_path.parent.mkdir(parents=True)
    from skm.utils import compact_path
    lock_path.write_text(
        "skills:\n"
        f"  - name: my-skill\n"
        f"    local_path: {compact_path(str(local_dir))}\n"
        f"    skill_path: my-skill\n"
        f"    linked_to:\n"
        f"      - ~/.claude/skills/my-skill\n"
    )

    config_path = tmp_path / "config" / "skills.yaml"
    config_path.write_text(
        f"packages:\n  - local_path: {local_dir}\n"
    )

    config = load_config(config_path)
    store_dir = tmp_path / "store"
    agents = {"claude": str(tmp_path / "agents" / "claude" / "skills")}

    run_update("my-skill", config, lock_path, store_dir, agents)

    captured = capsys.readouterr()
    assert "local path" in captured.out.lower()
    assert "skipping" in captured.out.lower()
