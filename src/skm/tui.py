import sys

import click


def has_terminal() -> bool:
    """True when stdin is a terminal, i.e. someone can answer a prompt."""
    return sys.stdin.isatty()


def interactive_multi_select(
    items: list[str],
    header: str | None = None,
    preselected: set[int] | None = None,
) -> list[int] | None:
    """Interactive multi-select with checkboxes. Space to toggle, Enter to confirm, q to cancel.

    Returns list of selected indices, or None if cancelled.
    preselected: indices that start checked (default: all selected).
    Without a terminal it returns the preselection right away instead of waiting for keys.
    """
    if not items:
        return []

    if preselected is None:
        selected = set(range(len(items)))
    else:
        selected = set(preselected)

    if not has_terminal():
        picked = ', '.join(items[i] for i in sorted(selected)) or 'nothing'
        click.secho(f'{header or "Select:"} no terminal to ask, using the defaults: {picked}', fg='yellow')
        return sorted(selected)

    current = 0
    total_lines = len(items) + (1 if header else 0)
    first_draw = True

    while True:
        if not first_draw:
            click.echo(f'\033[{total_lines}A', nl=False)
        first_draw = False

        if header:
            click.echo(f'\033[2K{header}')

        for i, item in enumerate(items):
            check = click.style('[x]', fg='green', bold=True) if i in selected else '[ ]'
            cursor = click.style('> ', fg='green', bold=True) if i == current else '  '
            label = click.style(item, bold=True) if i == current else item
            click.echo(f'\033[2K{cursor}{check} {label}')

        ch = click.getchar()

        if ch in ('\r',):
            # Clear menu
            click.echo(f'\033[{total_lines}A', nl=False)
            for _ in range(total_lines):
                click.echo('\033[2K')
            click.echo(f'\033[{total_lines}A', nl=False)
            return sorted(selected)
        elif ch in ('q', '\x03'):
            click.echo(f'\033[{total_lines}A', nl=False)
            for _ in range(total_lines):
                click.echo('\033[2K')
            click.echo(f'\033[{total_lines}A', nl=False)
            return None
        elif ch == ' ':
            if current in selected:
                selected.discard(current)
            else:
                selected.add(current)
        elif ch == '\x1b[A' or ch == 'k':  # up
            current = (current - 1) % len(items)
        elif ch == '\x1b[B' or ch == 'j':  # down
            current = (current + 1) % len(items)


def interactive_select(items: list[str], header: str | None = None, initial: int = 0) -> int | None:
    """Interactive list selector using arrow keys/j/k, enter to select, q to quit.

    Returns the selected index, or None if the user quit.
    """
    if not items:
        return None

    current = max(0, min(initial, len(items) - 1))
    total_lines = len(items) + (1 if header else 0)
    first_draw = True

    while True:
        # Move cursor up to redraw (except on first draw)
        if not first_draw:
            click.echo(f'\033[{total_lines}A', nl=False)
        first_draw = False

        if header:
            click.echo(f'\033[2K{header}')

        for i, item in enumerate(items):
            prefix = click.style('❯ ', fg='green', bold=True) if i == current else '  '
            label = click.style(item, bold=True) if i == current else item
            click.echo(f'\033[2K{prefix}{label}')

        ch = click.getchar()

        if ch in ('\r', 'q', '\x03'):
            # Move cursor up and clear all menu lines before returning
            click.echo(f'\033[{total_lines}A', nl=False)
            for _ in range(total_lines):
                click.echo('\033[2K')
            # Move back up so caller's next output starts at the right place
            click.echo(f'\033[{total_lines}A', nl=False)
            if ch == '\r':
                return current
            return None
        elif ch == '\x1b[A' or ch == 'k':  # up
            current = (current - 1) % len(items)
        elif ch == '\x1b[B' or ch == 'j':  # down
            current = (current + 1) % len(items)
