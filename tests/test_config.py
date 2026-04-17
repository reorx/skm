import pytest
from skm.config import load_config, save_config, upsert_package, _raw_cache
from skm.types import SkillRepoConfig


EXAMPLE_YAML = """\
packages:
  - repo: https://github.com/vercel-labs/agent-skills
    skills:
      - react-best-practices
      - web-design-guidelines
    agents:
      excludes:
        - openclaw
  - repo: https://github.com/blader/humanizer
"""

EXAMPLE_WITH_AGENTS_DEFAULT = """\
agents:
  default:
    - claude
    - standard
  override:
    codex:
      path: ~/.custom-codex/skills

packages:
  - repo: https://github.com/vercel-labs/agent-skills
"""


def test_load_config(tmp_path):
    config_file = tmp_path / 'skills.yaml'
    config_file.write_text(EXAMPLE_YAML)
    config = load_config(config_file)
    assert len(config.packages) == 2
    assert config.packages[0].repo == 'https://github.com/vercel-labs/agent-skills'
    assert config.packages[0].skills == ['react-best-practices', 'web-design-guidelines']
    assert config.packages[0].agents.excludes == ['openclaw']
    assert config.packages[1].repo == 'https://github.com/blader/humanizer'
    assert config.packages[1].skills is None
    assert config.packages[1].agents is None
    assert config.agents is None


def test_load_config_with_agents_default(tmp_path):
    config_file = tmp_path / 'skills.yaml'
    config_file.write_text(EXAMPLE_WITH_AGENTS_DEFAULT)
    config = load_config(config_file)
    assert config.agents is not None
    assert config.agents.default == ['claude', 'standard']
    assert config.agents.override['codex'].path == '~/.custom-codex/skills'
    assert len(config.packages) == 1


def test_load_config_unknown_agent(tmp_path):
    config_file = tmp_path / 'skills.yaml'
    config_file.write_text('agents:\n  default:\n    - nonexistent\npackages:\n  - repo: https://example.com/repo\n')
    with pytest.raises(Exception, match='Unknown agents'):
        load_config(config_file)


def test_load_config_unknown_override_agent(tmp_path):
    config_file = tmp_path / 'skills.yaml'
    config_file.write_text(
        'agents:\n'
        '  override:\n'
        '    unknown-agent:\n'
        '      path: ~/.unknown/skills\n'
        'packages:\n'
        '  - repo: https://example.com/repo\n'
    )
    with pytest.raises(Exception, match="Unknown agent 'unknown-agent' in agents.override"):
        load_config(config_file)


def test_load_config_unknown_package_include_agent_is_allowed(tmp_path):
    config_file = tmp_path / 'skills.yaml'
    config_file.write_text(
        'agents:\n'
        '  default:\n'
        '    - claude\n'
        'packages:\n'
        '  - repo: https://example.com/repo\n'
        '    agents:\n'
        '      includes:\n'
        '        - codex\n'
    )
    config = load_config(config_file)
    assert config.packages[0].agents.includes == ['codex']


def test_load_config_unknown_package_exclude_agent_is_allowed(tmp_path):
    config_file = tmp_path / 'skills.yaml'
    config_file.write_text(
        'agents:\n'
        '  default:\n'
        '    - claude\n'
        'packages:\n'
        '  - repo: https://example.com/repo\n'
        '    agents:\n'
        '      excludes:\n'
        '        - codex\n'
    )
    config = load_config(config_file)
    assert config.packages[0].agents.excludes == ['codex']


def test_load_config_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / 'nonexistent.yaml')


def test_load_config_empty_file(tmp_path):
    config_file = tmp_path / 'skills.yaml'
    config_file.write_text('')
    with pytest.raises(ValueError, match='empty'):
        load_config(config_file)


