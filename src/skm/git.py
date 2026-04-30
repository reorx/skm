import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import click

ALLOWED_URL_RE = re.compile(r'^(https?://|git@|/)')
SHA_RE = re.compile(r'^[0-9a-f]{7,40}$')


def run_cmd(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a command, raising click.ClickException with stdout/stderr on failure."""
    result = subprocess.run(cmd, capture_output=True, **kwargs)
    if result.returncode != 0:
        parts = [f"Command failed: {' '.join(cmd)}"]
        stdout = result.stdout.decode() if isinstance(result.stdout, bytes) else (result.stdout or "")
        stderr = result.stderr.decode() if isinstance(result.stderr, bytes) else (result.stderr or "")
        if stdout.strip():
            parts.append(f"stdout: {stdout.strip()}")
        if stderr.strip():
            parts.append(f"stderr: {stderr.strip()}")
        raise click.ClickException("\n".join(parts))
    return result


def repo_url_to_dirname(repo_url: str) -> str:
    """Convert a repo URL to a filesystem-safe directory name."""
    parsed = urlparse(repo_url)
    # e.g. "github.com/vercel-labs/agent-skills" -> "github.com_vercel-labs_agent-skills"
    path = parsed.path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    return f"{parsed.hostname}_{path.replace('/', '_')}"


def _validate_repo_url(repo_url: str) -> None:
    if not ALLOWED_URL_RE.match(repo_url):
        raise ValueError(f"Disallowed repo URL: {repo_url!r} (only https:// and git@ are supported)")


def _validate_sha(sha: str) -> None:
    if not SHA_RE.match(sha):
        raise ValueError(f"Invalid commit SHA: {sha!r}")


def clone_or_pull(repo_url: str, dest: Path, clone_strategy: str | None = None) -> None:
    """Clone repo if not present, otherwise pull latest."""
    if dest.exists() and (dest / ".git").exists():
        run_cmd(["git", "pull", "--ff-only"], cwd=dest)
    else:
        _validate_repo_url(repo_url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["git", "clone", "--filter=blob:none"]
        if clone_strategy == "shallow":
            cmd.extend(["--depth", "1"])
        cmd.extend([repo_url, str(dest)])
        run_cmd(cmd)


def get_head_commit(repo_path: Path) -> str:
    """Get the HEAD commit SHA of a repo."""
    result = run_cmd(["git", "rev-parse", "HEAD"], cwd=repo_path, text=True)
    return result.stdout.strip()


def get_log_since(repo_path: Path, since_commit: str, max_count: int = 20) -> str:
    """Get git log from a commit to HEAD."""
    _validate_sha(since_commit)
    result = run_cmd(
        ["git", "log", f"{since_commit}..HEAD", "--oneline", f"--max-count={max_count}"],
        cwd=repo_path, text=True,
    )
    return result.stdout.strip()


def fetch(repo_path: Path) -> None:
    """Fetch latest from remote without merging."""
    run_cmd(["git", "fetch"], cwd=repo_path)


def get_remote_head_commit(repo_path: Path) -> str:
    """Get the remote HEAD commit after fetch."""
    try:
        result = run_cmd(["git", "rev-parse", "origin/HEAD"], cwd=repo_path, text=True)
        return result.stdout.strip()
    except click.ClickException:
        pass
    # fallback: try origin/main or origin/master
    for branch in ["origin/main", "origin/master"]:
        try:
            result = run_cmd(["git", "rev-parse", branch], cwd=repo_path, text=True)
            return result.stdout.strip()
        except click.ClickException:
            pass
    raise click.ClickException(f"Cannot determine remote HEAD for {repo_path}")


def get_log_between(repo_path: Path, old_commit: str, new_commit: str, max_count: int = 20) -> str:
    """Get git log between two commits."""
    _validate_sha(old_commit)
    _validate_sha(new_commit)
    result = run_cmd(
        ["git", "log", f"{old_commit}..{new_commit}", "--oneline", f"--max-count={max_count}"],
        cwd=repo_path, text=True,
    )
    return result.stdout.strip()
