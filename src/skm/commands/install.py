from pathlib import Path

import click

from skm.config import load_config
from skm.detect import detect_skills
from skm.git import clone_or_pull, get_head_commit, repo_url_to_dirname
from skm.linker import link_skill, unlink_skill, resolve_target_agents
from skm.lock import load_lock, save_lock
from skm.types import InstalledSkill, LockFile


def run_install(
    config_path: Path,
    lock_path: Path,
    store_dir: Path,
    known_agents: dict[str, str],
) -> None:
    configs = load_config(config_path)
    lock = load_lock(lock_path)
    new_lock_skills: list[InstalledSkill] = []

    # Track which skills are configured (for removal detection)
    configured_skill_names: set[str] = set()

    for repo_config in configs:
        repo_dir_name = repo_url_to_dirname(repo_config.repo)
        repo_path = store_dir / repo_dir_name

        # Clone or pull latest
        if repo_path.exists():
            click.echo(f"Updating {repo_config.repo}...")
        else:
            click.echo(f"Cloning {repo_config.repo}...")
        clone_or_pull(repo_config.repo, repo_path)

        commit = get_head_commit(repo_path)
        detected = detect_skills(repo_path)
        target_agents = resolve_target_agents(repo_config.agents, known_agents)

        # Filter to requested skills (if specified)
        if repo_config.skills is not None:
            requested = set(repo_config.skills)
            skills_to_install = [s for s in detected if s.name in requested]
            missing = requested - {s.name for s in skills_to_install}
            if missing:
                click.echo(f"  Warning: skills not found in repo: {missing}")
        else:
            # No filter → install all detected skills
            skills_to_install = detected

        for skill in skills_to_install:
            configured_skill_names.add(skill.name)
            linked_paths = []

            for agent_name, agent_dir in target_agents.items():
                link = link_skill(skill.path, skill.name, agent_dir)
                linked_paths.append(str(link))
                click.echo(f"  Linked {skill.name} -> [{agent_name}] {link}")

            new_lock_skills.append(InstalledSkill(
                name=skill.name,
                repo=repo_config.repo,
                commit=commit,
                skill_path=skill.relative_path,
                linked_to=linked_paths,
            ))

    # Remove skills that were in old lock but no longer in config
    for old_skill in lock.skills:
        if old_skill.name not in configured_skill_names:
            click.echo(f"  Removing {old_skill.name} (no longer in config)")
            for link_path in old_skill.linked_to:
                p = Path(link_path)
                if p.is_symlink():
                    p.unlink()

    new_lock = LockFile(skills=new_lock_skills)
    save_lock(new_lock, lock_path)
    click.echo(f"Lock file updated: {lock_path}")
