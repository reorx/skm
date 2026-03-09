from pathlib import Path

import yaml

from skm.types import LockFile, InstalledSkill


def load_lock(lock_path: Path) -> LockFile:
    if not lock_path.exists():
        return LockFile()

    data = yaml.safe_load(lock_path.read_text())
    if not data or "skills" not in data:
        return LockFile()

    return LockFile(skills=[InstalledSkill(**s) for s in data["skills"]])


def save_lock(lock: LockFile, lock_path: Path) -> None:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    data = {"skills": [s.model_dump() for s in lock.skills]}
    lock_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
