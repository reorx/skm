import subprocess

import skm.agents as agents_mod
import skm.types as types_mod
from click.testing import CliRunner

from skm.cli import cli
from skm.commands.install import run_install
from skm.config import load_config
from skm.lock import load_lock


def _make_skill_repo(tmp_path, name, skills_subdir=True):
    """Create a minimal local git repo with a skill."""
    repo = tmp_path / f'repo-{name}'
    repo.mkdir()
    subprocess.run(['git', 'init'], cwd=repo, capture_output=True)
    subprocess.run(['git', 'config', 'user.email', 't@t.com'], cwd=repo, capture_output=True)
    subprocess.run(['git', 'config', 'user.name', 'T'], cwd=repo, capture_output=True)

    if skills_subdir:
        skill_dir = repo / 'skills' / name
    else:
        skill_dir = repo

    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / 'SKILL.md').write_text(f'---\nname: {name}\ndescription: test\n---\nContent\n')
    subprocess.run(['git', 'add', '.'], cwd=repo, capture_output=True)
    subprocess.run(['git', 'commit', '-m', 'init'], cwd=repo, capture_output=True)
    return repo


def test_install_basic(tmp_path):
    """Install a skill from a local repo, verify symlinks and lock file."""
    repo = _make_skill_repo(tmp_path, 'test-skill')

    config_path = tmp_path / 'config' / 'skills.yaml'
    config_path.parent.mkdir(parents=True)
    config_path.write_text(f'packages:\n  - repo: {repo}\n    skills:\n      - test-skill\n')

    lock_path = tmp_path / 'config' / 'skills-lock.yaml'
    store_dir = tmp_path / 'store'

    # Use tmp dirs as agent targets
    agents = {
        'claude': types_mod.AgentSpec(path=str(tmp_path / 'agents' / 'claude' / 'skills')),
        'codex': types_mod.AgentSpec(path=str(tmp_path / 'agents' / 'codex' / 'skills')),
    }

    config = load_config(config_path)
    run_install(
        config=config,
        lock_path=lock_path,
        store_dir=store_dir,
        known_agents=agents,
    )

    # Check symlinks exist
    assert (tmp_path / 'agents' / 'claude' / 'skills' / 'test-skill').is_symlink()
    assert (tmp_path / 'agents' / 'codex' / 'skills' / 'test-skill').is_symlink()

    # Check lock file
    assert lock_path.exists()


def test_install_singleton_skill(tmp_path):
    """Install a singleton skill (SKILL.md at repo root)."""
    repo = _make_skill_repo(tmp_path, 'singleton', skills_subdir=False)

    config_path = tmp_path / 'config' / 'skills.yaml'
    config_path.parent.mkdir(parents=True)
    config_path.write_text(f'packages:\n  - repo: {repo}\n')

    lock_path = tmp_path / 'config' / 'skills-lock.yaml'
    store_dir = tmp_path / 'store'
    agents = {'claude': types_mod.AgentSpec(path=str(tmp_path / 'agents' / 'claude' / 'skills'))}

    config = load_config(config_path)
    run_install(
        config=config,
        lock_path=lock_path,
        store_dir=store_dir,
        known_agents=agents,
    )

    assert (tmp_path / 'agents' / 'claude' / 'skills' / 'singleton').is_symlink()


