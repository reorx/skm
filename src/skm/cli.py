from pathlib import Path

import click

from skm.config import load_config, save_config, upsert_package
from skm.tui import interactive_multi_select
from skm.types import (
    CONFIG_PATH,
    LOCK_PATH,
    STORE_DIR,
    KNOWN_AGENTS,
    AgentsConfig,
    SkillRepoConfig,
    SkmConfig,
)


@click.group()
@click.option('--config', 'config_path', type=click.Path(), default=None, help='Path to skills.yaml config file.')
@click.option('--store', 'store_dir', type=click.Path(), default=None, help='Path to skill store directory.')
@click.option('--lock', 'lock_path', type=click.Path(), default=None, help='Path to skills-lock.yaml lock file.')
@click.option(
    '--agents-dir',
    'agents_dir',
    type=click.Path(),
    default=None,
    help='Base directory for agent skill symlinks (overrides all known agents).',
)
@click.pass_context
def cli(ctx, config_path, store_dir, lock_path, agents_dir):
    """SKM - Skill Manager for AI coding agents."""
    ctx.ensure_object(dict)
    ctx.obj['config_path'] = Path(config_path) if config_path else CONFIG_PATH
    ctx.obj['lock_path'] = Path(lock_path) if lock_path else LOCK_PATH
    ctx.obj['store_dir'] = Path(store_dir) if store_dir else STORE_DIR
    ctx.obj['agents_dir'] = agents_dir


def _expand_agents(agents_dir: str | None = None, default_agents: list[str] | None = None) -> dict[str, str]:
    agents = KNOWN_AGENTS
    if default_agents is not None:
        agents = {k: v for k, v in agents.items() if k in default_agents}
    if agents_dir:
        base = Path(agents_dir)
        return {name: str(base / name) for name in agents}
    return {name: str(Path(path).expanduser()) for name, path in agents.items()}


@cli.command()
@click.argument('source', required=False, default=None)
@click.argument('skill_name', required=False, default=None)
@click.option(
    '--force', is_flag=True, default=False, help='Override existing non-symlink skill directories without prompting.'
)
@click.option('--agents-includes', default=None, help='Comma-separated agents to include (skips interactive).')
@click.option('--agents-excludes', default=None, help='Comma-separated agents to exclude (skips interactive).')
@click.pass_context
def install(ctx, source, skill_name, force, agents_includes, agents_excludes):
    """Install skills from config or directly from a source.

    SOURCE can be a repo URL or local path. If omitted, installs from config.
    SKILL_NAME optionally specifies a single skill to install from the source.
    """
    from skm.commands.install import run_install, run_install_package
    from skm.detect import detect_skills
    from skm.git import clone_or_pull, repo_url_to_dirname
    from skm.lock import load_lock

    if source is None:
        # Existing behavior: install from config
        config = load_config(ctx.obj['config_path'])
        default_agents = config.agents.default if config.agents else None
        agents = _expand_agents(ctx.obj['agents_dir'], default_agents)
        run_install(
            config=config,
            lock_path=ctx.obj['lock_path'],
            store_dir=ctx.obj['store_dir'],
            known_agents=agents,
            force=force,
        )
        return

    # --- Source provided: direct install flow ---

    if agents_includes and agents_excludes:
        raise click.ClickException('Cannot specify both --agents-includes and --agents-excludes')

    # Resolve source
    source_path = Path(source).expanduser()
    if source_path.is_dir():
        repo_path = source_path
        is_local = True
    else:
        dest = ctx.obj['store_dir'] / repo_url_to_dirname(source)
        clone_or_pull(source, dest)
        repo_path = dest
        is_local = False

    # Load or create config
    config_path = ctx.obj['config_path']
    if config_path.exists():
        config = load_config(config_path)
    else:
        config = SkmConfig(packages=[])

    # Check if existing package with skills: None and specific skill_name
    if skill_name:
        source_key = str(source_path) if is_local else source
        existing_pkg = _find_package_by_source(config, source_key, is_local)
        if existing_pkg and existing_pkg.skills is None:
            # Check if skill is already installed (in lock file)
            lock = load_lock(ctx.obj['lock_path'])
            skill_installed = any(
                s.name == skill_name and (s.local_path or s.repo) and _source_matches(s, source_key, is_local)
                for s in lock.skills
            )
            if skill_installed:
                click.echo(f'Skill "{skill_name}" is already installed from this source (all skills configured).')
                return
            else:
                # Re-install just this package to pick up new skills
                default_agents = config.agents.default if config.agents else None
                agents = _expand_agents(ctx.obj['agents_dir'], default_agents)
                run_install_package(
                    repo_config=existing_pkg,
                    lock_path=ctx.obj['lock_path'],
                    store_dir=ctx.obj['store_dir'],
                    known_agents=agents,
                    force=force,
                )
                return

    # Detect skills
    detected = detect_skills(repo_path)
    if not detected:
        click.echo('No skills found in source.')
        return

    # Select skills
    if skill_name:
        matched = [s for s in detected if s.name == skill_name]
        if not matched:
            raise click.ClickException(
                f'Skill "{skill_name}" not found in source. Available: {", ".join(s.name for s in detected)}'
            )
        selected_skills = matched
    else:
        labels = [f'{s.name}  ({s.relative_path})' for s in detected]
        indices = interactive_multi_select(labels, header='Select skills to install:')
        if indices is None:
            click.echo('Cancelled.')
            return
        selected_skills = [detected[i] for i in indices]

    if not selected_skills:
        click.echo('No skills selected.')
        return

    # Determine agents config
    # Check if repo already exists in config — if so, reuse its agents setting
    existing_pkg = _find_package_by_source(
        config,
        SkillRepoConfig(
            repo=source if not is_local else None, local_path=str(source_path) if is_local else None
        ).source_key,
        is_local,
    )
    if agents_includes:
        agents_config = AgentsConfig(includes=[a.strip() for a in agents_includes.split(',')])
    elif agents_excludes:
        agents_config = AgentsConfig(excludes=[a.strip() for a in agents_excludes.split(',')])
    elif existing_pkg is not None:
        # Repo already in config, keep existing agents setting
        agents_config = existing_pkg.agents
    else:
        agent_names = list(KNOWN_AGENTS.keys())
        # Pre-select based on config default
        default_agents_list = config.agents.default if config.agents else None
        if default_agents_list:
            preselected = {i for i, name in enumerate(agent_names) if name in default_agents_list}
        else:
            preselected = None  # all selected

        agent_indices = interactive_multi_select(agent_names, header='Select agents:', preselected=preselected)
        if agent_indices is None:
            click.echo('Cancelled.')
            return

        selected_agent_names = [agent_names[i] for i in agent_indices]
        if set(selected_agent_names) == set(agent_names):
            agents_config = None  # all agents = no filter needed
        else:
            agents_config = AgentsConfig(includes=selected_agent_names)

    # Build SkillRepoConfig
    skill_names = [s.name for s in selected_skills]
    # Only set skills list if not all skills were selected
    if len(selected_skills) == len(detected):
        config_skills = None
    else:
        config_skills = skill_names

    if is_local:
        new_pkg = SkillRepoConfig(local_path=str(source_path), skills=config_skills, agents=agents_config)
    else:
        new_pkg = SkillRepoConfig(repo=source, skills=config_skills, agents=agents_config)

    # Upsert into config
    upsert_package(config, new_pkg)

    # Save config
    save_config(config, config_path)
    click.echo(f'Config saved: {config_path}')

    # Find the actual package in config (upsert may have merged into existing)
    pkg_to_install = _find_package_by_source(config, new_pkg.source_key, is_local) or new_pkg

    # Install just this package
    default_agents = config.agents.default if config.agents else None
    agents = _expand_agents(ctx.obj['agents_dir'], default_agents)
    run_install_package(
        repo_config=pkg_to_install,
        lock_path=ctx.obj['lock_path'],
        store_dir=ctx.obj['store_dir'],
        known_agents=agents,
        force=force,
    )


