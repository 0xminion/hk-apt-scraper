# HK Apartment Rental Scraper

Scrapes 4 sources for rental listings across HK Island districts.

## Sources

| Source | Tag | Method | Est. Listings |
|---|---|---|---|
| Squarefoot.com.hk | 🔵 | Camoufox (cloudscraper fallback) | ~236 |
| Midland.com.hk | 🟠 | Playwright + API | ~179 |
| Centanet (中原地產) | 🟢 | Node.js + Nuxt SSR | ~64 |
| House730.com | 🔴 | Camoufox + API interception | ~162 |

All 4 sources run in parallel via ThreadPoolExecutor (~226s total).

## Criteria

- Size: 500-850 sqft
- Budget: HKD $25,000-55,000/month
- Building age: < 25 years
- Freshness: < 7 days
- Floor: exclude lower/ground floors
- Excluded: Mid-Levels locations
- Districts: Wan Chai/Admiralty, Causeway Bay, Tin Hau, Central/Sheung Wan, Sai Ying Pun, Kennedy Town

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

## Usage

```bash
pip install cloudscraper beautifulsoup4 lxml camoufox
python3 hk_apartment_scraper.py
```

## How it works

1. Runs all 4 scrapers in parallel (Squarefoot via Camoufox, Midland via Node.js/Playwright, Centanet via Node.js, House730 via Camoufox)
2. Deduplicates across sources (building+price+area+address hash)
3. Enriches with building age from detail pages (cached)
4. Filters by criteria (area, price, age, floor, freshness, mid-levels)
5. Scores by floor height, direction, value-for-money, building age, bedrooms, recency
6. Outputs ranked report with markdown links

## Deduplication

1. **Intra-source** — each scraper deduplicates its own results
2. **Cross-source** — keeps listing with most complete data, breaks ties by source priority (Squarefoot > Midland > Centanet > House730)
3. **Cross-run** — `hk_seen_ids.json` ensures only new listings in daily reports

## Files

- `hk_apartment_scraper.py` — main orchestrator
- `squarefoot_scraper.py` — Camoufox-based Squarefoot scraper
- `house730_scraper.py` — Camoufox + API interception for House730
- `centanet_scraper.js` — Node.js Nuxt SSR parser
- `midland_scraper.js` — Playwright + Midland API
- `skill/SKILL.md` — Hermes Agent skill documentation

## Cron

Job `62c44988b826`, daily at 03:00 UTC (11:00 GMT+8). System timezone is CEST.