def test_install_removes_skill_dropped_from_config(tmp_path):
    """When a skill is removed from skills.yaml skills list, its links get cleaned up."""
    repo = tmp_path / 'repo'
    repo.mkdir()
    subprocess.run(['git', 'init'], cwd=repo, capture_output=True)
    subprocess.run(['git', 'config', 'user.email', 't@t.com'], cwd=repo, capture_output=True)
    subprocess.run(['git', 'config', 'user.name', 'T'], cwd=repo, capture_output=True)

    for name in ('skill-a', 'skill-b'):
        skill_dir = repo / 'skills' / name
        skill_dir.mkdir(parents=True)
        (skill_dir / 'SKILL.md').write_text(f'---\nname: {name}\ndescription: test\n---\n')
    subprocess.run(['git', 'add', '.'], cwd=repo, capture_output=True)
    subprocess.run(['git', 'commit', '-m', 'init'], cwd=repo, capture_output=True)

    config_path = tmp_path / 'config' / 'skills.yaml'
    config_path.parent.mkdir(parents=True)
    lock_path = tmp_path / 'config' / 'skills-lock.yaml'
    store_dir = tmp_path / 'store'
    agents = {
        'claude': types_mod.AgentSpec(path=str(tmp_path / 'agents' / 'claude' / 'skills')),
        'codex': types_mod.AgentSpec(path=str(tmp_path / 'agents' / 'codex' / 'skills')),
    }

    # First install: both skills
    config_path.write_text(f'packages:\n  - repo: {repo}\n    skills:\n      - skill-a\n      - skill-b\n')
    config = load_config(config_path)
    run_install(config=config, lock_path=lock_path, store_dir=store_dir, known_agents=agents)

    assert (tmp_path / 'agents' / 'claude' / 'skills' / 'skill-a').is_symlink()
    assert (tmp_path / 'agents' / 'claude' / 'skills' / 'skill-b').is_symlink()
    assert (tmp_path / 'agents' / 'codex' / 'skills' / 'skill-b').is_symlink()

    # Second install: remove skill-b from config
    config_path.write_text(f'packages:\n  - repo: {repo}\n    skills:\n      - skill-a\n')
    config = load_config(config_path)
    run_install(config=config, lock_path=lock_path, store_dir=store_dir, known_agents=agents)

    assert (tmp_path / 'agents' / 'claude' / 'skills' / 'skill-a').is_symlink()
    assert not (tmp_path / 'agents' / 'claude' / 'skills' / 'skill-b').exists()
    assert not (tmp_path / 'agents' / 'codex' / 'skills' / 'skill-b').exists()


def test_install_removes_links_for_excluded_agent(tmp_path):
    """When agents config changes to exclude an agent, stale links get removed."""
    repo = _make_skill_repo(tmp_path, 'my-skill')

    config_path = tmp_path / 'config' / 'skills.yaml'
    config_path.parent.mkdir(parents=True)
    lock_path = tmp_path / 'config' / 'skills-lock.yaml'
    store_dir = tmp_path / 'store'
    agents = {
        'claude': types_mod.AgentSpec(path=str(tmp_path / 'agents' / 'claude' / 'skills')),
        'codex': types_mod.AgentSpec(path=str(tmp_path / 'agents' / 'codex' / 'skills')),
    }

    # First install: all agents
    config_path.write_text(f'packages:\n  - repo: {repo}\n    skills:\n      - my-skill\n')
    config = load_config(config_path)
    run_install(config=config, lock_path=lock_path, store_dir=store_dir, known_agents=agents)

    assert (tmp_path / 'agents' / 'claude' / 'skills' / 'my-skill').is_symlink()
    assert (tmp_path / 'agents' / 'codex' / 'skills' / 'my-skill').is_symlink()

    # Second install: exclude codex
    config_path.write_text(
        f'packages:\n  - repo: {repo}\n    skills:\n      - my-skill\n    agents:\n      excludes:\n        - codex\n'
    )
    config = load_config(config_path)
    run_install(config=config, lock_path=lock_path, store_dir=store_dir, known_agents=agents)

    assert (tmp_path / 'agents' / 'claude' / 'skills' / 'my-skill').is_symlink()
    assert not (tmp_path / 'agents' / 'codex' / 'skills' / 'my-skill').exists()


def test_install_uses_env_override_path_in_lock(tmp_path, monkeypatch):
    repo = _make_skill_repo(tmp_path, 'my-skill')

    config_path = tmp_path / 'config' / 'skills.yaml'
    config_path.parent.mkdir(parents=True)
    config_path.write_text(f'agents:\n  default:\n    - claude\npackages:\n  - repo: {repo}\n    skills:\n      - my-skill\n')

    lock_path = tmp_path / 'config' / 'skills-lock.yaml'
    store_dir = tmp_path / 'store'

    home = tmp_path / 'home'
    claude_config = home / '.config' / 'claude'
    claude_skills = claude_config / 'skills'

    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(claude_config))
    monkeypatch.setattr('skm.cli._resolve_default_agents', lambda config, agents_dir=None: agents_mod.resolve_agent_specs(config.agents))

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            '--config',
            str(config_path),
            '--lock',
            str(lock_path),
            '--store',
            str(store_dir),
            'install',
        ],
    )

    assert result.exit_code == 0, result.output
    assert (claude_skills / 'my-skill').is_symlink()

    config = load_config(config_path)
    assert config.agents.default == ['claude']

    lock = load_lock(lock_path)
    assert lock.skills[0].linked_to == ['~/.config/claude/skills/my-skill']
