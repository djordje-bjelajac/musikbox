import click
from rich.console import Console

from musikbox.adapters.migrations import init_db
from musikbox.domain.exceptions import DatabaseError

console = Console()


@click.group()
def db() -> None:
    """Database management commands."""


@db.command()
@click.pass_context
def init(ctx: click.Context) -> None:
    """Initialize the database schema."""
    try:
        db_path = ctx.obj.config.db_path
        init_db(db_path)
        console.print(f"[green]Database initialized at:[/green] {db_path}")
    except DatabaseError as e:
        console.print(f"[red]Database initialization failed:[/red] {e}")
        raise SystemExit(1)
