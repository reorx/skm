from io import StringIO
from pathlib import Path

from ruamel.yaml import YAML, CommentedMap, CommentedSeq

from skm.types import SkillRepoConfig, SkmConfig

_yaml = YAML()
_yaml.default_flow_style = False
_yaml.indent(mapping=2, sequence=4, offset=2)

# Stash raw YAML data keyed by config file path, so save_config can round-trip.
_raw_cache: dict[Path, CommentedMap] = {}


def load_config(config_path: Path) -> SkmConfig:
    if not config_path.exists():
        raise FileNotFoundError(f'Config file not found: {config_path}')

    data = _yaml.load(config_path)

    if not data:
        raise ValueError(f'Config file is empty: {config_path}')

    if not isinstance(data, dict):
        raise ValueError(f"Config must be a YAML dict with 'packages' key, got {type(data).__name__}: {config_path}")

    # Cache the raw CommentedMap for round-trip saving
    _raw_cache[config_path.resolve()] = data

    return SkmConfig(**data)


def _to_commented(obj):
    """Convert plain dicts/lists to ruamel.yaml CommentedMap/CommentedSeq."""
    if isinstance(obj, dict):
        cm = CommentedMap()
        for k, v in obj.items():
            cm[k] = _to_commented(v)
        return cm
    if isinstance(obj, list):
        cs = CommentedSeq()
        for item in obj:
            cs.append(_to_commented(item))
        return cs
    return obj


def _raw_pkg_source_key(raw_pkg: dict) -> str:
    """Extract source key from a raw YAML package dict."""
    if 'local_path' in raw_pkg:
        return str(Path(raw_pkg['local_path']).expanduser())
    return raw_pkg.get('repo', '')


def _plain_equal(raw_val, new_val) -> bool:
    """Compare a ruamel.yaml value to a plain Python value, ignoring comment metadata."""
    if isinstance(new_val, dict):
        if not isinstance(raw_val, dict) or set(raw_val.keys()) != set(new_val.keys()):
            return False
        return all(_plain_equal(raw_val[k], new_val[k]) for k in new_val)
    if isinstance(new_val, list):
        if not isinstance(raw_val, list) or len(raw_val) != len(new_val):
            return False
        return all(_plain_equal(r, n) for r, n in zip(raw_val, new_val))
    return raw_val == new_val


def _merge_packages(raw_packages: CommentedSeq, new_packages: list[dict]) -> CommentedSeq:
    """Merge new package data into raw packages, preserving original items when unchanged.

    Modifies raw_packages in-place to preserve ruamel.yaml formatting metadata.
    """
    # Index raw packages by source key
    raw_by_key = {}
    for i, raw_pkg in enumerate(raw_packages):
        raw_by_key[_raw_pkg_source_key(raw_pkg)] = (i, raw_pkg)

    # Build the new list of items, reusing raw items where possible
    new_items = []
    for new_pkg in new_packages:
        pkg_model = SkillRepoConfig(**new_pkg)
        key = pkg_model.source_key
        entry = raw_by_key.get(key)

        if entry is not None:
            _, raw_pkg = entry
            if _plain_equal(raw_pkg, new_pkg):
                # Unchanged — keep original raw item as-is
                new_items.append(raw_pkg)
            else:
                # Changed — rebuild from new data
                new_items.append(_to_commented(new_pkg))
        else:
            # Brand new package
            new_items.append(_to_commented(new_pkg))

    # Replace contents of raw_packages in-place
    raw_packages.clear()
    for item in new_items:
        raw_packages.append(item)

    return raw_packages


def save_config(config: SkmConfig, config_path: Path) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    resolved = config_path.resolve()
    raw = _raw_cache.get(resolved)

    new_data = config.model_dump(exclude_none=True)

    if raw is not None:
        # Merge packages preserving original raw items
        raw['packages'] = _merge_packages(raw['packages'], new_data['packages'])
        # Sync other top-level keys — only update if changed
        for key in new_data:
            if key != 'packages':
                if key not in raw or not _plain_equal(raw[key], new_data[key]):
                    raw[key] = _to_commented(new_data[key])
        # Remove keys that were dropped
        for key in list(raw.keys()):
            if key not in new_data:
                del raw[key]
        out = raw
    else:
        out = _to_commented(new_data)

    buf = StringIO()
    _yaml.dump(out, buf)
    config_path.write_text(buf.getvalue())

    # Update cache so sequential saves without re-loading work correctly
    _raw_cache[resolved] = out


def upsert_package(config: SkmConfig, new_pkg: SkillRepoConfig) -> SkillRepoConfig | None:
    """Upsert a package into config. Returns existing package if found with skills: None, else None."""
    new_key = new_pkg.source_key

    for i, existing in enumerate(config.packages):
        if existing.source_key == new_key:
            # Found existing package
            if existing.skills is None:
                # Existing has all skills — keep existing agents config
                return existing

            if new_pkg.skills is not None:
                # Merge skills: union old + new, deduplicate
                merged = list(dict.fromkeys(existing.skills + new_pkg.skills))
                existing.skills = merged

            return None

    # Not found: append
    config.packages.append(new_pkg)
    return None
