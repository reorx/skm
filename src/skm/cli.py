from pathlib import Path

import click

from skm.types import CONFIG_PATH, LOCK_PATH, STORE_DIR, KNOWN_AGENTS


@click.group()
@click.option("--config", "config_path", type=click.Path(), default=None,
              help="Path to skills.yaml config file.")
@click.option("--store", "store_dir", type=click.Path(), default=None,
              help="Path to skill store directory.")
@click.option("--lock", "lock_path", type=click.Path(), default=None,
              help="Path to skills-lock.yaml lock file.")
@click.option("--agents-dir", "agents_dir", type=click.Path(), default=None,
              help="Base directory for agent skill symlinks (overrides all known agents).")
@click.pass_context
def cli(ctx, config_path, store_dir, lock_path, agents_dir):
    """SKM - Skill Manager for AI coding agents."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = Path(config_path) if config_path else CONFIG_PATH
    ctx.obj["lock_path"] = Path(lock_path) if lock_path else LOCK_PATH
    ctx.obj["store_dir"] = Path(store_dir) if store_dir else STORE_DIR
    ctx.obj["agents_dir"] = agents_dir


def _expand_agents(agents_dir: str | None = None) -> dict[str, str]:
    if agents_dir:
        # All agents symlink into subdirs of the given base directory
        base = Path(agents_dir)
        return {name: str(base / name) for name in KNOWN_AGENTS}
    return {name: str(Path(path).expanduser()) for name, path in KNOWN_AGENTS.items()}


@cli.command()
@click.pass_context
def install(ctx):
    """Install/remove skills based on config."""
    from skm.commands.install import run_install
    agents = _expand_agents(ctx.obj["agents_dir"])
    run_install(
        config_path=ctx.obj["config_path"],
        lock_path=ctx.obj["lock_path"],
        store_dir=ctx.obj["store_dir"],
        known_agents=agents,
    )


@cli.command(name="check-updates")
@click.pass_context
def check_updates(ctx):
    """Check for skill updates."""
    from skm.commands.check_updates import run_check_updates
    run_check_updates(ctx.obj["lock_path"], ctx.obj["store_dir"])


@cli.command()
@click.argument("skill_name")
@click.pass_context
def update(ctx, skill_name: str):
    """Update a specific skill."""
    from skm.commands.update import run_update
    agents = _expand_agents(ctx.obj["agents_dir"])
    run_update(
        skill_name=skill_name,
        config_path=ctx.obj["config_path"],
        lock_path=ctx.obj["lock_path"],
        store_dir=ctx.obj["store_dir"],
        known_agents=agents,
    )


@cli.command(name="list")
@click.pass_context
def list_skills(ctx):
    """List installed skills and their linked paths."""
    from skm.commands.list_cmd import run_list
    run_list(ctx.obj["lock_path"])
