import pytest
from skm.types import SkillRepoConfig, AgentsConfig


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
