"""
bazos.sk scraper for motorcycle listings.

robots.txt: https://bazos.sk/robots.txt
Allows:  Main category pages (/motorky/)
Disallows: Search pages (/search.php, ?hledat=), contact forms, admin functions
"""

import logging
import re
from datetime import datetime
from typing import Any

from selectolax.parser import HTMLParser

from a2moto.models import Listing
from a2moto.parsers import text_extract
from a2moto.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class BazosSKScraper(BaseScraper):
    """Scraper for bazos.sk motorcycle listings."""

    @property
    def site_name(self) -> str:
        return "bazos.sk"

    @property
    def base_url(self) -> str:
        return "https://motocykle.bazos.sk"

    @property
    def robots_txt_notes(self) -> str:
        return (
            "bazos.sk robots.txt allows category pages but disallows "
            "search endpoints (/search.php, ?hledat=), contact forms, and admin functions. "
            "We scrape only the main category pagination, which is allowed."
        )

    def _extract_listing_id(self, url: str) -> str:
        """
        Extract listing ID from a bazos.sk URL.

        Example: https://motocykle.bazos.sk/inzerat/123456789/some-title -> "123456789"
        """
        match = re.search(r"/inzerat/(\d+)/", url)
        if match:
            return match.group(1)
        # Fallback: hash the URL if pattern doesn't match
        return str(hash(url))

    def scrape_list_page(self, page_number: int) -> list[str]:
        """
        Scrape a list page to extract listing URLs.

        bazos.sk uses pagination:
        - Page 1: https://motocykle.bazos.sk/
        - Page 2: https://motocykle.bazos.sk/20/
        - Page 3: https://motocykle.bazos.sk/40/ (20 per page, offset-based)
        """
        # bazos.sk uses offset-based pagination: /0/, /20/, /40/, etc.
        if page_number == 1:
            url = f"{self.base_url}/"
        else:
            offset = (page_number - 1) * 20
            url = f"{self.base_url}/{offset}/"

        logger.info(f"Fetching list page: {url}")

        # Fetch with list page caching
        html = self.fetch_page(url, cache_key=str(page_number), is_list_page=True)

        if html is None:
            logger.warning(f"Failed to fetch list page {page_number}")
            return []

        # Parse HTML
        tree = HTMLParser(html)

        # Find all listing links
        # bazos.sk listings are in divs with class "inzeraty inzeratyflex"
        # Each listing has a link: <a href="/inzerat/123456/title">
        listing_urls = []

        # Find all links that match /inzerat/ pattern
        for link in tree.css("a[href*='/inzerat/']"):
            href = link.attributes.get("href", "")
            if href and "/inzerat/" in href:
                # Make absolute URL
                if href.startswith("/"):
                    full_url = f"{self.base_url}{href}"
                elif href.startswith("http"):
                    full_url = href
                else:
                    full_url = f"{self.base_url}/{href}"

                listing_urls.append(full_url)

        # Deduplicate while preserving order
        seen = set()
        unique_urls = []
        for url in listing_urls:
            # Extract just the ID part to deduplicate
            listing_id = self._extract_listing_id(url)
            if listing_id not in seen:
                seen.add(listing_id)
                unique_urls.append(url)

        logger.info(f"Found {len(unique_urls)} unique listings on page {page_number}")
        return unique_urls

    def parse_listing(self, url: str, html: str, scrape_run_id: str) -> Listing | None:
        """
        Parse a bazos.sk listing detail page.

        Args:
            url: The listing URL
            html: The HTML content
            scrape_run_id: Identifier for this scrape run

        Returns:
            Parsed Listing object, or None if parsing failed
        """
        try:
            tree = HTMLParser(html)
            listing_id = self._extract_listing_id(url)
            now = datetime.now()

            # Extract title
            title_elem = tree.css_first("h1.nadpisdetail")
            if not title_elem:
                title_elem = tree.css_first("h1")  # Fallback to any h1
            title = title_elem.text(strip=True) if title_elem else ""

            if not title:
                logger.warning(f"No title found for {url}")
                return None

            # Extract description
            desc_elem = tree.css_first("div.popisdetail")
            description = desc_elem.text(strip=True) if desc_elem else None

            # Extract price
            price_raw: float | None = None
            currency = None
            price_text = None

            # Try div.inzeratycena first (some listings)
            price_elem = tree.css_first("div.inzeratycena")
            if price_elem:
                price_text = price_elem.text(strip=True)

            # Fallback: find in table structure (td containing "Cena:" followed by td with price)
            if not price_text:
                for td in tree.css("td"):
                    text = td.text(strip=True)
                    if text == "Cena:":
                        # Next sibling should have the price
                        parent = td.parent
                        if parent:
                            all_tds = parent.css("td")
                            # Find index of current td
                            for i, cell in enumerate(all_tds):
                                if cell == td and i + 1 < len(all_tds):
                                    price_text = all_tds[i + 1].text(strip=True)
                                    break
                        break

            # Parse the price if found
            if price_text:
                # Remove whitespace and parse
                # Example: "5 500 €" or "120000 Kč" or "16 000 €"
                price_clean = re.sub(r"\s+", "", price_text)
                price_match = re.search(r"([\d,\.]+)", price_clean)
                if price_match:
                    try:
                        price_raw = float(price_match.group(1).replace(",", "."))
                        if "€" in price_text or "EUR" in price_text:
                            currency = "EUR"
                        elif "Kč" in price_text or "CZK" in price_text:
                            currency = "CZK"
                    except ValueError:
                        pass

            # Extract location (city) from table
            city = None
            # Look for table row with "Lokalita:" or "Mesto:"
            for td in tree.css("td"):
                text = td.text(strip=True)
                if "Lokalita:" in text or "Mesto:" in text or "Lokality:" in text:
                    # Next sibling or parent row might have the location
                    parent = td.parent
                    if parent:
                        all_text = parent.text(strip=True)
                        # Extract text after the label
                        location_text = re.sub(r"(Lokalita|Mesto|Lokality):?\s*", "", all_text).strip()
                        if location_text and len(location_text) < 100:
                            if "," in location_text:
                                city = location_text.split(",")[0].strip()
                            else:
                                city = location_text
                            break

            # Extract posted date from page
            # bazos.sk shows multiple dates: -TOP- refreshes and bump dates
            # The OLDEST date is the original posting date
            posted_at = None
            dates_found = []

            for span in tree.css("span.velikost10"):
                text = span.text(strip=True)
                # Match patterns like "- [22.8. 2026]" or "-TOP- [24.8. 2026]"
                date_match = re.search(r"\[(\d{1,2})\.(\d{1,2})\.\s*(\d{4})\]", text)
                if date_match:
                    try:
                        day, month, year = date_match.groups()
                        date_obj = datetime(int(year), int(month), int(day)).date()
                        dates_found.append(date_obj)
                    except ValueError as e:
                        logger.debug(f"Failed to parse date {text}: {e}")

            # Use the oldest date as the original posting date
            if dates_found:
                posted_at = min(dates_found)
            else:
                # No date found - log it and set None
                logger.warning(f"No posting date found for {url}")

            # Detect parts listings (rozpredám, na diely, etc.)
            # CZ/SK/PL keywords for parts/parting out
            is_parts_listing = False
            parts_keywords = [
                "rozpredam",
                "rozpredám",
                "rozprodej",
                "rozprodám",
                "na diely",
                "na díly",
                "na czesci",
                "na części",
                "diely",
                "díly",
                "časti",
                "czesci",
                "części",
            ]

            # Check both title and description
            text_to_check = (title + " " + (description or "")).lower()
            if any(keyword in text_to_check for keyword in parts_keywords):
                is_parts_listing = True

            # Extract seller type (check if it's a dealer)
            seller_type: Any = "private"  # Default to private
            # bazos.sk doesn't clearly mark dealers, so we'll check description for keywords
            if description:
                dealer_keywords = [
                    "firma",
                    "predaj motocyklov",
                    "moto obchod",
                    "predajca",
                    "bazár",
                ]
                if any(kw in description.lower() for kw in dealer_keywords):
                    seller_type = "dealer"

            # Count photos
            photos_count = None
            photo_links = tree.css("div.obrazek img")
            if photo_links:
                photos_count = len(photo_links)

            # Extract structured data from text using parsers
            mileage_data = text_extract.extract_mileage(title, description)
            year_data = text_extract.extract_year(title, description)
            negotiable_data = text_extract.extract_price_negotiable(title, description)
            crash_data = text_extract.extract_crash_damage(title, description)
            restriction_data = text_extract.extract_restriction(title, description)
            service_data = text_extract.extract_service_book(title, description)

            # Build raw_attrs with any extra data
            raw_attrs: dict[str, Any] = {
                "raw_title": title,
                "raw_description": description,
                "raw_price_text": price_elem.text(strip=True) if price_elem else None,
                "raw_location": city,
                "mileage_raw_match": mileage_data.get("raw_match"),
                "year_raw_match": year_data.get("raw_match"),
                "restriction_raw_match": restriction_data.get("raw_match"),
                "service_raw_match": service_data.get("raw_match"),
            }

            # Create Listing object
            listing = Listing(
                id=f"bazos.sk:{listing_id}",
                site="bazos.sk",
                url=url,
                site_listing_id=listing_id,
                title_raw=title,
                description_raw=description,
                model_canonical=None,  # Will be resolved later
                manufacturer=None,  # Will be resolved later
                year=year_data.get("year"),
                mileage_km=mileage_data.get("mileage_km"),
                displacement_cc=None,  # Will be extracted from text later
                power_kw=None,  # Will be extracted from text later
                price_raw=price_raw,
                currency=currency,
                price_eur=None,  # Will be converted later
                price_negotiable=negotiable_data.get("negotiable"),
                vat_deductible=None,
                country="SK",
                region=None,
                city=city,
                lat=None,
                lon=None,
                seller_type=seller_type,
                posted_at=posted_at,
                first_seen_at=now,
                last_seen_at=now,
                is_active=True,
                condition_notes=None,
                has_abs=None,  # Will be extracted from text later
                has_crash_damage=crash_data.get("has_crash_damage"),
                is_restricted_35kw=restriction_data.get("is_restricted_35kw"),
                service_book=service_data.get("service_book"),
                owners_count=None,
                photos_count=photos_count,
                is_parts_listing=is_parts_listing,
                raw_attrs=raw_attrs,
                dupe_group_id=None,
                scrape_run_id=scrape_run_id,
            )

            logger.debug(f"Parsed listing: {listing.id} - {listing.title_raw[:50]}")
            return listing

        except Exception as e:
            logger.error(f"Failed to parse listing {url}: {e}", exc_info=True)
            return None
