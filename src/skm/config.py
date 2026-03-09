from pathlib import Path

import yaml

from skm.types import SkillRepoConfig


def load_config(config_path: Path) -> list[SkillRepoConfig]:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    text = config_path.read_text()
    data = yaml.safe_load(text)

    if not data:
        raise ValueError(f"Config file is empty: {config_path}")

    return [SkillRepoConfig(**item) for item in data]
