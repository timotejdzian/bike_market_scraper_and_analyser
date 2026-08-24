"""SQLAlchemy 2.0 database layer: listings, price_history, new_prices.

SQLite via `data/listings.db`. Callers must dispose engines / close sessions
explicitly -- Windows file locking is stricter than POSIX.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import JSON, Date, DateTime, Engine, ForeignKey, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from a2moto.models import Listing, NewPrice


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON}


class ListingRow(Base):
    __tablename__ = "listings"

    id: Mapped[str] = mapped_column(primary_key=True)  # f"{site}:{site_listing_id}"
    site: Mapped[str] = mapped_column(index=True)
    url: Mapped[str]
    site_listing_id: Mapped[str]
    title_raw: Mapped[str]
    description_raw: Mapped[str | None]
    model_canonical: Mapped[str | None] = mapped_column(index=True)
    manufacturer: Mapped[str | None]
    year: Mapped[int | None]
    mileage_km: Mapped[int | None]
    displacement_cc: Mapped[int | None]
    power_kw: Mapped[float | None]
    price_raw: Mapped[float | None]
    currency: Mapped[str | None]
    price_eur: Mapped[float | None]
    price_negotiable: Mapped[bool | None]
    vat_deductible: Mapped[bool | None]
    country: Mapped[str] = mapped_column(index=True)
    region: Mapped[str | None]
    city: Mapped[str | None]
    lat: Mapped[float | None]
    lon: Mapped[float | None]
    seller_type: Mapped[str | None]
    posted_at: Mapped[date | None] = mapped_column(Date)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime)
    is_active: Mapped[bool] = mapped_column(default=True)
    condition_notes: Mapped[str | None]
    has_abs: Mapped[bool | None]
    has_crash_damage: Mapped[bool | None]
    is_restricted_35kw: Mapped[bool | None]
    service_book: Mapped[bool | None]
    owners_count: Mapped[int | None]
    photos_count: Mapped[int | None]
    raw_attrs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    dupe_group_id: Mapped[str | None] = mapped_column(index=True)
    scrape_run_id: Mapped[str | None]


class PriceHistoryRow(Base):
    __tablename__ = "price_history"

    listing_id: Mapped[str] = mapped_column(ForeignKey("listings.id"), primary_key=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    price_eur: Mapped[float | None]


class NewPriceRow(Base):
    __tablename__ = "new_prices"

    id: Mapped[str] = mapped_column(primary_key=True)  # f"{model}:{country}:{year}"
    model_canonical: Mapped[str] = mapped_column(index=True)
    model_year: Mapped[int]
    country: Mapped[str] = mapped_column(index=True)
    price_raw: Mapped[float]
    currency: Mapped[str]
    price_eur: Mapped[float]
    includes_vat: Mapped[bool]
    on_road_costs_eur: Mapped[float | None]
    source_type: Mapped[str]  # oem_page / oem_pricelist_pdf / dealer / manual
    source_url: Mapped[str | None]
    observed_at: Mapped[date] = mapped_column(Date)
    is_estimated: Mapped[bool] = mapped_column(default=False)


def get_engine(db_path: Path) -> Engine:
    """Create an engine for the SQLite DB at `db_path`, creating parent dirs."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{db_path.as_posix()}")


def init_db(engine: Engine) -> None:
    """Create all tables if they do not exist."""
    Base.metadata.create_all(engine)


def listing_to_row(listing: Listing) -> ListingRow:
    return ListingRow(**listing.model_dump())


def new_price_to_row(new_price: NewPrice) -> NewPriceRow:
    return NewPriceRow(**new_price.model_dump())
