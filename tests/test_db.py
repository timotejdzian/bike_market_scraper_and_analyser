"""DB layer round-trip test, including explicit close (Windows file locking)."""

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from a2moto.db import ListingRow, PriceHistoryRow, get_engine, init_db, listing_to_row
from a2moto.models import Listing


def make_listing() -> Listing:
    now = datetime(2026, 8, 24, 12, 0, 0, tzinfo=UTC)
    return Listing(
        id="bazos_sk:12345678",
        site="bazos_sk",
        url="https://motorky.bazos.sk/inzerat/12345678/",
        site_listing_id="12345678",
        title_raw="Kawasaki Ninja 650, r.v. 2019, 24 000 km",
        description_raw="Predám Ninja 650, servisná knižka, ABS.",
        model_canonical="Ninja 650",
        manufacturer="Kawasaki",
        year=2019,
        mileage_km=24000,
        power_kw=50.2,
        price_raw=5600.0,
        currency="EUR",
        price_eur=5600.0,
        country="SK",
        seller_type="private",
        first_seen_at=now,
        last_seen_at=now,
        raw_attrs={"category": "motorky"},
    )


def test_listing_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    engine = get_engine(db_path)
    try:
        init_db(engine)
        listing = make_listing()
        with Session(engine) as session:
            session.add(listing_to_row(listing))
            session.add(
                PriceHistoryRow(
                    listing_id=listing.id,
                    observed_at=listing.first_seen_at,
                    price_eur=listing.price_eur,
                )
            )
            session.commit()
        with Session(engine) as session:
            row = session.get(ListingRow, "bazos_sk:12345678")
            assert row is not None
            assert row.model_canonical == "Ninja 650"
            assert row.mileage_km == 24000
            assert row.price_eur == 5600.0
            assert row.raw_attrs == {"category": "motorky"}
            history = session.scalars(select(PriceHistoryRow)).all()
            assert len(history) == 1
            assert history[0].price_eur == 5600.0
    finally:
        engine.dispose()
    # Windows file locking: after dispose, the DB file must be free to delete.
    db_path.unlink()
    assert not db_path.exists()


def test_init_db_creates_parent_dirs(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "dir" / "test.db"
    engine = get_engine(db_path)
    try:
        init_db(engine)
    finally:
        engine.dispose()
    assert db_path.exists()
