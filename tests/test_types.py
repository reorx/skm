import pytest

import skm.agents as agents_mod
from skm.types import AgentsConfig, GlobalAgentsConfig, SkillRepoConfig


def test_skill_repo_config_minimal():
    """Repo with no skills listed and no agents config."""
    cfg = SkillRepoConfig(repo="https://github.com/blader/humanizer")
    assert cfg.repo == "https://github.com/blader/humanizer"
    assert cfg.skills is None
    assert cfg.agents is None


def test_skill_repo_config_with_skills():
    cfg = SkillRepoConfig(
        repo="https://github.com/vercel-labs/agent-skills",
        skills=["react-best-practices", "react-native-skills"],
    )
    assert cfg.skills == ["react-best-practices", "react-native-skills"]


def test_agents_config_excludes():
    agents = AgentsConfig(excludes=["openclaw"])
    assert agents.excludes == ["openclaw"]
    assert agents.includes is None


def test_agents_config_includes():
    agents = AgentsConfig(includes=["claude", "codex"])
    assert agents.includes == ["claude", "codex"]
    assert agents.excludes is None


def test_skill_repo_config_with_agents():
    cfg = SkillRepoConfig(
        repo="https://github.com/vercel-labs/agent-skills",
        skills=["react-best-practices"],
        agents=AgentsConfig(excludes=["openclaw"]),
    )
    assert cfg.agents.excludes == ["openclaw"]


def test_resolve_agent_specs_uses_parent_env_override(monkeypatch, tmp_path):
    home = tmp_path / 'home'
    claude_config_dir = home / '.claude-custom'

    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(claude_config_dir))

    agents = agents_mod.resolve_agent_specs(None)
    assert agents['claude'].path == str(claude_config_dir / 'skills')


def test_get_all_agent_specs_defaults():
    specs = agents_mod.get_all_agent_specs(None)
    assert specs['standard'].install_mode == 'materialize'
    assert specs['claude'].parent_env_var == 'CLAUDE_CONFIG_DIR'
    assert specs['pi'].parent_env_var == 'PI_CODING_AGENT_DIR'


def test_get_all_agent_specs_applies_override():
    specs = agents_mod.get_all_agent_specs(
        GlobalAgentsConfig(
            override={
                'codex': {
                    'path': '~/.custom-codex/skills',
                    'install_mode': 'materialize',
                }
            }
        )
    )

    assert specs['codex'].path == '~/.custom-codex/skills'
    assert specs['codex'].install_mode == 'materialize'
    assert specs['codex'].parent_env_var is None


def test_get_all_agent_specs_rejects_unknown_override():
    with pytest.raises(ValueError, match="Unknown agent 'unknown-agent' in agents.override"):
        agents_mod.get_all_agent_specs(GlobalAgentsConfig(override={'unknown-agent': {'path': '~/.unknown/skills'}}))
