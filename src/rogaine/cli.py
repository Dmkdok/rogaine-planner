"""Command line entry point.

M0 ships only the corpus commands — enough for the `rogaine` console script to work and for
``data/README.md`` to describe something that exists. T050 (WS-C) adds `segment`, `plan`, `bench`
and `serve` to this same app.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from rogaine import __version__
from rogaine.io.corpus import list_corpus, read_entry

DEFAULT_CORPUS = Path("data/maps")

app = typer.Typer(
    help="Plan rogaine routes from orienteering map rasters.",
    no_args_is_help=True,
    add_completion=False,
)
corpus_app = typer.Typer(help="Inspect the map corpus under data/maps/.", no_args_is_help=True)
app.add_typer(corpus_app, name="corpus")

console = Console()


# invoke_without_command lets `--version` run without a subcommand; no_args_is_help still turns a
# bare `rogaine` into the help screen.
@app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", help="Print the version and exit."),
) -> None:
    if version:
        console.print(__version__)
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())
        raise typer.Exit()


@corpus_app.command("list")
def corpus_list(
    root: Path = typer.Option(DEFAULT_CORPUS, "--root", help="Corpus directory."),
) -> None:
    """List every map and what metadata it is still missing.

    Never fails on an incomplete map: a half-set-up corpus is the normal state while files are
    still arriving.
    """
    entries = list_corpus(root)
    if not entries:
        console.print(f"[yellow]No maps under {root}[/]. See data/README.md for the layout.")
        raise typer.Exit()

    table = Table(title=f"{len(entries)} map(s) under {root}")
    table.add_column("id")
    table.add_column("m/px", justify="right")
    table.add_column("plannable", justify="center")
    table.add_column("missing / problems")

    for entry in entries:
        mpp = f"{entry.meters_per_pixel:.3f}" if entry.meters_per_pixel else "-"
        notes = [*entry.problems, *entry.missing]
        table.add_row(
            entry.map_id,
            mpp,
            "[green]yes[/]" if entry.is_plannable else "[red]no[/]",
            "; ".join(notes) if notes else "[green]complete[/]",
        )
    console.print(table)


@corpus_app.command("check")
def corpus_check(
    map_id: str = typer.Argument(..., help="Directory name under the corpus root."),
    root: Path = typer.Option(DEFAULT_CORPUS, "--root", help="Corpus directory."),
) -> None:
    """Report one map in full. Exits non-zero when the map cannot be planned on."""
    map_dir = root / map_id
    if not map_dir.is_dir():
        console.print(f"[red]{map_dir} does not exist[/]")
        raise typer.Exit(code=2)

    entry = read_entry(map_dir)
    console.print(f"[bold]{entry.map_id}[/]" + (f" — {entry.name}" if entry.name else ""))
    console.print(f"  raster:     {entry.raster or '[red]missing[/]'}")
    console.print(f"  scale:      {entry.scale_denominator or '-'} at {entry.dpi or '-'} dpi")
    console.print(f"  calibrated: {'yes' if entry.calibration else 'no'}")
    mpp = entry.meters_per_pixel
    console.print(f"  m/px:       {f'{mpp:.4f}' if mpp else '[red]unknown[/]'}")
    console.print(f"  controls:   {'controls.csv' if entry.has_controls else 'none (detect)'}")
    console.print(f"  reference:  {'reference.json' if entry.has_reference else 'none'}")
    for problem in entry.problems:
        console.print(f"  [red]problem:[/]  {problem}")
    for gap in entry.missing:
        console.print(f"  [yellow]missing:[/]  {gap}")

    if not entry.is_plannable:
        raise typer.Exit(code=1)


if __name__ == "__main__":  # pragma: no cover
    app()
