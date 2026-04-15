---
name: hk-apartment-scraper
description: Scrapes 4 sources for HK apartment rentals matching specific criteria. Runs daily via cron.
---

# HK Apartment Rental Scraper

## What it does
Scrapes FOUR sources for rental listings across HK Island. All sources run in parallel via ThreadPoolExecutor (~226s total).

### Source 1: Squarefoot.com.hk (Camoufox) 🔵
Uses Camoufox (stealth Firefox) to load pages, parses with BeautifulSoup. Falls back to cloudscraper if Camoufox fails.

Districts: Wan Chai/Admiralty, Causeway Bay, Tin Hau, Central/Sheung Wan, Sai Ying Pun, Kennedy Town

CSS selector: `find_all('div', class_='property_item')`. Lambda fallback if 0 results:
```python
soup.find_all('div', class_=lambda c: bool(c) and 'property_item' in str(c))
```
Pagination: `/page-{N}` suffix. Retries up to 3 times with 1.5s delays.

Script: `~/.hermes/scripts/squarefoot_scraper.py`

### Source 2: Midland.com.hk (Playwright + API) 🟠
Midland's React app uses a JSON API at `data.midland.com.hk/search/v2/properties`. Playwright gets the Bearer auth token, then API is called directly.

District codes:
- 130ND10012 = Wanchai
- 130ND10013 = Causeway Bay
- 130ND10014 = Tin Hau
- 130ND10004 = Central / Sheung Wan
- 130ND10002 = Sai Ying Pun
- 130ND10001 = Kennedy Town
- 130ND10005 = Admiralty

Script: `~/.hermes/scripts/midland_scraper.js`

### Source 3: Centanet.com / 中原地產 (Node.js + __NUXT__) 🟢
Nuxt.js SSR app — data embedded in `window.__NUXT__` state. Node.js evaluates the JS function to extract structured JSON.

Districts: Wan Chai, Causeway Bay, Happy Valley, Tin Hau, Central/Sheung Wan, Sai Ying Pun, Kennedy Town

URL pattern: `https://hk.centanet.com/findproperty/list/rent/{neighborhood}?adsource=DMK-G0011&offset={N}`
- 24 listings per page, offset-based pagination
- Territory filter: `scope.terr == "港島"` (HK Island)
- Building age directly in `buildingAge` field (no detail page needed)
- Net area in `areaInfo.nSize`, rent in `priceInfo.rent`

Script: `~/.hermes/scripts/centanet_scraper.js`

### Source 4: House730.com (Camoufox + API interception) 🔴
Hard Cloudflare 403 for all datacenter IPs. Camoufox bypasses CF, then intercepts the API response from `api.house730.com/Property/QueryProperty`. Requires GTK3 libs at `~/.local/lib/gtk3/`.

Filters via API interception: `regionCode=HK01` (HK Island), `minSaleableArea=500`, `maxSaleableArea=850`, `minRentPrice=25000`, `maxRentPrice=55000`. Client-side: excludes low floors, buildings >25yr, mid-levels keywords.

Script: `~/.hermes/scripts/house730_scraper.py`

## Filters

- Size: 500-850 sqft
- Budget: HKD$25k-55k/mo
- Building age: <25yr
- Listing freshness: <7 days
- Floor: exclude lower/ground (Low Floor, Ground Floor, Lower Floor)
- Location: exclude Mid-Levels (`mid-levels`, `mid levels`, `midlevels`, `the mid-levels`, `mid_levels`)

## Scoring

| Factor | Points |
|---|---|
| Area ≥700 sqft | +30 |
| Area ≥500 sqft | +15 |
| Price/sqft <45 | +20 |
| Price/sqft <55 | +10 |
| Building age ≤10yr | +25 |
| Building age ≤15yr | +15 |
| Building age ≤20yr | +10 |
| High/upper/top floor | +25 |
| Middle floor | +15 |
| South/SW/SE facing | +15 |
| North/NW/NE facing | +10 |
| 2 bedrooms | +15 |
| 3 bedrooms | +10 |
| 1 bedroom | +5 |
| Posted <1hr ago | +10 |
| Posted <1min ago | +15 |

