#!/usr/bin/env python3
"""
HK Apartment Rental Scraper
Scrapes squarefoot.com.hk for apartments matching criteria:
- Districts: Wan Chai/Admiralty, Causeway Bay, Tin Hau, Central/Sheung Wan, Sai Ying Pun, Kennedy Town
- Net area: 500-850 sqft
- Budget: HKD$25k-55k/month
- Building age: < 25 years
- Scores by floor height, direction, value-for-money, bedrooms, recency
"""

import cloudscraper
from bs4 import BeautifulSoup
import re
import json
import os
import hashlib
import time
from datetime import datetime, timezone

# --- Configuration ---
TARGET_DISTRICTS = {
    'Wan Chai / Admiralty': '/en/rent/a1/dg4',
    'Causeway Bay / Happy Valley': '/en/rent/a1/dg5',
    'Tin Hau / Tai Hang': '/en/rent/a1/dg6',
    'Central / Sheung Wan': '/en/rent/a1/dg2',
    'Sai Ying Pun (HKU area)': '/en/rent/a1/dg1',
    'Kennedy Town (HKU area)': '/en/rent/a1/dg121',
}

# Midland district URL mappings (different format)
MIDLAND_DISTRICTS = {
    'Wan Chai / Admiralty': 'Wan-Chai-D-130ND10002',
    'Causeway Bay / Happy Valley': 'Causeway-Bay-Happy-Valley-D-130ND10005',
    'Tin Hau / Tai Hang': 'Tin-Hau-Tai-Hang-D-130ND10014',
    'Central / Sheung Wan': 'Central-Sheung-Wan-D-130ND10028',
    'Sai Ying Pun (HKU area)': 'Sai-Ying-Pun-D-130ND10030',
    'Kennedy Town (HKU area)': 'Kennedy-Town-D-130ND10033',
}

# 28hse uses same URL structure as squarefoot (same parent company)
# but we scrape it separately for any listing differences

MIN_AREA = 500
MAX_AREA = 850
MIN_PRICE = 25000
MAX_PRICE = 55000
MAX_BUILDING_AGE = 25  # years
MAX_LISTING_AGE_DAYS = 7  # only show listings posted/updated within 7 days
MAX_PAGES_PER_DISTRICT = 5
EXCLUDED_KEYWORDS = ['mid-levels', 'mid levels', 'midlevels', 'the mid-levels', 'mid_levels']

SEEN_FILE = os.path.expanduser('~/.hermes/scripts/hk_seen_ids.json')
STATE_FILE = os.path.expanduser('~/.hermes/scripts/hk_scraper_state.json')
REPORT_FILE = os.path.expanduser('~/.hermes/scripts/hk_report.txt')
BUILDING_AGE_CACHE = os.path.expanduser('~/.hermes/scripts/hk_building_ages.json')


