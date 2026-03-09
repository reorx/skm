from pathlib import Path

import click

from skm.git import fetch, get_head_commit, get_remote_head_commit, get_log_between, repo_url_to_dirname
from skm.lock import load_lock


def run_check_updates(lock_path: Path, store_dir: Path) -> None:
    lock = load_lock(lock_path)

    if not lock.skills:
        click.echo("No skills installed.")
        return

    # Group by repo, skip local_path packages
    repos: dict[str, list] = {}
    for skill in lock.skills:
        if skill.repo is None:
            click.echo(f"Skipping local path package: {skill.name}")
            continue
        repos.setdefault(skill.repo, []).append(skill)

    has_updates = False

    for repo_url, skills in repos.items():
        repo_dir_name = repo_url_to_dirname(repo_url)
        repo_path = store_dir / repo_dir_name

        if not repo_path.exists():
            click.echo(click.style(f"Warning: Repo not found locally: {repo_url}", fg="red"))
            continue

        click.echo(f"Fetching {repo_url}...")
        fetch(repo_path)

        local_commit = skills[0].commit  # all skills from same repo share commit
        remote_commit = get_remote_head_commit(repo_path)

        if local_commit == remote_commit:
            click.echo(f"  Up to date")
            continue

        has_updates = True
        log = get_log_between(repo_path, local_commit, remote_commit)
        skill_names = ", ".join(s.name for s in skills)
        click.echo(f"  Updates available for: {skill_names}")
        click.echo(f"  {local_commit[:8]} -> {remote_commit[:8]}")
        if log:
            for line in log.splitlines():
                click.echo(f"    {line}")

    if not has_updates:
        click.echo("\nAll skills are up to date.")
