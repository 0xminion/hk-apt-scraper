---
name: hk-apartment-scraper
description: Scrapes squarefoot.com.hk for HK apartment rentals matching specific criteria. Runs daily via cron.
---

# HK Apartment Rental Scraper

## What it does
Scrapes THREE sources for rental listings across 6+ HK Island districts:

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

Filters: 500-850 sqft, HKD$25k-55k/mo, building age <25yr, listing freshness <7 days, scores by floor height, direction, value-for-money, building newness, bedrooms, recency.

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
- **Critical**: squarefoot has trailing spaces in CSS class names. Use lambda selector:
  ```python
  soup.find_all('div', class_=lambda c: bool(c) and 'property_item' in str(c))
  ```
  NOT `class_='property_item'` (won't match due to trailing space)
- HTML structure: `div.property_item` > `div.content.sqfoot_property_card` contains all data
- Building name in `div.header.cat`, address in `div.meta`, price in `span.priceDesc`
- Pagination: `/page-{N}` suffix

## Building age enrichment
Building age is NOT on listing cards — only on detail pages. Approach:
1. Maintain cache in `hk_building_ages.json` (building_name → age)
2. For each listing, check cache first
3. For unknown buildings, fetch ONE detail page per building to get age
4. Parse with: `re.search(r'Building age:\\s*(\\d+)\\s*Year', page_text)`
5. Filter out buildings older than MAX_BUILDING_AGE
- First run fetches ~200 detail pages (slow). Subsequent runs only check new buildings (fast).
- Centanet has building age directly in listing data (no enrichment needed)

## Other HK rental sites — tested reality
| Site | Status | Notes |
|---|---|---|
| **centanet.com** | ✅ Scrapable | Nuxt SSR with `__NUXT__` data. Node.js evaluates JS to extract structured JSON. Building age included in listing data. ~62 unique HK Island listings after dedup. |
| **28hse.com** | ✅ Scrapable | Same parent company as squarefoot (28Hse Ltd). Same URL structure (`/en/rent/a1/dg4`), same lambda class fix needed. ~80-90% listing overlap with squarefoot — marginal value-add. |
| **midland.com.hk** | ❌ React SPA | Fully client-rendered. No listings in raw HTML. Would need `playwright` + correct district codes. District code format: `Hong-Kong-Island-{District}-D-{code}`. Building age shown on cards if you can render. |
| **centaline.com.hk** | ❌ Timeout | Connection timeout from this server. Can't reach. |
| **house730.com** | ❌ Cloudflare 403 | Hard Cloudflare block. Would need `playwright`. |
| **spacious.hk** | ❌ Cloudflare | Cloudflare challenge page blocks all access. Client-rendered React app with undocumented GraphQL API at `/graphql`. |

## Cron timezone note
System timezone is CEST (UTC+2). To run at 11am GMT+8 (03:00 UTC), use cron `0 5 * * *` (05:00 CEST). Always verify with `date -u; date` before setting cron.
