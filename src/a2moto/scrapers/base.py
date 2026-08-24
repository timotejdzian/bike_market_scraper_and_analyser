"""Base scraper class with caching, rate limiting, and error isolation."""

import gzip
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
from pydantic import BaseModel

from a2moto.models import Listing

logger = logging.getLogger(__name__)


class ScraperConfig(BaseModel):
    """Configuration for a scraper instance."""

    rate_limit_seconds: float = 2.0
    """Minimum seconds between requests to the same domain."""

    max_retries: int = 3
    """Maximum number of retry attempts for failed requests."""

    timeout_seconds: float = 30.0
    """HTTP request timeout in seconds."""

    cache_dir: Path = Path("data/cache")
    """Base directory for caching raw responses."""

    cache_ttl_days: int = 7
    """Cache TTL in days for detail pages. Detail pages older than this are re-fetched to capture price changes."""

    list_page_cache_ttl_hours: int = 6
    """Cache TTL in hours for list pages. List pages expire quickly to discover new listings."""

    force_refresh: bool = False
    """If True, bypass cache and re-fetch all pages."""

    user_agent: str = (
        "a2moto/0.1.0 (+https://github.com/timotejdzian/bike_market_scraper_and_analyser) "
        "A2 sportbike market research tool"
    )
    """User-Agent string identifying this scraper."""


