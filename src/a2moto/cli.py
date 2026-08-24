"""Typer CLI. Only `models` is functional in step 1; the rest are stubs."""

from __future__ import annotations

import typer

from a2moto.config import load_model_specs
from a2moto.eligibility import check_a2_eligibility

app = typer.Typer(
    help="A2 sportbike market scraper and fair-price analyzer (CZ/SK/PL).",
    no_args_is_help=True,
)


@app.command()
def scrape(
    sites: str = typer.Option("all", help="Comma-separated site list or 'all'."),
    max_pages: int = typer.Option(20, help="Max result pages per site."),
) -> None:
    """Scrape classified listings. Not implemented yet (step 2+)."""
    typer.echo(f"scrape(sites={sites!r}, max_pages={max_pages}): not implemented yet (step 2+)")
    raise typer.Exit(code=1)


@app.command("scrape-new")
def scrape_new(
    countries: str = typer.Option("cz,sk,pl", help="Comma-separated country codes."),
) -> None:
    """Refresh OEM MSRP data. Not implemented yet (step 6)."""
    typer.echo(f"scrape-new(countries={countries!r}): not implemented yet (step 6)")
    raise typer.Exit(code=1)


@app.command()
def parse() -> None:
    """Re-parse listings from the on-disk cache, no network. Not implemented yet (step 3)."""
    typer.echo("parse: not implemented yet (step 3)")
    raise typer.Exit(code=1)


@app.command()
def analyze(
    model: str = typer.Option(None, help="Canonical model name filter."),
    max_price: float = typer.Option(None, help="Max price in EUR."),
    max_mileage: int = typer.Option(None, help="Max mileage in km."),
) -> None:
    """Analyze fair market price. Not implemented yet (step 7)."""
    typer.echo(
        f"analyze(model={model!r}, max_price={max_price}, max_mileage={max_mileage}): "
        "not implemented yet (step 7)"
    )
    raise typer.Exit(code=1)


@app.command()
def report() -> None:
    """Build the self-contained HTML report. Not implemented yet (step 7)."""
    typer.echo("report: not implemented yet (step 7)")
    raise typer.Exit(code=1)


@app.command()
def models() -> None:
    """Print the model whitelist with A2 eligibility and verification status."""
    specs = load_model_specs()
    header = (
        f"{'model':<22} {'mfr':<10} {'kW':>5} {'kg':>5} {'kW/kg@rest':>10} "
        f"{'class':<12} {'eligible':<8} {'verified':<8} notes"
    )
    typer.echo(header)
    typer.echo("-" * len(header))
    for spec in specs:
        result = check_a2_eligibility(stock_kw=spec.stock_kw, wet_weight_kg=spec.wet_weight_kg)
        klass = "native" if spec.a2_native else ("restrictable" if spec.restrictable else "?")
        notes = "; ".join(result.failures + result.warnings)
        typer.echo(
            f"{spec.canonical:<22} {spec.manufacturer:<10} {spec.stock_kw:>5.1f} "
            f"{spec.wet_weight_kg:>5.0f} {result.kw_per_kg:>10.4f} {klass:<12} "
            f"{str(result.eligible):<8} {str(spec.verified):<8} {notes}"
        )
    unverified = sum(1 for s in specs if not s.verified)
    typer.echo(f"\n{len(specs)} models, {unverified} with unverified spec figures.")


if __name__ == "__main__":
    app()
