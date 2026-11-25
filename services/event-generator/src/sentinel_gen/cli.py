"""Command-line interface: `sentinel-gen <command>`."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from sentinel_gen import db
from sentinel_gen.config import DEFAULT_CONFIG, load_config
from sentinel_gen.logs import configure_logging
from sentinel_gen.seed import ExistingDataError
from sentinel_gen.seed import seed as seed_reference_data
from sentinel_gen.settings import Settings

app = typer.Typer(help="Simulated ERP of Atlas Distribution.", no_args_is_help=True)

ConfigOption = Annotated[Path, typer.Option(help="Market configuration file.")]
SeedOption = Annotated[int, typer.Option(help="Random seed: the same seed gives the same data.")]


@app.callback()
def main() -> None:
    configure_logging()


@app.command()
def seed(
    seed: SeedOption = 42,
    force: Annotated[bool, typer.Option(help="Replace existing ERP data.")] = False,
    config: ConfigOption = DEFAULT_CONFIG,
) -> None:
    """Load the reference data: geography, warehouses, sales reps, customers, catalog, stock."""
    with db.connect(Settings()) as conn:
        try:
            seed_reference_data(conn, load_config(config), seed, force)
        except ExistingDataError as error:
            typer.echo(f"error: {error}", err=True)
            raise typer.Exit(code=1) from error


@app.command()
def fingerprint() -> None:
    """Print a SHA-256 fingerprint of each ERP table's content."""
    with db.connect(Settings()) as conn:
        for table in db.ERP_TABLES:
            typer.echo(f"{table:<14} {db.fingerprint(conn, table)}")


if __name__ == "__main__":
    app()
