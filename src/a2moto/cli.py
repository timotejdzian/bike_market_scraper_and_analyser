"""Typer CLI. Only `models` is functional in step 1; the rest are stubs."""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

import typer

from a2moto.config import load_model_specs
from a2moto.db import SessionLocal, init_db, save_listing
from a2moto.eligibility import check_a2_eligibility
from a2moto.scrapers.base import ScraperConfig
from a2moto.scrapers.bazos_sk import BazosSKScraper

app = typer.Typer(
    help="A2 sportbike market scraper and fair-price analyzer (CZ/SK/PL).",
    no_args_is_help=True,
)


def setup_logging(verbose: bool = False) -> None:
    """Configure structured logging to console and file."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"a2moto_{timestamp}.log"

    level = logging.DEBUG if verbose else logging.INFO

    # Configure root logger
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    logger = logging.getLogger(__name__)
    logger.info(f"Logging to {log_file}")


# Mapping of site names to scraper classes
SCRAPERS = {
    "bazos.sk": BazosSKScraper,
}


@app.command()
def scrape(
    sites: str = typer.Option("all", help="Comma-separated site list or 'all'."),
    max_pages: int = typer.Option(20, help="Max result pages per site."),
    refresh: bool = typer.Option(False, help="Force re-fetch, bypass cache."),
    verbose: bool = typer.Option(False, help="Enable debug logging."),
) -> None:
    """Scrape classified listings and save to database."""
    setup_logging(verbose=verbose)
    logger = logging.getLogger(__name__)

    # Initialize database
    init_db()

    # Determine which sites to scrape
    if sites == "all":
        site_list = list(SCRAPERS.keys())
    else:
        site_list = [s.strip() for s in sites.split(",")]

    # Validate site names
    unknown = [s for s in site_list if s not in SCRAPERS]
    if unknown:
        typer.echo(f"Error: Unknown sites: {', '.join(unknown)}", err=True)
        typer.echo(f"Available sites: {', '.join(SCRAPERS.keys())}")
        raise typer.Exit(code=1)

    logger.info(f"Starting scrape of {len(site_list)} site(s): {', '.join(site_list)}")
    logger.info(f"Max pages per site: {max_pages}, Force refresh: {refresh}")

    # Scrape each site
    total_stats = {
        "sites_scraped": 0,
        "sites_failed": 0,
        "total_listings": 0,
        "total_failed": 0,
    }

    for site_name in site_list:
        scraper_class = SCRAPERS[site_name]
        config = ScraperConfig(force_refresh=refresh)

        try:
            with scraper_class(config=config) as scraper:
                listings, stats = scraper.scrape(max_pages=max_pages)

                # Save listings to database
                logger.info(f"Saving {len(listings)} listings to database...")
                session = SessionLocal()
                try:
                    saved_count = 0
                    for listing in listings:
                        save_listing(session, listing)
                        saved_count += 1
                    session.commit()
                    logger.info(f"Saved {saved_count} listings from {site_name}")
                except Exception as e:
                    session.rollback()
                    logger.error(f"Failed to save listings: {e}", exc_info=True)
                    raise
                finally:
                    session.close()

                # Update totals
                total_stats["sites_scraped"] += 1
                total_stats["total_listings"] += stats["listings_parsed"]
                total_stats["total_failed"] += stats["listings_failed"]

                # Print summary for this site
                typer.echo(f"\n{site_name} Summary:")
                typer.echo(f"  Pages scraped: {stats['pages_scraped']}")
                typer.echo(f"  URLs found: {stats['urls_found']}")
                typer.echo(f"  Listings parsed: {stats['listings_parsed']}")
                typer.echo(f"  Listings failed: {stats['listings_failed']}")
                if stats["errors"]:
                    typer.echo(f"  Errors: {len(stats['errors'])}")
                    for error in stats["errors"][:5]:  # Show first 5 errors
                        typer.echo(f"    - {error}")

        except Exception as e:
            logger.error(f"Failed to scrape {site_name}: {e}", exc_info=True)
            total_stats["sites_failed"] += 1
            typer.echo(f"\nError scraping {site_name}: {e}", err=True)

    # Print final summary
    typer.echo("\n" + "=" * 60)
    typer.echo("Final Summary:")
    typer.echo(f"  Sites scraped successfully: {total_stats['sites_scraped']}")
    typer.echo(f"  Sites failed: {total_stats['sites_failed']}")
    typer.echo(f"  Total listings saved: {total_stats['total_listings']}")
    typer.echo(f"  Total listings failed: {total_stats['total_failed']}")
    typer.echo("=" * 60)

    if total_stats["sites_failed"] > 0:
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