def load_json(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def listing_id(listing):
    key = f"{listing.get('building', '')}-{listing.get('price', '')}-{listing.get('area_sqft', '')}-{listing.get('address', '')}"
    return hashlib.md5(key.encode()).hexdigest()[:12]


def parse_listing_item(item, district_name):
    """Parse a property_item div using structured HTML selectors."""
    card = item.find('div', class_='sqfoot_property_card')
    if not card:
        return None

    # District + Building name
    header_cat = card.find('div', class_='header cat')
    building = None
    if header_cat:
        full_text = header_cat.get_text(separator=' ', strip=True)
        parts = full_text.split('  ')
        building = parts[-1].strip() if parts else full_text.strip()

    # Address
    meta_div = card.find('div', class_='meta')
    address = meta_div.get_text(strip=True) if meta_div else None

    # Price
    price_el = card.find('span', class_=re.compile(r'priceDesc'))
    price = None
    ppsf = None
    if price_el:
        price_match = re.search(r'HKD\$([\d,]+)', price_el.get_text())
        if price_match:
            price = int(price_match.group(1).replace(',', ''))
        unit_el = price_el.find_next_sibling('span', class_='unitPrice')
        if unit_el:
            ppsf_match = re.search(r'@([\d,.]+)', unit_el.get_text())
            if ppsf_match:
                ppsf = float(ppsf_match.group(1))

    # Area, bedrooms, bathrooms
    area = None
    bedrooms = None
    bathrooms = None
    for header_div in card.find_all('div', class_='header'):
        text = header_div.get_text(strip=True)
        area_match = re.search(r'([\d,]+)\s*ft²', text)
        if area_match:
            area = int(area_match.group(1).replace(',', ''))
            bed_match = re.search(r'ft²\s*(\d+)\s*(\d+)', text)
            if bed_match:
                bedrooms = int(bed_match.group(1))
                bathrooms = int(bed_match.group(2))
            break

    # Floor, direction, posted time
    card_text = card.get_text(separator=' ', strip=True)
    floor_match = re.search(r'((?:High|Low|Middle|Upper|Ground|Top)\s*Floor)', card_text, re.I)
    floor = floor_match.group(1) if floor_match else None

    direction = None
    dir_match = re.search(r'\b(North|South|East|West|Northeast|Northwest|Southeast|Southwest)\b', card_text)
    if dir_match:
        direction = dir_match.group(1)

    time_match = re.search(r'(\d+\s*(?:hours?|minutes?|days?)\s*ago)', card_text, re.I)
    posted = time_match.group(1) if time_match else None

    # Description
    desc_el = card.find('div', class_='description')
    desc = desc_el.get_text(strip=True) if desc_el else None

    # Detail URL
    detail_url = None
    img_link = item.find('img', class_='detail_page')
    if img_link:
        detail_url = img_link.get('href')
    if not detail_url:
        link = item.find('a', href=re.compile(r'/en/(rent|service-apartment)/'))
        if link:
            detail_url = link.get('href')
    if detail_url and not detail_url.startswith('http'):
        detail_url = f"https://www.squarefoot.com.hk{detail_url}"

    return {
        'source': 'squarefoot',
        'district': district_name,
        'building': building,
        'address': address,
        'floor': floor,
        'price': price,
        'area_sqft': area,
        'price_per_sqft': ppsf,
        'bedrooms': bedrooms,
        'bathrooms': bathrooms,
        'direction': direction,
        'description': (desc[:150] if desc else None),
        'posted': posted,
        'url': detail_url,
        'building_age': None,  # filled later
    }


def fetch_building_age(scraper, detail_url):
    """Fetch building age from a property detail page (Squarefoot or Midland)."""
    try:
        resp = scraper.get(detail_url, timeout=15)
        if resp.status_code != 200:
            return None
        # Squarefoot format: "Building age: 51 Year"
        match = re.search(r'Building age:\s*(\d+)\s*Year', resp.text)
        if match:
            return int(match.group(1))
        # Midland format: "building age of 11.0 years" or "X Year(s)"
        match = re.search(r'building.age.{0,20}([\d.]+)\s*year', resp.text, re.I)
        if match:
            return int(float(match.group(1)))
        match = re.search(r'([\d.]+)\s*Year\(s\)', resp.text)
        if match:
            return int(float(match.group(1)))
        return None
    except Exception:
        return None


def scrape_district(scraper, district_name, path):
    """Scrape all pages of a district with retry for rate-limited responses."""
    all_listings = []
    for page in range(1, MAX_PAGES_PER_DISTRICT + 1):
        url = f"https://www.squarefoot.com.hk{path}" if page == 1 else f"https://www.squarefoot.com.hk{path}/page-{page}"
        items = []
        for attempt in range(3):
            try:
                resp = scraper.get(url, timeout=20)
                if resp.status_code != 200:
                    break
                soup = BeautifulSoup(resp.text, 'lxml')
                items = soup.find_all('div', class_='property_item')
                if not items:
                    # Fallback: class names may have trailing spaces or extra classes
                    items = soup.find_all('div', class_=lambda c: bool(c) and 'property_item' in str(c))
                if items:
                    break  # Got data, stop retrying
                time.sleep(1.5)  # Brief wait before retry
            except Exception as e:
                print(f"  Error on page {page} attempt {attempt+1}: {e}")
                time.sleep(1)
        if not items:
            continue
        for item in items:
            listing = parse_listing_item(item, district_name)
            if listing and listing.get('price') and listing.get('area_sqft'):
                all_listings.append(listing)
        time.sleep(0.5)
    return all_listings


def enrich_building_ages(scraper, listings, age_cache):
    """Look up building ages from cache; fetch from detail pages for unknown buildings."""
    unknown_buildings = set()
    # First pass: assign from cache
    for l in listings:
        bname = l.get('building')
        if bname and bname in age_cache:
            l['building_age'] = age_cache[bname]
        elif bname and l.get('url'):
            unknown_buildings.add(bname)

    # Second pass: fetch detail pages for unknowns (one per building)
    building_urls = {}
    for l in listings:
        bname = l.get('building')
        if bname in unknown_buildings and bname not in building_urls and l.get('url'):
            building_urls[bname] = l['url']

    fetched = 0
    for bname, url in building_urls.items():
        age = fetch_building_age(scraper, url)
        if age is not None:
            age_cache[bname] = age
            fetched += 1
        time.sleep(0.3)  # Be polite

    if fetched > 0:
        save_json(BUILDING_AGE_CACHE, age_cache)
        print(f"  Fetched {fetched} new building ages")

    # Third pass: assign newly fetched ages
    for l in listings:
        bname = l.get('building')
        if bname and l.get('building_age') is None and bname in age_cache:
            l['building_age'] = age_cache[bname]

    return listings


def filter_listings(listings):
    """Filter by area, price, building age, listing freshness. Score by desirability."""
    now = datetime.now(timezone.utc)
    filtered = []
    for l in listings:
        area = l.get('area_sqft', 0)
        price = l.get('price', 0)
        age = l.get('building_age')

        if area < MIN_AREA or area > MAX_AREA:
            continue
        if price < MIN_PRICE or price > MAX_PRICE:
            continue
        if age is not None and age > MAX_BUILDING_AGE:
            continue

        # Exclude Mid-Levels locations (check all text fields + URL)
        searchable = ' '.join([
            (l.get('building') or '').lower(),
            (l.get('address') or '').lower(),
            (l.get('district') or '').lower(),
            (l.get('description') or '').lower(),
            (l.get('url') or '').lower(),
        ])
        if any(kw in searchable for kw in EXCLUDED_KEYWORDS):
            continue

        # Listing freshness filter (< 7 days)
        posted = l.get('posted') or ''
        listing_age_days = None

        # Squarefoot format: "6 hours ago", "2 days ago", "30 minutes ago"
        hour_match = re.search(r'(\d+)\s*hours?\s*ago', posted, re.I)
        day_match = re.search(r'(\d+)\s*days?\s*ago', posted, re.I)
        min_match = re.search(r'(\d+)\s*minutes?\s*ago', posted, re.I)

        if hour_match:
            listing_age_days = int(hour_match.group(1)) / 24
        elif day_match:
            listing_age_days = int(day_match.group(1))
        elif min_match:
            listing_age_days = int(min_match.group(1)) / 1440
        elif posted:
            # Midland format: ISO date string like "2026-04-06"
            try:
                post_date = datetime.fromisoformat(posted.replace('Z', '+00:00'))
                listing_age_days = (now - post_date).total_seconds() / 86400
            except (ValueError, TypeError):
                pass

        # Skip if we can determine age and it's too old
        if listing_age_days is not None and listing_age_days > MAX_LISTING_AGE_DAYS:
            continue

        score = 0

        # Area bonus (larger within range = better)
        if area >= 700:
            score += 30
        elif area >= 500:
            score += 15

        # Value for money
        if l.get('price_per_sqft'):
            ppsf = l['price_per_sqft']
            if ppsf < 45:
                score += 20
            elif ppsf < 55:
                score += 10

        # Building age bonus (newer = better)
        if age is not None:
            if age <= 10:
                score += 25
            elif age <= 15:
                score += 15
            elif age <= 20:
                score += 10

        # Higher floor
        floor = (l.get('floor') or '').lower()
        if 'high' in floor or 'upper' in floor or 'top' in floor:
            score += 25
        elif 'middle' in floor:
            score += 15

        # Direction (mountain = south, sea = north on HK Island)
        direction = (l.get('direction') or '').lower()
        if direction in ('south', 'southeast', 'southwest'):
            score += 15
        if direction in ('north', 'northeast', 'northwest'):
            score += 10

        # 2BR ideal for a couple
        beds = l.get('bedrooms')
        if beds == 2:
            score += 15
        elif beds == 1:
            score += 5
        elif beds == 3:
            score += 10

        # Recency
        posted = (l.get('posted') or '').lower()
        if 'hour' in posted:
            score += 10
        elif 'minute' in posted:
            score += 15

        l['score'] = score
        l['area_category'] = 'match'
        filtered.append(l)

    filtered.sort(key=lambda x: x.get('score', 0), reverse=True)
    return filtered


def format_report(new_listings, all_filtered, stats):
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    lines = []
    lines.append(f"🏠 HK Apartment Daily Report — {now}")
    lines.append(f"Scraped {stats['total_scraped']} listings from {stats['districts']} districts")
    lines.append(f"Budget: HKD$25k-55k/mo | Size: 500-850 sqft | Age: <25yr | Fresh: <7 days")
    lines.append(f"Filtered: {stats['filtered']} match all criteria ({stats['new']} new today)")
    lines.append("")

    if not new_listings:
        lines.append("No new listings today. Top current matches:")
        show_list = all_filtered[:8]
    else:
        lines.append(f"🆕 {len(new_listings)} NEW listings!")
        lines.append("")
        show_list = new_listings[:10]

    for i, l in enumerate(show_list, 1):
        price_str = f"HKD${l['price']:,}" if l.get('price') else '?'
        area_str = f"{l['area_sqft']} sqft" if l.get('area_sqft') else '?'
        beds = f"{l['bedrooms']}BR" if l.get('bedrooms') else '?'
        floor = l.get('floor') or ''
        direction = f" {l['direction']}" if l.get('direction') else ''
        age_str = f" | 🏗{l['building_age']}yr" if l.get('building_age') else ''
        source = l.get('source', 'squarefoot')
        src_tag = {'midland': '🟠', 'centanet': '🟢'}.get(source, '🔵')
        cat = '📌'
        score = l.get('score', 0)
        building = l.get('building') or 'Unknown'

        lines.append(f"{cat} {i}. [{score}pts] {src_tag} {building}")
        lines.append(f"   📍 {l.get('district', '?')}")
        if l.get('address'):
            lines.append(f"   🏠 {l['address']}")
        lines.append(f"   💰 {price_str} | 📐 {area_str} | 🛏 {beds} | {floor}{direction}{age_str}")
        if l.get('description'):
            lines.append(f"   📝 {l['description'][:100]}")
        if l.get('url'):
            lines.append(f"   🔗 {l['url']}")
        lines.append("")

    lines.append("— Summary —")
    lines.append(f"Total matching: {len(all_filtered)} (500-850 sqft)")
    lines.append("")
    lines.append("🔍 Browse manually:")
    for name, path in TARGET_DISTRICTS.items():
        lines.append(f"  {name}: https://www.squarefoot.com.hk{path}")

    return '\n'.join(lines)


def scrape_centanet():
    """Run the Node.js Centanet scraper and return listings."""
    import subprocess
    script_path = os.path.expanduser('~/.hermes/scripts/centanet_scraper.js')
    results_path = os.path.expanduser('~/.hermes/scripts/centanet_results.json')

    try:
        result = subprocess.run(
            ['node', script_path],
            capture_output=True, text=True, timeout=300,
            cwd=os.path.expanduser('~/.hermes/scripts')
        )
        if result.stdout:
            for line in result.stdout.strip().split('\n'):
                if 'Total' in line or 'Scraping' in line:
                    print(f"  {line}")
        if result.returncode != 0:
            print(f"  Centanet error (rc={result.returncode}): {result.stderr[:300]}")
            return []
    except subprocess.TimeoutExpired:
        print("  Centanet scraper timed out")
        return []
    except Exception as e:
        print(f"  Centanet scraper error: {e}")
        return []

    if os.path.exists(results_path):
        with open(results_path) as f:
            listings = json.load(f)
        return listings
    return []


def scrape_midland():
    """Run the Node.js Midland scraper and return listings."""
    import subprocess
    script_dir = os.path.dirname(os.path.expanduser('~/.hermes/scripts/hk_apartment_scraper.py'))
    script_path = os.path.expanduser('~/.hermes/scripts/midland_scraper.js')
    results_path = os.path.expanduser('~/.hermes/scripts/midland_results.json')

    try:
        result = subprocess.run(
            ['node', script_path],
            capture_output=True, text=True, timeout=180,
            cwd=os.path.expanduser('~/.hermes/scripts')
        )
        if result.stdout:
            for line in result.stdout.strip().split('\n'):
                if 'Total Midland' in line or 'Got' in line:
                    print(f"  {line}")
        if result.returncode != 0:
            print(f"  Midland error (rc={result.returncode}): {result.stderr[:300]}")
            return []
    except subprocess.TimeoutExpired:
        print("  Midland scraper timed out")
        return []
    except Exception as e:
        print(f"  Midland scraper error: {e}")
        return []

    if os.path.exists(results_path):
        with open(results_path) as f:
            listings = json.load(f)
        return listings
    return []


def main():
    scraper = cloudscraper.create_scraper()
    seen = load_json(SEEN_FILE)
    age_cache = load_json(BUILDING_AGE_CACHE)

    all_listings = []
    district_counts = {}

    # --- Scrape Squarefoot ---
    print("=== Squarefoot.com.hk ===")
    for district_name, path in TARGET_DISTRICTS.items():
        print(f"Scraping: {district_name}")
        listings = scrape_district(scraper, district_name, path)
        district_counts[district_name] = len(listings)
        all_listings.extend(listings)
        print(f"  Got {len(listings)} listings")
        time.sleep(1)

    # --- Scrape Midland ---
    print("\n=== Midland.com.hk ===")
    midland_listings = scrape_midland()
    print(f"  Total Midland: {len(midland_listings)} listings")
    all_listings.extend(midland_listings)

    # Count by district including Midland
    for l in midland_listings:
        d = l.get('district', 'Unknown')
        district_counts[d] = district_counts.get(d, 0) + 1

    # --- Scrape Centanet ---
    print("\n=== Centanet.com (中原地產) ===")
    centanet_listings = scrape_centanet()
    print(f"  Total Centanet: {len(centanet_listings)} listings")
    all_listings.extend(centanet_listings)

    for l in centanet_listings:
        d = l.get('district', 'Unknown')
        district_counts[d] = district_counts.get(d, 0) + 1

    print(f"\nTotal scraped: {len(all_listings)}. Enriching building ages...")
    all_listings = enrich_building_ages(scraper, all_listings, age_cache)

    # Filter
    filtered = filter_listings(all_listings)

    # Cross-source deduplication within this run
    source_priority = {'squarefoot': 0, 'midland': 1, 'centanet': 2}
    deduped = {}
    dupes_removed = 0
    for l in filtered:
        lid = listing_id(l)
        if lid in deduped:
            existing = deduped[lid]
            # Keep the listing with more complete data, break ties by source priority
            existing_fields = sum(1 for v in existing.values() if v is not None and v != '')
            new_fields = sum(1 for v in l.values() if v is not None and v != '')
            existing_pri = source_priority.get(existing.get('source', ''), 99)
            new_pri = source_priority.get(l.get('source', ''), 99)
            if new_fields > existing_fields or (new_fields == existing_fields and new_pri < existing_pri):
                deduped[lid] = l
            dupes_removed += 1
        else:
            deduped[lid] = l
    filtered = sorted(deduped.values(), key=lambda x: x.get('score', 0), reverse=True)
    print(f"Dedup: {dupes_removed} cross-source duplicates removed ({len(filtered)} unique)")

    # Deduplicate against seen
    new_listings = []
    for l in filtered:
        lid = listing_id(l)
        if lid not in seen:
            new_listings.append(l)
            seen[lid] = {
                'first_seen': datetime.now(timezone.utc).isoformat(),
                'price': l.get('price'),
                'area': l.get('area_sqft'),
                'building': l.get('building'),
            }

    # Clean old seen entries (>30 days)
    cutoff = datetime.now(timezone.utc).timestamp() - (30 * 86400)
    seen = {k: v for k, v in seen.items()
            if datetime.fromisoformat(v.get('first_seen', '2000-01-01')).timestamp() > cutoff}

    save_json(SEEN_FILE, seen)

    stats = {
        'total_scraped': len(all_listings),
        'districts': len(TARGET_DISTRICTS),
        'filtered': len(filtered),
        'new': len(new_listings),
    }

    report = format_report(new_listings, filtered, stats)
    print(report)

    with open(REPORT_FILE, 'w') as f:
        f.write(report)

    with open(STATE_FILE, 'w') as f:
        json.dump({
            'last_run': datetime.now(timezone.utc).isoformat(),
            'stats': stats,
            'district_counts': district_counts,
            'building_age_cache_size': len(age_cache),
        }, f, indent=2)

    return report


if __name__ == '__main__':
    main()
