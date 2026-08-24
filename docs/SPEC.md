# Claude Code Prompt: A2 Sportbike Market Scraper & Price Analyzer

Paste everything below the line into Claude Code.

---

Build a Python project that scrapes second-hand motorcycle listings from Czech, Slovak, and Polish classifieds, normalizes them into one dataset, and analyzes fair market price. Project name: `a2moto`.

## Goal

I want to buy a used A2-legal sportbike and I don't know what a fair price is. The tool must tell me, for a given model/year/mileage, what the market price actually is, and flag listings that are cheap relative to prediction.

## Target inventory

Two classes of bike:

1. **Native A2** (stock power 35 kW / 47 hp or under, but I still want them for price comparison): Ninja 400, Ninja 500, CB500F/CBR500R, CB500X, Z400, Z500, RS 457, MT-03, R3, RC 390, Duke 390, SV650 (restricted), Trident 660 (restricted).
2. **Restrictable** (stock 50 hp+, up to 70 kW / 94 hp stock, restrictable to 35 kW): Ninja 650, Z650, CBR650R, CB650R, MT-07, R7, XSR700, Tenere 700, SV650, GSX-8S, GSX-8R, Trident 660, Tiger Sport 660, CF Moto 700CL-X, Aprilia RS 660 (94 hp, borderline, include and flag).

Store the model whitelist in a YAML config file (`config/models.yaml`) with fields per model: canonical name, manufacturer, list of regex aliases as they appear in listing titles across three languages, stock kW, stock hp, cc, wet weight kg, `a2_native` bool, `restrictable` bool.

**A2 eligibility logic** must be a real function, not a hardcoded flag:
- restricted power ≤ 35 kW
- power-to-weight ≤ 0.2 kW/kg at 35 kW (so wet weight ≥ 175 kg fails nothing here, but check it)
- stock power ≤ 70 kW (a restricted bike may not derive from a machine over double the restricted output)

Emit a warning when a listing's model fails eligibility so I can see borderline cases instead of silently dropping them.

## Sites to scrape

Write one scraper module per site, all implementing the same `BaseScraper` interface. Start with these, ordered by priority:

- `bazos.sk` (SK, `motorky` category)
  - **Note on posted_at**: bazos.sk shows multiple dates (promotions, bumps, refreshes). The scraper derives `posted_at` from `min()` of visible dates, which represents the oldest date shown. This may be a renewal rather than the original posting date. Analysis in step 7 must not treat it as a definitive listing age; use it only for relative recency and assume it's a lower bound on actual age.
- `bazos.cz` (CZ)
- `autobazar.eu` (SK/CZ, has structured filters)
- `motorkary.cz` (CZ, bazar section)
- `tipmoto.com` (CZ/SK)
- `sauto.cz` (CZ, motorcycle section)
- `olx.pl` (PL)
- `otomoto.pl` (PL, structured, has API-ish JSON endpoints, check `__NEXT_DATA__`)

Before writing each scraper, fetch and read the site's `robots.txt` and record what it allows in a comment at the top of the module. Respect it. Rate-limit every scraper to 1 request per 2 seconds per domain by default, configurable. Set a real User-Agent that identifies the tool. Use `httpx` with retries and exponential backoff. Cache raw HTML to disk (`data/cache/{site}/{listing_id}.html.gz`) so re-parsing never re-hits the network. Do not attempt to bypass Cloudflare, captchas, or login walls. If a site blocks the scraper, log it and skip; don't work around it.

Prefer parsing embedded JSON (`__NEXT_DATA__`, JSON-LD `Product`/`Offer` schema) over CSS selectors where available. It survives redesigns better.

## New-bike reference prices

A used price is meaningless without the new price it decays from. Scrape current MSRP for every model in `models.yaml` from manufacturer sites, per country, since CZ/SK/PL list different numbers.

Sources, in order of preference:

1. **Manufacturer country sites**, which usually expose a price in a configurator or a model page: `kawasaki.cz`, `kawasaki.sk`, `kawasaki.pl`, `honda.cz` / `moto.honda.pl`, `yamaha-motor.eu` (country selector in URL path), `suzuki.cz` / `suzuki-motor.pl`, `ktm.com`, `aprilia.com`, `triumphmotorcycles.cz`, `cfmoto.cz` / `cfmoto.pl`. Many of these are a single page per model with a JSON-LD `Offer` block. Check that first.
2. **Official importer price lists (PDF)**. Kawasaki and Honda importers in CZ/SK publish an annual `ceník` PDF. If a PDF is linked from the official site, download it, extract the table with `pdfplumber`, and store it. These are more reliable than the configurator because they list every trim and the year.
3. **Official dealer stock pages** for the current model year, as a fallback when the manufacturer hides price behind "contact dealer".

