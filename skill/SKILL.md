---
name: hk-apartment-scraper
description: Scrapes squarefoot.com.hk for HK apartment rentals matching specific criteria. Runs daily via cron.
---

# HK Apartment Rental Scraper

## What it does
Scrapes FOUR sources for rental listings across HK Island:

### Source 1: Squarefoot.com.hk (cloudscraper)
Districts: Wan Chai/Admiralty, Causeway Bay, Tin Hau, Central/Sheung Wan, Sai Ying Pun, Kennedy Town

### Source 2: Midland.com.hk (Playwright + API)
Midland's React app uses a JSON API at `data.midland.com.hk/search/v2/properties`. Playwright is needed to get the Bearer auth token, then the API is called directly (fast, structured data).

District codes:
- 130ND10012 = Wanchai
- 130ND10013 = Causeway Bay
- 130ND10014 = Tin Hau
- 130ND10004 = Central / Sheung Wan
- 130ND10002 = Sai Ying Pun
- 130ND10001 = Kennedy Town
- 130ND10005 = Admiralty

### Source 3: Centanet.com / 中原地產 (Node.js + __NUXT__)
Nuxt.js SSR app — data embedded in `window.__NUXT__` state. Node.js evaluates the JS function to extract structured JSON.

Districts: Wan Chai, Causeway Bay, Happy Valley, Tin Hau, Central/Sheung Wan, Sai Ying Pun, Kennedy Town

URL pattern: `https://hk.centanet.com/findproperty/list/rent/{neighborhood}?adsource=DMK-G0011&offset={N}`
- 24 listings per page, offset-based pagination
- Territory filter: `scope.terr == "港島"` (HK Island)
- District in `scope.db`, neighborhood in `scope.hma`
- Building age directly in `buildingAge` field (no detail page needed!)
- Net area in `areaInfo.nSize`, rent in `priceInfo.rent`

### Source 4: House730.com (Camoufox + CF bypass)
House730.com has hard Cloudflare 403 for all datacenter IPs. Uses Camoufox (stealth Firefox) to bypass CF, then intercepts the API response from `api.house730.com/Property/QueryProperty`. Requires GTK3 libs installed at `~/.local/lib/gtk3/`.

Filters via API interception: `regionCode=HK01` (HK Island), `minSaleableArea=500`, `maxSaleableArea=850`, `minRentPrice=25000`, `maxRentPrice=55000`. Additional client-side filtering: excludes low floors (unitFloor=1 / 低層), buildings older than 25yr, mid-levels keyword match.

Script: `~/.hermes/scripts/house730_scraper.py`

Filters: 500-850 sqft, HKD$25k-55k/mo, building age <25yr, listing freshness <7 days, excludes Mid-Levels, excludes lower/ground floors (Low Floor, Ground Floor, Lower Floor). Scores by floor height, direction, value-for-money, building newness, bedrooms, recency.

## Deduplication pipeline
Three-stage dedup before results are delivered:

1. **Intra-source** — each scraper deduplicates its own results (e.g., Centanet across 7 neighborhood searches)
2. **Cross-source** — deduplicates across Squarefoot/Midland/Centanet using building+price+area+address hash. Keeps listing with more complete data, breaks ties by source priority (Squarefoot > Midland > Centanet)
3. **Cross-run** — `seen` file ensures only truly new listings appear in daily reports

## Files
- Script: `~/.hermes/scripts/hk_apartment_scraper.py`
- Centanet scraper: `~/.hermes/scripts/centanet_scraper.js`
- Midland scraper: `~/.hermes/scripts/midland_scraper.js`
- Centanet results: `~/.hermes/scripts/centanet_results.json`
- House730 scraper: `~/.hermes/scripts/house730_scraper.py`
- House730 results: `~/.hermes/scripts/house730_results.json`
- Seen IDs: `~/.hermes/scripts/hk_seen_ids.json`
- State: `~/.hermes/scripts/hk_scraper_state.json`
- Building ages: `~/.hermes/scripts/hk_building_ages.json`
- Report: `~/.hermes/scripts/hk_report.txt`

## Cron job
Job ID: `62c44988b826`, runs daily at 05:00 CEST (03:00 UTC / 11:00 GMT+8).

