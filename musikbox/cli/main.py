import click

from musikbox.bootstrap import create_app
from musikbox.cli.analyze import analyze
from musikbox.cli.config import config
from musikbox.cli.db import db
from musikbox.cli.download import download
from musikbox.cli.library import library


@click.group()
@click.pass_context
def cli(ctx: click.Context) -> None:
    """musikbox - download, analyze, and manage your music library."""
    ctx.ensure_object(dict)
    ctx.obj = create_app()


cli.add_command(download)
cli.add_command(analyze)
cli.add_command(db)
cli.add_command(library)
cli.add_command(config)