Do not scrape aggregator sites for MSRP. They report stale or invented numbers and you'll poison the baseline.

Store in a separate table `new_prices`:

```
id                  TEXT PK      # f"{model_canonical}:{country}:{model_year}"
model_canonical     TEXT
model_year          INT
country             TEXT
price_raw           REAL
currency            TEXT
price_eur           REAL
includes_vat        BOOL         # CZ/SK/PL list VAT-inclusive; verify per site and record
on_road_costs_eur   REAL         # NULL unless the source states it
source_type         TEXT         # oem_page / oem_pricelist_pdf / dealer
source_url          TEXT
observed_at         DATE
```

Flag `includes_vat` explicitly rather than assuming. Comparing a VAT-inclusive new price to a VAT-deductible dealer used price is a 20% error and it will silently wreck the depreciation curve.

**Historical MSRP.** Current-year MSRP alone can't tell you what a 2019 Ninja 650 cost new in 2019. Handle this in two tiers: (a) let me hand-populate `config/msrp_history.yaml` with known launch prices per model-year, and load it into the same table with `source_type: manual`; (b) where history is missing, back-cast current MSRP using country CPI or a flat 3%/yr and mark those rows `is_estimated = true`. Never mix estimated and observed rows in a chart without visually distinguishing them.

## Data schema

One SQLite database (`data/listings.db`) via SQLAlchemy. Core table `listings`:

```
id                  TEXT PK       # f"{site}:{site_listing_id}"
site                TEXT
url                 TEXT
site_listing_id     TEXT
title_raw           TEXT
description_raw     TEXT
model_canonical     TEXT          # resolved via models.yaml, NULL if unmatched
manufacturer        TEXT
year                INT
mileage_km          INT
displacement_cc     INT
power_kw            REAL          # as advertised
price_raw           REAL
currency            TEXT          # CZK / EUR / PLN
price_eur           REAL          # normalized
price_negotiable    BOOL
vat_deductible      BOOL
country             TEXT          # CZ / SK / PL
region              TEXT
city                TEXT
lat, lon            REAL          # optional geocode
seller_type         TEXT          # private / dealer
posted_at           DATE
first_seen_at       DATETIME
last_seen_at        DATETIME
is_active           BOOL
condition_notes     TEXT
has_abs             BOOL
has_crash_damage    BOOL
is_restricted_35kw  BOOL
service_book        BOOL
owners_count        INT
photos_count        INT
raw_attrs           JSON          # everything site-specific
scrape_run_id       TEXT
```

Second table `price_history` (listing_id, observed_at, price_eur) so repeated runs capture price drops. A price drop is the single strongest negotiation signal, so track it.

## Extraction rules

Most of these sites dump everything into free text, so structured fields are unreliable. Build a `parsers/text_extract.py` with regex + heuristics that runs on title + description in Czech, Slovak, and Polish:

- Mileage: handle `km`, `tis. km`, `tys. km`, `przebieg`, `najeto`, `najazdené`, thousand separators as space/dot/comma. Reject values > 200,000 or < 100 as suspicious, flag rather than drop.
- Year: `r.v.`, `rok výroby`, `rocznik`, bare 4-digit 1990-2026. Cross-check against model production years from config; flag mismatches.
- Price: `Kč`, `CZK`, `€`, `EUR`, `zł`, `PLN`. Handle `dohoda`, `dohodou`, `do negocjacji` → negotiable flag. Handle `cena při osobním jednání` → price unknown, not zero.
- Damage keywords: `havarované`, `bourané`, `po nehode`, `uszkodzony`, `rozbite` → `has_crash_damage`.
- Restriction: `omezeno na 35kW`, `obmedzené`, `A2`, `ograniczony do 35kW`.
- Service: `servisní knížka`, `servisná knižka`, `książka serwisowa`.

Write unit tests for every extractor using real listing text as fixtures. Save fixtures in `tests/fixtures/`. Test the ambiguous cases: "35kW" appearing in a description that also says the restriction was removed; mileage in miles; prices that are obviously per-month financing.

## Normalization

