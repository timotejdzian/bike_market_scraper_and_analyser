"""
Text extraction for Czech, Slovak, and Polish motorcycle listings.

Handles free-text fields: mileage, year, price negotiability, crash damage,
restriction status, service book, across three languages with thousands
separators, ambiguous phrasing, and embedded values.
"""

import logging
import re
import unicodedata
from typing import Any

logger = logging.getLogger(__name__)


def normalize_text(text: str) -> str:
    """
    Normalize text by removing diacritics and converting to lowercase.

    Slovak and Czech sellers frequently type without accents.
    This function ensures patterns match both accented and unaccented text.

    Example:
        "najazdené" → "najazdene"
        "servisná knížka" → "servisna knizka"

    Args:
        text: Input text with potential diacritics

    Returns:
        Normalized text without diacritics, lowercase
    """
    # NFKD decomposition separates base characters from combining diacritics
    nfkd = unicodedata.normalize('NFKD', text)
    # Filter out combining characters (diacritics)
    without_diacritics = ''.join([c for c in nfkd if not unicodedata.combining(c)])
    return without_diacritics.lower()


def extract_mileage(title: str, description: str | None) -> dict[str, Any]:
    """
    Extract mileage in kilometers from title and description.

    Languages: CZ/SK/PL
    Formats:
    - CZ/SK: "najeto 25 000 km", "25000 km", "25 tis. km", "najazdených 12500km"
    - PL: "przebieg 30000 km", "30 tys. km"
    - Structured: "Najazdené km: 20300 km"

    Args:
        title: Listing title
        description: Listing description (optional)

    Returns:
        Dict with:
        - mileage_km: int | None (extracted mileage in km)
        - suspicious: bool (True if value is < 100 or > 200,000)
        - raw_match: str | None (the matched text)
    """
    original_text = title + " " + (description or "")
    text = normalize_text(original_text)

    # Patterns for mileage keywords + number
    # CZ/SK: najeto, najazdene, najazdenych, najetych, km, tis. km, tisic km, najazd
    # PL: przebieg, najazdow, tys. km, tysiac
    # Note: patterns use normalized (no diacritics) keywords
    patterns = [
        # Structured format: "Najazdené km: 20300 km" or "Nájazd: 28.000"
        r"(?:najazdene|najazd|najeto|najetych|najazdenych)\s*(?:km)?\s*:\s*([\d\s\.,']+)(?:\s*km)?",
        # With explicit mileage keywords
        r"(?:najeto|najazdene|najazdenych|najetych|przebieg|najazdow)\s*:?\s*([\d\s\.,']+)\s*(?:tis\.|tisic|tys\.|tysiac)?\s*km",
        # Number adjacent to km with no whitespace or hyphen: "4000km", "- 4000km"
        r"[\s\-]([\d\s\.,']+)km\b",
        # Standalone number + km (common in titles)
        r"\b([\d\s\.,']+)\s*(?:tis\.|tisic|tys\.|tysiac)?\s*km\b",
        # Czech/Slovak thousand marker
        r"\b([\d\s\.,']+)\s+(?:tis\.|tisic)\s*km",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            raw_value = match.group(1)
            # Clean: remove spaces, dots, commas (thousand separators)
            cleaned = re.sub(r"[\s\.,']", "", raw_value)

            try:
                mileage = int(cleaned)

                # Handle thousand markers (tis., tisíc, tys., tysiąc)
                if any(kw in match.group(0) for kw in ["tis.", "tisic", "tys.", "tysiac"]):
                    mileage *= 1000

                # Flag suspicious values
                suspicious = mileage < 100 or mileage > 200_000

                return {
                    "mileage_km": mileage,
                    "suspicious": suspicious,
                    "raw_match": match.group(0),
                }
            except ValueError:
                logger.debug(f"Failed to parse mileage: {raw_value}")
                continue

    return {"mileage_km": None, "suspicious": False, "raw_match": None}


def extract_year(title: str, description: str | None, model_year_from: int | None = None, model_year_to: int | None = None) -> dict[str, Any]:
    """
    Extract model year from title and description.

    Languages: CZ/SK/PL
    Formats:
    - "r.v. 2019", "rok výroby 2020", "rocznik 2018"
    - Bare 4-digit year: "2015", but only if in plausible range (1990-2026)

    Args:
        title: Listing title
        description: Listing description (optional)
        model_year_from: Production start year for this model (for cross-check)
        model_year_to: Production end year for this model (for cross-check)

    Returns:
        Dict with:
        - year: int | None
        - mismatch: bool (True if year is outside model production years)
        - raw_match: str | None
    """
    original_text = title + " " + (description or "")
    text = normalize_text(original_text)

    # Patterns for year
    # CZ/SK: r.v., r. v., rok vyroby (normalized from rok výroby)
    # PL: rocznik, rok produkcji
    patterns = [
        r"(?:r\.?\s*v\.?|rok\s+vyroby|rok\s+produkcji|rocznik)\s*:?\s*(\d{4})",
        r"\b(19\d{2}|20[0-2]\d)\b",  # Bare 4-digit 1900-2029
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                year = int(match.group(1))

                # Validate range 1990-2026
                if not (1990 <= year <= 2026):
                    continue

                # Check against model production years if provided
                mismatch = False
                if model_year_from is not None and year < model_year_from:
                    mismatch = True
                if model_year_to is not None and year > model_year_to:
                    mismatch = True

                return {
                    "year": year,
                    "mismatch": mismatch,
                    "raw_match": match.group(0),
                }
            except ValueError:
                continue

    return {"year": None, "mismatch": False, "raw_match": None}


def extract_price_negotiable(title: str, description: str | None) -> dict[str, Any]:
    """
    Detect if price is negotiable.

    Languages: CZ/SK/PL
    Keywords:
    - CZ/SK: dohoda, dohodou, dohovor
    - PL: do negocjacji, negocjacja
    - "cena při osobním jednání" = price unknown, not negotiable

    Args:
        title: Listing title
        description: Listing description (optional)

    Returns:
        Dict with:
        - negotiable: bool | None
        - raw_match: str | None
    """
    original_text = title + " " + (description or "")
    text = normalize_text(original_text)

    # Price unknown indicators (not negotiable, just unknown)
    # Normalized: pri -> pri, osobnim -> osobnim
    unknown_patterns = [
        r"cena\s+pri\s+osobnim\s+jednani",
        r"cena\s+v\s+popise",
        r"cena\s+po\s+dohode",
    ]

    for pattern in unknown_patterns:
        if re.search(pattern, text):
            return {"negotiable": None, "raw_match": None}

    # Negotiable keywords
    negotiable_patterns = [
        r"\bdohoda\b",
        r"\bdohodou\b",
        r"\bdohovor\b",
        r"do\s+negocjacji",
        r"negocjacja",
        r"mozna\s+sleva",
        r"cena\s+dohodou",
    ]

    for pattern in negotiable_patterns:
        match = re.search(pattern, text)
        if match:
            return {"negotiable": True, "raw_match": match.group(0)}

    return {"negotiable": False, "raw_match": None}


def extract_crash_damage(title: str, description: str | None) -> dict[str, Any]:
    """
    Detect crash damage keywords.

    Languages: CZ/SK/PL
    Keywords:
    - CZ/SK: havarované, bourané, po nehode, po nehodě
    - PL: uszkodzony, rozbite, po wypadku

    Args:
        title: Listing title
        description: Listing description (optional)

    Returns:
        Dict with:
        - has_crash_damage: bool
        - raw_match: str | None
    """
    original_text = title + " " + (description or "")
    text = normalize_text(original_text)

    # Normalized patterns (no diacritics)
    # havarovane, bourane, po nehode, poskodeny
    damage_patterns = [
        r"\bhavaro",  # havarovane, havarovany
        r"\bbouran",  # bourane, bourany
        r"po\s+nehod",  # po nehode
        r"\buszkodzon",  # uszkodzony
        r"\brozbite",
        r"po\s+wypadku",
        r"\bposkoden",  # poskodeny
        r"\btotal",  # total loss
    ]

    for pattern in damage_patterns:
        match = re.search(pattern, text)
        if match:
            return {"has_crash_damage": True, "raw_match": match.group(0)}

    return {"has_crash_damage": False, "raw_match": None}


def extract_restriction(title: str, description: str | None) -> dict[str, Any]:
    """
    Detect A2 restriction (35kW) and removal.

    Languages: CZ/SK/PL
    Patterns:
    - Restricted: "omezeno na 35kW", "obmedzené na 35kW", "A2", "ograniczony do 35kW"
    - Removal: "odstranění omezení", "zrušené obmedzenie", "usunięte ograniczenie"

    Ambiguous: "35kW" in description mentioning removal.

    Args:
        title: Listing title
        description: Listing description (optional)

    Returns:
        Dict with:
        - is_restricted_35kw: bool | None (None if ambiguous)
        - raw_match: str | None
    """
    original_text = title + " " + (description or "")
    text = normalize_text(original_text)

    # Check for removal first (takes precedence)
    # Normalized: odstraneni omezeni, zrusene obmedzenie
    removal_patterns = [
        r"odstraneni\s+omezen",
        r"zrusene\s+obmedzen",
        r"usunite\s+ograniczen",
        r"bez\s+omezen",
        r"bez\s+obmedzen",
    ]

    for pattern in removal_patterns:
        match = re.search(pattern, text)
        if match:
            return {"is_restricted_35kw": False, "raw_match": match.group(0)}

    # Check for restriction keywords
    # Normalized: omezeno, obmedzene, ograniczony
    restriction_patterns = [
        r"omezen[oy]\s+na\s+35\s*kw",
        r"obmedzen[ye]\s+na\s+35\s*kw",
        r"ograniczon[yy]\s+do\s+35\s*kw",
        r"\ba2\b",
        r"35\s*kw\s+(?:omezen|obmedzen|ograniczon)",
    ]

    for pattern in restriction_patterns:
        match = re.search(pattern, text)
        if match:
            # Check if "removal" is mentioned nearby (ambiguous case)
            context = text[max(0, match.start() - 50):min(len(text), match.end() + 50)]
            if any(kw in context for kw in ["odstraneni", "zrusene", "usuni"]):
                return {"is_restricted_35kw": None, "raw_match": match.group(0) + " (ambiguous)"}

            return {"is_restricted_35kw": True, "raw_match": match.group(0)}

    return {"is_restricted_35kw": None, "raw_match": None}


def extract_service_book(title: str, description: str | None) -> dict[str, Any]:
    """
    Detect service book presence.

    Languages: CZ/SK/PL
    Keywords:
    - CZ/SK: servisní knížka, servisná knižka
    - PL: książka serwisowa

    Args:
        title: Listing title
        description: Listing description (optional)

    Returns:
        Dict with:
        - service_book: bool | None
        - raw_match: str | None
    """
    original_text = title + " " + (description or "")
    text = normalize_text(original_text)

    # Normalized patterns (no diacritics)
    # servisni knizka, servisna knizka, ksiazka serwisowa
    service_patterns = [
        r"servisn[ia]\s+kn[ii][zz]ka",
        r"k[ss][ii][aa][zz]ka\s+serwisowa",
        r"service\s+book",
        r"kniha\s+servisu",
    ]

    for pattern in service_patterns:
        match = re.search(pattern, text)
        if match:
            return {"service_book": True, "raw_match": match.group(0)}

    return {"service_book": None, "raw_match": None}
