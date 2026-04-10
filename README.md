# HK Apartment Rental Scraper

Scrapes [squarefoot.com.hk](https://www.squarefoot.com.hk) for rental listings across 6+ HK Island districts.

## Criteria

- Size: 500-850 sqft
- Budget: HKD $25,000-55,000/month
- Building age: < 25 years
- Districts: Wan Chai/Admiralty, Causeway Bay, Tin Hau, Central/Sheung Wan, Sai Ying Pun, Kennedy Town

## Usage

```bash
pip install cloudscraper beautifulsoup4 lxml
python3 hk_apartment_scraper.py
```

## How it works

1. Scrapes squarefoot.com.hk using cloudscraper (bypasses Cloudflare)
2. Parses listings with BeautifulSoup
3. Enriches with building age from detail pages (cached)
4. Scores by floor height, direction, value-for-money, building age, bedrooms, recency
5. Outputs ranked report

## Files

- `hk_apartment_scraper.py` — main scraper script
- `skill/SKILL.md` — Hermes Agent skill documentation