- Currency: fetch daily ECB rates (`https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml`), cache locally, convert everything to EUR at the rate for `posted_at` where known, else latest. Never hardcode a rate.
- Model matching: fuzzy match title against aliases from `models.yaml`. Use exact regex first, then rapidfuzz with a threshold, then leave NULL. Log unmatched titles to `data/unmatched.txt` so I can extend the alias list.
- Deduplication: same bike is often cross-posted. Dedupe on a fuzzy key of (model, year, mileage ±2%, price ±5%, first 2 photo perceptual hashes if available). Keep all rows, mark duplicates with a `dupe_group_id` instead of deleting.

## Analysis

Module `analysis/`:

1. **Hedonic price model.** Log-price OLS or gradient boosting on: model_canonical (categorical), age in years, mileage_km, mileage², country, seller_type, has_crash_damage, is_restricted. Report R², coefficient table, and per-model median absolute error. Use scikit-learn. Print the depreciation coefficient in plain terms: EUR lost per year, EUR lost per 10,000 km, per model.

2. **Deal score.** For each active listing: residual = actual price − predicted price, expressed both in EUR and as a percentile within its model cohort. Sort ascending. That list is the main output. Suppress listings with crash damage or missing mileage from the top of the list, but still show them in a separate section.

3. **Per-model summary table**: n listings, median price EUR, IQR, median mileage, median year, price per 1000 km, and how many listings appeared in the last 30 days (liquidity, because a rare bike means less negotiating room and a longer search).

4. **Cross-border spread.** Same model, same age band, compare CZ vs SK vs PL medians. Include a note on whether the spread exceeds plausible import/registration cost, since a 600 EUR spread is not a deal if re-registration eats it.

5. **Time-on-market.** Using first_seen/last_seen, estimate how long listings survive by price percentile. A bike sitting 60 days above prediction is a bike whose seller will negotiate.

6. **Retained-value curve.** For each model, plot median used price as a percentage of the new price for that model-year and country. Fit the curve and report: percentage retained at year 1, 3, 5, and the age at which the curve flattens. That flattening point is the cheapest place on the curve to buy, because from there depreciation stops being the dominant cost.

7. **New-vs-used break-even.** For each model, compute the EUR gap between the cheapest sane used listing and the new price in the same country, then express it as cost per year of age and cost per 1000 km already on the clock. Output a per-model verdict line, e.g. "Ninja 650: 2019/24k km at 5,600 EUR vs 9,900 new. 4,300 EUR saved, 1,075/yr." Include warranty status in the note: a two-year-old bike may still carry factory warranty, which is real money the raw price gap hides.

8. **Overpriced-used detector.** Flag any used listing priced above 85% of current new MSRP in the same country. Those exist in volume on bazos and they are the main way a first-time buyer loses money. Put them in their own section of the report, labeled clearly.

## Outputs

- `a2moto scrape --sites all --max-pages 20`
- `a2moto scrape-new --countries cz,sk,pl` (OEM MSRP refresh, run weekly, it changes rarely)
- `a2moto parse` (re-parse from cache, no network)
- `a2moto analyze --model "Ninja 650" --max-price 6000 --max-mileage 30000`
- `a2moto report` → single self-contained HTML file with Plotly charts: price vs mileage scatter colored by year per model, retained-value curves with the new price anchored at year 0, deal-score table with clickable links, country boxplots, new-vs-used gap table.
- CSV and Parquet export of the full normalized table.

## Engineering constraints

- Python 3.11+, `uv` or `pip` with `pyproject.toml`.
- `httpx`, `selectolax` (faster than bs4), `pydantic` v2 for the listing model, `sqlalchemy`, `pandas`, `scikit-learn`, `plotly`, `typer` for CLI, `rapidfuzz`, `pytest`.
- Playwright only as a fallback for sites that hard-require JS, in a separate optional extra. Don't reach for it by default.
- Every scraper must fail loudly and independently. One broken site must not kill the run. Wrap each in try/except, log the traceback, continue, and print a per-site success/failure summary at the end.
- Structured logging with `structlog` or stdlib logging to `logs/`, one file per run.
- Type hints everywhere, `ruff` and `mypy` clean.

## Build order

Do this incrementally and show me working output at each stage before moving on:

1. Project scaffold, config, pydantic schema, DB layer, one passing test.
2. `bazos.sk` scraper end-to-end, 50 listings in the DB.
3. Text extractors + tests against those 50 listings. Show me the parse accuracy.
4. Second and third scrapers.
5. Normalization + dedup.
6. OEM MSRP scraping for CZ, one manufacturer end-to-end, then the rest.
7. Analysis + HTML report.
8. Remaining classifieds scrapers.

Don't write all eight scrapers before proving one works. Ask me to check the output after step 3.