class BaseScraper(ABC):
    """
    Abstract base class for site-specific scrapers.

    Provides:
    - Automatic rate limiting per domain
    - Persistent caching of raw HTML responses
    - Retry logic with exponential backoff
    - Error isolation (one listing failure doesn't stop the run)
    - Structured logging
    """

    def __init__(self, config: ScraperConfig | None = None) -> None:
        """
        Initialize the scraper.

        Args:
            config: Optional scraper configuration. Uses defaults if not provided.
        """
        self.config = config or ScraperConfig()
        self._last_request_time: dict[str, float] = {}
        self._session: httpx.Client | None = None
        self._robots_parsers: dict[str, RobotFileParser] = {}
        self._blocked_domains: set[str] = set()
        self._setup_cache_dir()

    @property
    @abstractmethod
    def site_name(self) -> str:
        """
        Unique identifier for this site (e.g., 'bazos.sk').

        Used for cache directory naming and logging.
        """
        ...

    @property
    @abstractmethod
    def base_url(self) -> str:
        """Base URL for the site (e.g., 'https://bazos.sk')."""
        ...

    @property
    @abstractmethod
    def robots_txt_notes(self) -> str:
        """
        Notes about what robots.txt allows/disallows.

        This serves as documentation and a reminder to respect the site's rules.
        """
        ...

    def _setup_cache_dir(self) -> None:
        """Create cache directory structure if it doesn't exist."""
        cache_path = self.config.cache_dir / self.site_name
        cache_path.mkdir(parents=True, exist_ok=True)
        # Create subdirectory for list pages
        (cache_path / "list").mkdir(exist_ok=True)
        logger.info(f"Cache directory for {self.site_name}: {cache_path}")

    def _fetch_robots(self, domain: str) -> RobotFileParser:
        """
        Fetch and parse robots.txt for a domain.

        Args:
            domain: The domain to fetch robots.txt from (e.g., 'bazos.sk')

        Returns:
            Parsed RobotFileParser instance
        """
        if domain in self._robots_parsers:
            return self._robots_parsers[domain]

        robots_url = f"https://{domain}/robots.txt"
        logger.info(f"Fetching robots.txt from {robots_url}")

        rp = RobotFileParser()
        rp.set_url(robots_url)

        try:
            # Fetch robots.txt without rate limiting (first request to domain)
            session = self._get_session()
            response = session.get(robots_url)
            response.raise_for_status()

            # Parse the content
            rp.parse(response.text.splitlines())

            # Print parsed rules on first run
            logger.info(f"Parsed robots.txt for {domain}:")
            logger.info(f"  User-agent: {self.config.user_agent}")
            logger.info(f"  Can fetch /: {rp.can_fetch(self.config.user_agent, f'https://{domain}/')}")

            # Log some example paths to show what's allowed
            test_paths = ["/", "/search.php", "/motorky/", "/api/"]
            for path in test_paths:
                can_fetch = rp.can_fetch(self.config.user_agent, f"https://{domain}{path}")
                logger.info(f"  Can fetch {path}: {can_fetch}")

            self._robots_parsers[domain] = rp

        except Exception as e:
            logger.warning(f"Failed to fetch robots.txt from {domain}: {e}")
            logger.warning(f"Proceeding with permissive default")
            # Create a permissive default that allows everything
            rp.parse([])
            self._robots_parsers[domain] = rp

        return rp

    def _is_allowed_by_robots(self, url: str) -> bool:
        """
        Check if a URL is allowed by robots.txt.

        Args:
            url: The URL to check

        Returns:
            True if allowed, False otherwise
        """
        parsed = urlparse(url)
        domain = parsed.netloc

        # Check if domain is already blocked
        if domain in self._blocked_domains:
            return False

        rp = self._fetch_robots(domain)
        return rp.can_fetch(self.config.user_agent, url)

    def _get_session(self) -> httpx.Client:
        """Get or create an HTTP client with retry logic."""
        if self._session is None:
            transport = httpx.HTTPTransport(retries=self.config.max_retries)
            self._session = httpx.Client(
                transport=transport,
                timeout=self.config.timeout_seconds,
                headers={"User-Agent": self.config.user_agent},
                follow_redirects=True,
            )
        return self._session

    def _rate_limit(self, url: str) -> None:
        """
        Enforce rate limiting for a URL's domain.

        Args:
            url: The URL being requested (domain extracted from netloc)
        """
        netloc = urlparse(url).netloc
        last_time = self._last_request_time.get(netloc, 0.0)
        elapsed = time.time() - last_time
        if elapsed < self.config.rate_limit_seconds:
            sleep_time = self.config.rate_limit_seconds - elapsed
            logger.debug(f"Rate limiting {netloc}: sleeping {sleep_time:.2f}s")
            time.sleep(sleep_time)
        self._last_request_time[netloc] = time.time()

    def _get_cache_path(self, cache_key: str, is_list_page: bool = False) -> Path:
        """
        Get the cache file path for a page.

        Args:
            cache_key: Unique identifier (listing ID or page number)
            is_list_page: True if this is a list/index page, False for detail page

        Returns:
            Path to the gzipped HTML cache file
        """
        # Sanitize cache_key to create a safe filename
        safe_key = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(cache_key))

        if is_list_page:
            return self.config.cache_dir / self.site_name / "list" / f"{safe_key}.html.gz"
        else:
            return self.config.cache_dir / self.site_name / f"{safe_key}.html.gz"

    def _is_cache_valid(self, cache_path: Path, is_list_page: bool = False) -> bool:
        """
        Check if a cache file exists and is within TTL.

        Args:
            cache_path: Path to the cache file
            is_list_page: True if this is a list page (short TTL), False for detail page (long TTL)

        Returns:
            True if cache is valid and should be used
        """
        if not cache_path.exists():
            return False

        if self.config.force_refresh:
            return False

        # Check TTL based on page type
        try:
            mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
            age = datetime.now() - mtime

            if is_list_page:
                # List pages: short TTL (hours) to discover new listings
                max_age = timedelta(hours=self.config.list_page_cache_ttl_hours)
            else:
                # Detail pages: long TTL (days) to capture price changes
                max_age = timedelta(days=self.config.cache_ttl_days)

            return age <= max_age
        except Exception as e:
            logger.warning(f"Failed to check cache age for {cache_path}: {e}")
            return True  # If we can't check, assume valid to avoid re-fetch

    def _read_from_cache(
        self, cache_key: str, is_list_page: bool = False
    ) -> str | None:
        """
        Read cached HTML if it exists and is valid.

        Args:
            cache_key: Unique identifier (listing ID or page number)
            is_list_page: True if this is a list page, False for detail page

        Returns:
            Cached HTML content, or None if not cached or invalid
        """
        cache_path = self._get_cache_path(cache_key, is_list_page=is_list_page)

        if not self._is_cache_valid(cache_path, is_list_page=is_list_page):
            return None

        try:
            with gzip.open(cache_path, "rt", encoding="utf-8") as f:
                page_type = "list page" if is_list_page else "detail page"
                logger.debug(f"Cache hit for {self.site_name} {page_type}:{cache_key}")
                return f.read()
        except Exception as e:
            logger.warning(f"Failed to read cache for {cache_key}: {e}")
            return None

    def _write_to_cache(
        self, cache_key: str, content: str, is_list_page: bool = False
    ) -> None:
        """
        Write HTML content to cache.

        Args:
            cache_key: Unique identifier (listing ID or page number)
            content: HTML content to cache
            is_list_page: True if this is a list page, False for detail page
        """
        cache_path = self._get_cache_path(cache_key, is_list_page=is_list_page)
        try:
            with gzip.open(cache_path, "wt", encoding="utf-8") as f:
                f.write(content)
            page_type = "list page" if is_list_page else "detail page"
            logger.debug(f"Cached {self.site_name} {page_type}:{cache_key}")
        except Exception as e:
            logger.warning(f"Failed to write cache for {cache_key}: {e}")

    def fetch_page(
        self,
        url: str,
        cache_key: str | None = None,
        is_list_page: bool = False,
        use_cache: bool = True,
    ) -> str | None:
        """
        Fetch a page with robots.txt checking, automatic caching, and rate limiting.

        Args:
            url: The URL to fetch
            cache_key: Optional cache key (listing ID or page number) for caching
            is_list_page: True if this is a list/index page, False for detail page
            use_cache: Whether to use cached content if available

        Returns:
            HTML content, or None if the fetch failed or was blocked
        """
        netloc = urlparse(url).netloc

        # Check if domain is already blocked
        if netloc in self._blocked_domains:
            logger.warning(f"Skipping {url} - domain {netloc} is blocked")
            return None

        # Check robots.txt
        if not self._is_allowed_by_robots(url):
            logger.warning(f"Blocked by robots.txt: {url}")
            return None

        # Check cache first if cache_key is provided and caching is enabled
        if use_cache and cache_key:
            cached = self._read_from_cache(cache_key, is_list_page=is_list_page)
            if cached:
                return cached

        # Rate limit
        self._rate_limit(url)

        # Fetch with retry logic
        session = self._get_session()
        for attempt in range(self.config.max_retries + 1):
            try:
                logger.debug(f"Fetching {url} (attempt {attempt + 1})")
                response = session.get(url)
                response.raise_for_status()
                content = response.text

                # Cache if we have a cache_key
                if cache_key:
                    self._write_to_cache(cache_key, content, is_list_page=is_list_page)

                return content

            except httpx.HTTPStatusError as e:
                status = e.response.status_code

                # 403: Access forbidden - stop scraping this domain immediately
                if status == 403:
                    logger.error(
                        f"HTTP 403 Forbidden from {netloc}. "
                        f"Blocking domain and stopping scrape."
                    )
                    self._blocked_domains.add(netloc)
                    return None

                # 429: Rate limited - respect Retry-After header
                elif status == 429:
                    retry_after = e.response.headers.get("Retry-After")
                    if retry_after:
                        try:
                            wait_time = int(retry_after)
                            logger.warning(
                                f"HTTP 429 Rate Limited. Retry-After: {wait_time}s"
                            )
                            if wait_time <= 60:  # Cap at 60 seconds
                                time.sleep(wait_time)
                                continue
                            else:
                                logger.error(
                                    f"Retry-After too long ({wait_time}s), giving up"
                                )
                                return None
                        except ValueError:
                            logger.warning(f"Invalid Retry-After header: {retry_after}")

                    # No Retry-After or invalid - use exponential backoff
                    if attempt < self.config.max_retries:
                        backoff = 2 ** (attempt + 1)  # 2, 4, 8 seconds
                        logger.warning(f"HTTP 429, backing off {backoff}s")
                        time.sleep(backoff)
                    else:
                        logger.error(f"HTTP 429 persists after {attempt + 1} attempts")
                        return None

                # Other HTTP errors - retry with backoff
                elif attempt < self.config.max_retries:
                    backoff = 2**attempt
                    logger.warning(
                        f"HTTP {status} for {url}, retrying in {backoff}s"
                    )
                    time.sleep(backoff)
                else:
                    logger.error(f"Failed to fetch {url} after {attempt + 1} attempts: {e}")
                    return None

            except (httpx.RequestError, httpx.TimeoutException) as e:
                if attempt < self.config.max_retries:
                    backoff = 2**attempt
                    logger.warning(f"Request error for {url}, retrying in {backoff}s: {e}")
                    time.sleep(backoff)
                else:
                    logger.error(f"Failed to fetch {url} after {attempt + 1} attempts: {e}")
                    return None

        return None

    @abstractmethod
    def scrape_list_page(self, page_number: int) -> list[str]:
        """
        Scrape a list/index page to extract listing detail URLs.

        Args:
            page_number: The page number to scrape (1-indexed)

        Returns:
            List of absolute URLs to listing detail pages
        """
        ...

    @abstractmethod
    def parse_listing(self, url: str, html: str, scrape_run_id: str) -> Listing | None:
        """
        Parse a listing detail page into a Listing object.

        Args:
            url: The URL of the listing
            html: The HTML content of the page
            scrape_run_id: Identifier for this scrape run

        Returns:
            Parsed Listing object, or None if parsing failed
        """
        ...

    def scrape(
        self, max_pages: int = 10, scrape_run_id: str | None = None
    ) -> tuple[list[Listing], dict[str, Any]]:
        """
        Run the full scraping process for this site.

        Args:
            max_pages: Maximum number of list pages to scrape
            scrape_run_id: Optional identifier for this scrape run

        Returns:
            Tuple of (listings, stats) where stats contains success/failure counts
        """
        if scrape_run_id is None:
            scrape_run_id = f"{self.site_name}_{datetime.now().isoformat()}"

        logger.info(f"Starting scrape of {self.site_name}, max_pages={max_pages}")

        all_listings: list[Listing] = []
        stats = {
            "site": self.site_name,
            "pages_scraped": 0,
            "urls_found": 0,
            "listings_parsed": 0,
            "listings_failed": 0,
            "errors": [],
        }

        try:
            # Scrape list pages to get listing URLs
            all_urls: set[str] = set()
            for page_num in range(1, max_pages + 1):
                try:
                    logger.info(f"Scraping list page {page_num}/{max_pages}")
                    urls = self.scrape_list_page(page_num)
                    all_urls.update(urls)
                    stats["pages_scraped"] += 1
                    logger.info(f"Found {len(urls)} listings on page {page_num}")

                    # Stop if we got no results (likely past the last page)
                    if not urls:
                        logger.info("No listings found, stopping pagination")
                        break

                except Exception as e:
                    error_msg = f"Failed to scrape list page {page_num}: {e}"
                    logger.error(error_msg, exc_info=True)
                    stats["errors"].append(error_msg)
                    # Continue to next page despite error

            stats["urls_found"] = len(all_urls)
            logger.info(f"Found {len(all_urls)} unique listing URLs")

            # Parse each listing
            for url in all_urls:
                try:
                    # Extract listing ID from URL for caching
                    listing_id = self._extract_listing_id(url)
                    html = self.fetch_page(url, cache_key=listing_id, is_list_page=False)

                    if html is None:
                        stats["listings_failed"] += 1
                        continue

                    listing = self.parse_listing(url, html, scrape_run_id)
                    if listing:
                        all_listings.append(listing)
                        stats["listings_parsed"] += 1
                    else:
                        stats["listings_failed"] += 1

                except Exception as e:
                    error_msg = f"Failed to parse listing {url}: {e}"
                    logger.error(error_msg, exc_info=True)
                    stats["errors"].append(error_msg)
                    stats["listings_failed"] += 1
                    # Continue to next listing despite error

        except Exception as e:
            error_msg = f"Critical error during scrape: {e}"
            logger.error(error_msg, exc_info=True)
            stats["errors"].append(error_msg)

        logger.info(
            f"Scrape complete: {stats['listings_parsed']} parsed, "
            f"{stats['listings_failed']} failed from {stats['urls_found']} URLs"
        )

        return all_listings, stats

    @abstractmethod
    def _extract_listing_id(self, url: str) -> str:
        """
        Extract a unique listing ID from a detail page URL.

        Args:
            url: The listing detail URL

        Returns:
            A unique identifier for this listing on this site
        """
        ...

    def close(self) -> None:
        """Close the HTTP session and clean up resources."""
        if self._session:
            self._session.close()
            self._session = None

    def __enter__(self) -> "BaseScraper":
        """Context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.close()
