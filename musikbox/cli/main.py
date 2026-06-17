import click

from musikbox.bootstrap import bootstrap_client, create_app
from musikbox.cli.analyze import analyze
from musikbox.cli.config import config
from musikbox.cli.db import db
from musikbox.cli.download import download
from musikbox.cli.library import library
from musikbox.cli.play import play
from musikbox.cli.playlist import playlist
from musikbox.config.settings import load_config


@click.group()
@click.pass_context
def cli(ctx: click.Context) -> None:
    """musikbox - download, analyze, and manage your music library."""
    ctx.ensure_object(dict)
    if load_config().mode == "client":
        ctx.obj = bootstrap_client()
    else:
        ctx.obj = create_app()


cli.add_command(download)
cli.add_command(analyze)
cli.add_command(db)
cli.add_command(library)
cli.add_command(config)
cli.add_command(play)
cli.add_command(playlist)
