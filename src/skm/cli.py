from pathlib import Path

import click

from skm.config import load_config
from skm.types import CONFIG_PATH, LOCK_PATH, STORE_DIR, KNOWN_AGENTS


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
@click.option(
    '--force', is_flag=True, default=False, help='Override existing non-symlink skill directories without prompting.'
)
@click.pass_context
def install(ctx, force):
    """Install/remove skills based on config."""
    from skm.commands.install import run_install

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
