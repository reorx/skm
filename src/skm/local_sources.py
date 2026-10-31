"""Device-local skill sources: symlinks under `<config dir>/local_sources/`.

The directory ignores itself in git, so a config dir kept in a shared repo
carries skills.yaml to every device while each device keeps its own extra
skills. Every usable entry is installed like a `local_path:` package.
"""

from pathlib import Path

from skm.types import LOCAL_SOURCES_DIRNAME, SkillRepoConfig, SkmConfig

GITIGNORE_CONTENT = '*\n'


def get_local_sources_dir(config_path: Path) -> Path:
    """Local sources live next to skills.yaml, so --config also isolates them."""
    return config_path.expanduser().absolute().parent / LOCAL_SOURCES_DIRNAME


def scan_local_sources(sources_dir: Path) -> tuple[list[Path], list[Path]]:
    """Return (usable, broken) entries sorted by name; dotfiles are ignored.

    An entry is usable when it is (or links to) a directory. Dangling links and
    plain files are broken.
    """
    if not sources_dir.is_dir():
        return [], []
    usable: list[Path] = []
    broken: list[Path] = []
    for entry in sorted(sources_dir.iterdir()):
        if entry.name.startswith('.'):
            continue
        if entry.is_dir():
            usable.append(entry)
        else:
            broken.append(entry)
    return usable, broken


def find_local_source(sources_dir: Path, target: Path) -> Path | None:
    """Return the entry that already points at target, if any."""
    resolved = target.resolve()
    usable, _ = scan_local_sources(sources_dir)
    for entry in usable:
        if entry.resolve() == resolved:
            return entry
    return None


def add_local_source(sources_dir: Path, target: Path) -> tuple[Path, bool]:
    """Link target into sources_dir. Returns (link path, created).

    The link points at the absolute, resolved target so it works from any cwd.
    Reuses an existing entry for the same target; a name taken by another
    target gets a numeric suffix.
    """
    target = target.expanduser().resolve()
    existing = find_local_source(sources_dir, target)
    if existing is not None:
        return existing, False

    sources_dir.mkdir(parents=True, exist_ok=True)
    gitignore = sources_dir / '.gitignore'
    if not gitignore.exists():
        gitignore.write_text(GITIGNORE_CONTENT)

    link = _free_entry_path(sources_dir, target.name)
    link.symlink_to(target, target_is_directory=True)
    return link, True


def _free_entry_path(sources_dir: Path, name: str) -> Path:
    candidate = sources_dir / name
    suffix = 2
    while candidate.exists() or candidate.is_symlink():
        candidate = sources_dir / f'{name}-{suffix}'
        suffix += 1
    return candidate


def is_local_source_path(sources_dir: Path, local_path: str) -> bool:
    """Whether a lock/config local_path is an entry of sources_dir."""
    return Path(local_path).expanduser().absolute().parent == sources_dir


def find_configured_duplicate(config: SkmConfig, entry: Path) -> SkillRepoConfig | None:
    """Return the skills.yaml local_path package that points at the same directory."""
    resolved = entry.resolve()
    for pkg in config.packages:
        if pkg.is_local and Path(pkg.local_path).expanduser().resolve() == resolved:
            return pkg
    return None
