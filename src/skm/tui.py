import click


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