ROUNDTRIP_YAML = """\
# My skills config
packages:
  # agent skills from vercel
  - repo: https://github.com/vercel-labs/agent-skills
    skills:
      - react-best-practices
      - web-design-guidelines
    agents:
      excludes:
        - openclaw
  - repo: https://github.com/blader/humanizer
"""

ROUNDTRIP_YAML_WITH_AGENTS = """\
# Global agent defaults
agents:
  default:
    - claude
    - standard

# My skills config
packages:
  - repo: https://github.com/vercel-labs/agent-skills
"""


def test_save_config_preserves_comments_and_key_order(tmp_path):
    """Load a config with comments, save it back unchanged, verify comments and order are preserved."""
    config_file = tmp_path / 'skills.yaml'
    config_file.write_text(ROUNDTRIP_YAML)

    config = load_config(config_file)
    save_config(config, config_file)

    result = config_file.read_text()
    assert result == ROUNDTRIP_YAML


def test_save_config_preserves_comments_after_upsert(tmp_path):
    """Load config, add a new package via upsert, verify existing comments survive."""
    config_file = tmp_path / 'skills.yaml'
    config_file.write_text(ROUNDTRIP_YAML)

    config = load_config(config_file)
    new_pkg = SkillRepoConfig(repo='https://github.com/new/repo', skills=['some-skill'])
    upsert_package(config, new_pkg)
    save_config(config, config_file)

    result = config_file.read_text()
    # Top-level comment preserved
    assert '# My skills config' in result
    # Per-package comment preserved
    assert '# agent skills from vercel' in result
    # Key order: packages still comes first (no agents key in this config)
    lines = result.strip().splitlines()
    assert lines[0] == '# My skills config'
    assert lines[1] == 'packages:'
    # New package appended
    assert 'https://github.com/new/repo' in result


def test_save_config_preserves_key_order_agents_before_packages(tmp_path):
    """When agents: comes before packages: in the original, that order is preserved."""
    config_file = tmp_path / 'skills.yaml'
    config_file.write_text(ROUNDTRIP_YAML_WITH_AGENTS)

    config = load_config(config_file)
    save_config(config, config_file)

    result = config_file.read_text()
    assert result == ROUNDTRIP_YAML_WITH_AGENTS
    # Verify agents comes before packages
    agents_pos = result.index('agents:')
    packages_pos = result.index('packages:')
    assert agents_pos < packages_pos


def test_save_config_without_prior_load(tmp_path):
    """save_config works even without a prior load (no cached raw data)."""
    config_file = tmp_path / 'skills.yaml'
    # Clear cache to simulate no prior load
    _raw_cache.clear()

    config = SkillRepoConfig(repo='https://github.com/example/repo')
    from skm.types import SkmConfig

    skm_config = SkmConfig(packages=[config])
    save_config(skm_config, config_file)

    result = config_file.read_text()
    assert 'https://github.com/example/repo' in result
    # Verify it can be loaded back
    loaded = load_config(config_file)
    assert len(loaded.packages) == 1


def test_save_config_sequential_saves_without_reload(tmp_path):
    """Two sequential saves without re-loading should both work correctly."""
    config_file = tmp_path / 'skills.yaml'
    config_file.write_text(ROUNDTRIP_YAML)

    # First load + upsert + save
    config = load_config(config_file)
    upsert_package(config, SkillRepoConfig(repo='https://github.com/new/repo-a', skills=['skill-a']))
    save_config(config, config_file)

    # Second upsert + save without re-loading
    upsert_package(config, SkillRepoConfig(repo='https://github.com/new/repo-b', skills=['skill-b']))
    save_config(config, config_file)

    result = config_file.read_text()
    # Both new packages present
    assert 'https://github.com/new/repo-a' in result
    assert 'https://github.com/new/repo-b' in result
    # Original comments preserved
    assert '# My skills config' in result
    assert '# agent skills from vercel' in result
    # Verify it loads back correctly
    loaded = load_config(config_file)
    assert len(loaded.packages) == 4