def _find_package_by_source(config: SkmConfig, source_key: str, is_local: bool) -> SkillRepoConfig | None:
    """Find existing package in config matching the source."""
    for pkg in config.packages:
        if is_local and pkg.local_path:
            if str(Path(pkg.local_path).expanduser()) == str(Path(source_key).expanduser()):
                return pkg
        elif not is_local and pkg.repo:
            if pkg.repo == source_key:
                return pkg
    return None


def _source_matches(installed_skill, source_key: str, is_local: bool) -> bool:
    """Check if an InstalledSkill matches the given source."""
    if is_local:
        return installed_skill.local_path is not None and str(Path(installed_skill.local_path).expanduser()) == str(
            Path(source_key).expanduser()
        )
    return installed_skill.repo == source_key


@cli.command()
@click.argument('skill_name')
@click.pass_context
def remove(ctx, skill_name: str):
    """Remove an installed skill."""
    from skm.commands.remove import run_remove

    run_remove(
        skill_name=skill_name,
        config_path=ctx.obj['config_path'],
        lock_path=ctx.obj['lock_path'],
    )


@cli.command(name='check-updates')
@click.pass_context
def check_updates(ctx):
    """Check for skill updates."""
    from skm.commands.check_updates import run_check_updates

    run_check_updates(ctx.obj['lock_path'], ctx.obj['store_dir'])


@cli.command()
@click.argument('skill_name')
@click.pass_context
def update(ctx, skill_name: str):
    """Update a specific skill."""
    from skm.commands.update import run_update

    config = load_config(ctx.obj['config_path'])
    default_agents = config.agents.default if config.agents else None
    agents = _expand_agents(ctx.obj['agents_dir'], default_agents)
    run_update(
        skill_name=skill_name,
        config=config,
        lock_path=ctx.obj['lock_path'],
        store_dir=ctx.obj['store_dir'],
        known_agents=agents,
    )


@cli.command()
@click.argument('source')
@click.pass_context
def view(ctx, source: str):
    """Browse and read skills from a repo or local path."""
    from skm.commands.view import run_view

    run_view(source=source, store_dir=ctx.obj['store_dir'])


@cli.command(name='list')
@click.option(
    '--all',
    'show_all',
    is_flag=True,
    default=False,
    help='Show all skills in each agent directory, including unmanaged ones.',
)
@click.pass_context
def list_skills(ctx, show_all: bool):
    """List installed skills and their linked paths."""
    from skm.commands.list_cmd import run_list, run_list_all

    if show_all:
        config = load_config(ctx.obj['config_path'])
        default_agents = config.agents.default if config.agents else None
        agents = _expand_agents(ctx.obj['agents_dir'], default_agents)
        run_list_all(ctx.obj['lock_path'], agents)
    else:
        run_list(ctx.obj['lock_path'])
