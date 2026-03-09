import pytest
from pathlib import Path
from skm.config import load_config


EXAMPLE_YAML = """\
- repo: https://github.com/vercel-labs/agent-skills
  skills:
    - react-best-practices
    - web-design-guidelines
  agents:
    excludes:
      - openclaw
- repo: https://github.com/blader/humanizer
"""


def test_load_config(tmp_path):
    config_file = tmp_path / "skills.yaml"
    config_file.write_text(EXAMPLE_YAML)
    configs = load_config(config_file)
    assert len(configs) == 2
    assert configs[0].repo == "https://github.com/vercel-labs/agent-skills"
    assert configs[0].skills == ["react-best-practices", "web-design-guidelines"]
    assert configs[0].agents.excludes == ["openclaw"]
    assert configs[1].repo == "https://github.com/blader/humanizer"
    assert configs[1].skills is None
    assert configs[1].agents is None


def test_load_config_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nonexistent.yaml")


def test_load_config_empty_file(tmp_path):
    config_file = tmp_path / "skills.yaml"
    config_file.write_text("")
    with pytest.raises(ValueError, match="empty"):
        load_config(config_file)
