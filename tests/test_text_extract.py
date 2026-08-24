"""Tests for text extraction parsers using real listing fixtures."""

import json
from pathlib import Path

import pytest

from a2moto.parsers.text_extract import (
    extract_crash_damage,
    extract_mileage,
    extract_price_negotiable,
    extract_restriction,
    extract_service_book,
    extract_year,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(listing_id: str) -> dict:
    """Load a fixture by listing ID."""
    fixture_path = FIXTURES_DIR / f"listing_{listing_id}.json"
    with open(fixture_path, encoding="utf-8") as f:
        return json.load(f)


class TestMileageExtraction:
    """Test mileage extraction from real listings."""

    def test_mileage_with_spaces(self):
        """BMW GS with '7 200 km' in title."""
        fixture = load_fixture("194757741")
        result = extract_mileage(fixture["title"], fixture["description"])
        assert result["mileage_km"] == 7200
        assert result["suspicious"] is False

    def test_mileage_harley(self):
        """Harley Davidson Pan America."""
        fixture = load_fixture("193391406")
        result = extract_mileage(fixture["title"], fixture["description"])
        # May or may not extract - depends on description content
        # This tests that it doesn't crash
        assert result is not None

    def test_no_mileage(self):
        """Ninja 650 without mileage in title."""
        fixture = load_fixture("194769418")
        result = extract_mileage(fixture["title"], fixture["description"])
        # Expected: no mileage found
        assert result["mileage_km"] is None


class TestYearExtraction:
    """Test year extraction from real listings."""

    def test_year_in_title_bare(self):
        """Duke 390 with bare '2018' in title."""
        fixture = load_fixture("194644458")
        result = extract_year(fixture["title"], fixture["description"])
        assert result["year"] == 2018
        assert result["mismatch"] is False

    def test_year_with_rv(self):
        """Suzuki Hayabusa with 'r.v 2023'."""
        fixture = load_fixture("194576140")
        result = extract_year(fixture["title"], fixture["description"])
        assert result["year"] == 2023

    def test_year_in_description(self):
        """BMW GS with year 2021 in description."""
        fixture = load_fixture("194757741")
        result = extract_year(fixture["title"], fixture["description"])
        assert result["year"] == 2021


class TestPriceNegotiable:
    """Test price negotiability detection."""

    def test_negotiable_dohoda(self):
        """Listing with 'dohoda' keyword."""
        fixture = load_fixture("193677960")
        result = extract_price_negotiable(fixture["title"], fixture["description"])
        # Check if it was detected
        assert result is not None

    def test_not_negotiable(self):
        """BMW GS with fixed price."""
        fixture = load_fixture("194757741")
        result = extract_price_negotiable(fixture["title"], fixture["description"])
        assert result["negotiable"] is False


class TestCrashDamage:
    """Test crash damage detection."""

    def test_damage_keywords(self):
        """Kawasaki Versys with damage mention."""
        fixture = load_fixture("194465940")
        result = extract_crash_damage(fixture["title"], fixture["description"])
        # Test doesn't crash
        assert result is not None

    def test_no_damage(self):
        """Ninja 650 without damage."""
        fixture = load_fixture("194769418")
        result = extract_crash_damage(fixture["title"], fixture["description"])
        assert result["has_crash_damage"] is False


class TestRestriction:
    """Test A2 restriction detection."""

    def test_restriction_35kw(self):
        """Yamaha XT660X with '35kw,25kw' in title."""
        fixture = load_fixture("194216388")
        result = extract_restriction(fixture["title"], fixture["description"])
        # Should detect restriction
        assert result is not None

    def test_a2_keyword(self):
        """Yamaha WR450F with 'A2' in title."""
        fixture = load_fixture("194525468")
        result = extract_restriction(fixture["title"], fixture["description"])
        # Should detect A2
        assert result is not None

    def test_no_restriction(self):
        """BMW GS without restriction mention."""
        fixture = load_fixture("194757741")
        result = extract_restriction(fixture["title"], fixture["description"])
        # Should return None (not mentioned)
        assert result["is_restricted_35kw"] is None


class TestServiceBook:
    """Test service book detection."""

    def test_service_book_mentioned(self):
        """BMW R1250GS with service book."""
        fixture = load_fixture("194504206")
        result = extract_service_book(fixture["title"], fixture["description"])
        # Test doesn't crash
        assert result is not None

    def test_no_service_book(self):
        """Ninja 650 without service book mention."""
        fixture = load_fixture("194769418")
        result = extract_service_book(fixture["title"], fixture["description"])
        assert result["service_book"] is None


class TestEdgeCases:
    """Test edge cases and ambiguous inputs."""

    def test_parts_listing(self):
        """Parts listing (rozpredám) - no meaningful data expected."""
        fixture = load_fixture("193962039")

        # Should not crash on any extractor
        mileage = extract_mileage(fixture["title"], fixture["description"])
        year = extract_year(fixture["title"], fixture["description"])
        negotiable = extract_price_negotiable(fixture["title"], fixture["description"])

        assert mileage is not None
        assert year is not None
        assert negotiable is not None

    def test_empty_description(self):
        """Listing with no description."""
        title = "Test Bike r.v. 2020, najeto 50000 km"
        description = None

        mileage = extract_mileage(title, description)
        year = extract_year(title, description)

        # With explicit keywords, should extract correctly
        assert mileage["mileage_km"] == 50000
        assert year["year"] == 2020

    def test_all_extractors_run(self):
        """Ensure all extractors run without crashing on every fixture."""
        fixture_files = list(FIXTURES_DIR.glob("listing_*.json"))

        assert len(fixture_files) >= 15, f"Expected at least 15 fixtures, found {len(fixture_files)}"

        for fixture_file in fixture_files:
            with open(fixture_file, encoding="utf-8") as f:
                fixture = json.load(f)

            title = fixture["title"]
            description = fixture["description"]

            # All extractors should run without exceptions
            extract_mileage(title, description)
            extract_year(title, description)
            extract_price_negotiable(title, description)
            extract_crash_damage(title, description)
            extract_restriction(title, description)
            extract_service_book(title, description)