## Report format

```
1. [65pts] 🔵 Sai Ying Pun Island Crest
📍 Sai Ying Pun (HKU area)
🏠 8 First Street, Sai Ying Pun
💰 HKD$38,000 | 📐 555 sqft | High Floor
🛏 2BR | 🏗17yr
📝 high-rise sea view luxury apartment in Sheung Wan SOHO
🔗 [Link](https://...)
```

## Deduplication pipeline

1. **Intra-source** — each scraper deduplicates its own results
2. **Cross-source** — building+price+area+address hash. Keeps listing with more complete data, breaks ties by source priority (Squarefoot > Midland > Centanet > House730)
3. **Cross-run** — `hk_seen_ids.json` ensures only new listings appear in daily reports

## Building age enrichment

Building age is NOT on listing cards — only on detail pages. Approach:
1. Cache in `hk_building_ages.json` (building_name → age)
2. Check cache first; fetch detail page only for unknown buildings
3. Parse with: `re.search(r'Building age:\s*(\d+)\s*Year', page_text)`
4. House730 and Centanet have age in listing data (no enrichment needed)

## Files

- Main orchestrator: `~/.hermes/scripts/hk_apartment_scraper.py`
- Squarefoot scraper: `~/.hermes/scripts/squarefoot_scraper.py`
- House730 scraper: `~/.hermes/scripts/house730_scraper.py`
- Centanet scraper: `~/.hermes/scripts/centanet_scraper.js`
- Midland scraper: `~/.hermes/scripts/midland_scraper.js`
- Results JSON: `~/.hermes/scripts/{squarefoot,midland,house730,centanet}_results.json`
- Seen IDs: `~/.hermes/scripts/hk_seen_ids.json`
- State: `~/.hermes/scripts/hk_scraper_state.json`
- Building ages cache: `~/.hermes/scripts/hk_building_ages.json`
- Report output: `~/.hermes/scripts/hk_report.txt`

## Cron job

Job ID: `62c44988b826`, runs daily at 05:00 CEST (03:00 UTC / 11:00 GMT+8).

## Running manually

```bash
python3 ~/.hermes/scripts/hk_apartment_scraper.py
```

## GTK3 setup for Camoufox

House730 and Squarefoot (Camoufox mode) require GTK3 libs. Install via:
```bash
# Extract from Ubuntu debs to ~/.local/lib/gtk3/
# Required: libgtk-3-0t64, libepoxy0, libwayland-cursor0, etc.
export LD_LIBRARY_PATH=~/.local/lib/gtk3/usr/lib/x86_64-linux-gnu
```

## Cloudflare bypass — tested Apr 2026

Tested agent-browser, @browserless.io, @steel-dev/cli, bb-browser against house730.com and spacious.hk. None can bypass CF from datacenter IPs:
- **house730.com**: Hard 403 (IP reputation). Bypassed with Camoufox.
- **spacious.hk**: JS challenge doesn't resolve for headless. Camoufox works but site has low value.
- **Root cause**: IP reputation blocking, not browser fingerprinting. Would need residential proxy.

## Other HK rental sites — tested

| Site | Status | Notes |
|---|---|---|
| squarefoot.com.hk | ✅ | Primary source. Camoufox + cloudscraper fallback. |
| midland.com.hk | ✅ | Playwright + API. ~178 HK Island listings. |
| centanet.com | ✅ | Nuxt SSR. ~62 unique HK Island listings. |
| house730.com | ✅ | Camoufox bypasses CF. ~162 listings. |
| 28hse.com | ✅ | Same parent as Squarefoot. ~80-90% overlap. |
| spacious.hk | ⚠️ | Camoufox works but /rent 404, React SPA. Low value. |
| centaline.com.hk | ❌ | Connection timeout from server. |

## Cron timezone note

System timezone is CEST (UTC+2). To run at 11am GMT+8 (03:00 UTC), use cron `0 5 * * *`.
