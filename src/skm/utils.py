from pathlib import Path


def same_install_location(left: str, right: str) -> bool:
    """Compare directory entries without following the skill symlink itself."""
    left_path = Path(left).expanduser()
    right_path = Path(right).expanduser()
    if left_path == right_path:
        return True
    # Distinct agent links can point at the same source; only their parents
    # should be followed when deciding whether cleanup would remove a new link.
    return (
        left_path.name == right_path.name
        and left_path.parent.exists()
        and right_path.parent.exists()
        and left_path.parent.samefile(right_path.parent)
    )


def compact_path(p: str) -> str:
    """Replace the user's home directory prefix with ~."""
    home = str(Path.home())
    if p.startswith(home):
        return '~' + p[len(home) :]
    return p