## Running manually
```bash
python3 ~/.hermes/scripts/hk_apartment_scraper.py
```

## Key technical details
- Uses `cloudscraper` to bypass Cloudflare (squarefoot.com.hk has CF protection)
- BeautifulSoup with lxml parser
- **Squarefoot CSS selector**: `find_all('div', class_='property_item')` works directly (confirmed Apr 2026). If it returns 0, a lambda fallback is also tried:
  ```python
  soup.find_all('div', class_=lambda c: bool(c) and 'property_item' in str(c))
  ```
- **Retry logic**: Each page retries up to 3 times with 1.5s delays if no items found (handles intermittent rate-limiting)
- HTML structure: `div.property_item` > `div.content.sqfoot_property_card` contains all data
- Building name in `div.header.cat`, address in `div.meta`, price in `span.priceDesc`
- Pagination: `/page-{N}` suffix

## Mid-Levels exclusion
Listings are filtered out if any of these fields contain mid-levels variants: building name, address, district, description, or detail URL. Keywords matched: `mid-levels`, `mid levels`, `midlevels`, `the mid-levels`, `mid_levels`.

## Building age enrichment
Building age is NOT on listing cards — only on detail pages. Approach:
1. Maintain cache in `hk_building_ages.json` (building_name → age)
2. For each listing, check cache first
3. For unknown buildings, fetch ONE detail page per building to get age
4. Parse with: `re.search(r'Building age:\s*(\d+)\s*Year', page_text)`
5. Filter out buildings older than MAX_BUILDING_AGE
- First run fetches ~200 detail pages (slow). Subsequent runs only check new buildings (fast).
- Centanet has building age directly in listing data (no enrichment needed)

## Floor filter (Apr 2026)
Listings with "Low Floor", "Ground Floor", or "Lower Floor" are excluded. This applies to:
- **Squarefoot**: parses floor from card text (e.g., "Low Floor 3")
- **Midland**: parses floor from URL segments (e.g., "...-Lower-Flat-...")
- **Centanet**: floor is null in listing data — not filtered (no floor info available)

## Cloudflare bypass — tested Apr 2026
Tested agent-browser, @browserless.io/browserless, @steel-dev/cli, bb-browser against house730.com and spacious.hk. None can bypass CF:
- **house730.com**: Hard 403 block for all datacenter IPs (regardless of browser)
- **spacious.hk**: JS challenge doesn't resolve for headless browsers
- **Root cause**: IP reputation blocking, not browser fingerprinting. Would need residential proxy.
- Existing sources (Squarefoot, Midland, Centanet) remain the working set.

## Other HK rental sites — tested reality
| Site | Status | Notes |
|---|---|---|
| **centanet.com** | ✅ Scrapable | Nuxt SSR with `__NUXT__` data. Node.js evaluates JS to extract structured JSON. Building age included in listing data. ~62 unique HK Island listings after dedup. |
| **28hse.com** | ✅ Scrapable | Same parent company as squarefoot (28Hse Ltd). Same URL structure (`/en/rent/a1/dg4`), same lambda class fix needed. ~80-90% listing overlap with squarefoot — marginal value-add. |
| **midland.com.hk** | ✅ Via API | `midland_scraper.js` uses Playwright to get Bearer token, then queries `data.midland.com.hk/search/v2/properties` directly. ~178 HK Island listings. Fast and reliable. |
| **centaline.com.hk** | ❌ Timeout | Connection timeout from this server. Can't reach. |
| **house730.com** | ✅ Via Camoufox | Hard CF 403 bypassed with Camoufox stealth Firefox. Intercepts API (`api.house730.com/Property/QueryProperty`). ~673 HK Island matches, ~11 pass all filters. Script: `house730_scraper.py`. GTK3 libs at `~/.local/lib/gtk3/`. |
| **spacious.hk** | ⚠️ CF bypassed, limited value | Camoufox bypasses CF JS challenge. Site is fully client-rendered React. /rent page returns 404 (URL changed). Would need Camoufox + significant reverse engineering. Low priority. |

## Cron timezone note
System timezone is CEST (UTC+2). To run at 11am GMT+8 (03:00 UTC), use cron `0 5 * * *` (05:00 CEST). Always verify with `date -u; date` before setting cron.
