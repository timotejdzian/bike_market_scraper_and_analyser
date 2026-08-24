"""Pydantic v2 schemas: model whitelist entries, listings, new-bike prices."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

Country = Literal["CZ", "SK", "PL"]
Currency = Literal["CZK", "EUR", "PLN"]
SellerType = Literal["private", "dealer"]


class ModelSpec(BaseModel):
    """One entry of the model whitelist (config/models.yaml)."""

    canonical: str
    manufacturer: str
    aliases: list[str] = Field(min_length=1)
    stock_kw: float = Field(gt=0)
    stock_hp: float = Field(gt=0)
    cc: int = Field(gt=0)
    wet_weight_kg: float = Field(gt=0)
    a2_native: bool
    restrictable: bool
    year_from: int | None = Field(default=None, ge=1990, le=2030)
    year_to: int | None = Field(default=None, ge=1990, le=2030)
    source: str
    verified: bool = False

    @field_validator("aliases")
    @classmethod
    def aliases_must_compile(cls, v: list[str]) -> list[str]:
        for pattern in v:
            try:
                re.compile(pattern, re.IGNORECASE)
            except re.error as exc:
                raise ValueError(f"alias is not a valid regex: {pattern!r} ({exc})") from exc
        return v


class Listing(BaseModel):
    """One normalized classified listing (mirrors the `listings` table)."""

    id: str  # f"{site}:{site_listing_id}"
    site: str
    url: str
    site_listing_id: str
    title_raw: str
    description_raw: str | None = None
    model_canonical: str | None = None  # resolved via models.yaml, None if unmatched
    manufacturer: str | None = None
    year: int | None = None
    mileage_km: int | None = None
    displacement_cc: int | None = None
    power_kw: float | None = None  # as advertised
    price_raw: float | None = None
    currency: Currency | None = None
    price_eur: float | None = None
    price_negotiable: bool | None = None
    vat_deductible: bool | None = None
    country: Country
    region: str | None = None
    city: str | None = None
    lat: float | None = None
    lon: float | None = None
    seller_type: SellerType | None = None
    posted_at: date | None = None
    first_seen_at: datetime
    last_seen_at: datetime
    is_active: bool = True
    condition_notes: str | None = None
    has_abs: bool | None = None
    has_crash_damage: bool | None = None
    is_restricted_35kw: bool | None = None
    service_book: bool | None = None
    owners_count: int | None = None
    photos_count: int | None = None
    is_parts_listing: bool | None = None
    raw_attrs: dict[str, Any] = Field(default_factory=dict)
    dupe_group_id: str | None = None
    scrape_run_id: str | None = None


class NewPrice(BaseModel):
    """One observed (or estimated) new-bike price (mirrors the `new_prices` table)."""

    id: str  # f"{model_canonical}:{country}:{model_year}"
    model_canonical: str
    model_year: int
    country: Country
    price_raw: float
    currency: Currency
    price_eur: float
    includes_vat: bool
    on_road_costs_eur: float | None = None
    source_type: Literal["oem_page", "oem_pricelist_pdf", "dealer", "manual"]
    source_url: str | None = None
    observed_at: date
    is_estimated: bool = False
