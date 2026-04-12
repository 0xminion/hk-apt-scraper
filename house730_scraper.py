#!/usr/bin/env python3
"""
House730.com HK Rental Scraper
Uses Camoufox (stealth Firefox) to bypass Cloudflare and intercept API responses.

Output: house730_results.json (listings array)
"""

import json
import os
import re
import sys
import time

# Set Camoufox library path
gtk_lib = os.path.expanduser('~/.local/lib/gtk3/usr/lib/x86_64-linux-gnu')
os.environ['LD_LIBRARY_PATH'] = gtk_lib

from camoufox.sync_api import Camoufox

# HK Island zone codes (region HK01)
HK_ISLAND_REGION = 'HK01'

# Filters (match main scraper)
MIN_AREA = 500
MAX_AREA = 850
MIN_PRICE = 25000
MAX_PRICE = 55000
MAX_BUILDING_AGE = 25
MAX_PAGES = 5  # 50 items per page = up to 250 listings

RESULTS_PATH = os.path.expanduser('~/.hermes/scripts/house730_results.json')

# Mid-Levels exclusion keywords (English only — Chinese 半山 is too broad for HK Island districts)
EXCLUDED_KEYWORDS = ['mid-levels', 'mid levels', 'midlevels', 'the mid-levels', 'mid_levels']


def normalize_listing(item):
    """Convert house730 API item to standard listing format."""
    area = item.get('saleableArea')
    price = item.get('rentPrice')
    
    # Floor mapping
    floor_map = {1: 'Low', 2: 'Middle', 3: 'High'}
    floor_num = item.get('unitFloor')
    floor = floor_map.get(floor_num, None)
    floor_text = item.get('unitFloorWithCulture', '')
    
    # Exclude lower floors
    if floor == 'Low' or (floor_text and '低層' in floor_text):
        return None
    
    # Building age — filter out old buildings
    age = item.get('buildingAge')
    if age and isinstance(age, (int, float)) and age > MAX_BUILDING_AGE:
        return None
    
    # District/building info
    district = item.get('gscopeNameWithCulture', '') or item.get('gscopeName', '')
    zone = item.get('zoneNameWithCulture', '') or item.get('zoneName', '')
    building = item.get('estateNameWithCulture', '') or item.get('estateName', '')
    building_en = item.get('estateNameEN', '')
    address = item.get('estateAddressWithCulture', '') or ''
    
    # Building age (already filtered above, just normalize type)
    if age and isinstance(age, (int, float)):
        age = int(age)
    else:
        age = None
    
    # Bedrooms
    beds = item.get('roomNumber')
    
    # Price per sqft
    ppsf = item.get('saleableAvgPrice')
    
    # Direction/view from tags
    direction = None
    view = None
    tags = item.get('propertyTag', []) or []
    tag_names = [t.get('propertyTagName', '') for t in tags]
    for tag in tag_names:
        if any(d in tag for d in ['北', '南', '東', '西', '海景', '山景']):
            view = tag
    
    # URL
    url = item.get('url', '')
    if url and not url.startswith('http'):
        url = f"https://www.house730.com{url}"
    
    # Description from tags
    desc_parts = [t for t in tag_names if t not in ['VR睇樓', '平面圖']]
    description = ', '.join(desc_parts[:4]) if desc_parts else None
    
    # Check mid-levels exclusion
    searchable = f"{building} {building_en} {address} {district} {zone} {url}".lower()
    if any(kw in searchable for kw in EXCLUDED_KEYWORDS):
        return None  # Mark for exclusion
    
    return {
        'source': 'house730',
        'district': f"{district} / {zone}",
        'building': building,
        'address': address,
        'floor': floor,
        'floor_text': floor_text,
        'price': int(price) if price else None,
        'area_sqft': int(area) if area else None,
        'price_per_sqft': float(ppsf) if ppsf else None,
        'bedrooms': beds,
        'bathrooms': item.get('toiletNumber'),
        'direction': direction,
        'view': view,
        'description': description,
        'posted': None,  # house730 doesn't show relative time
        'url': url,
        'building_age': age,
        'property_id': item.get('propertyID'),
        'latitude': item.get('latitudes'),
        'longitude': item.get('longitudes'),
    }


def scrape_house730():
    """Use Camoufox to load house730.com and intercept API responses."""
    all_listings = []
    seen_ids = set()
    
    print("=== House730.com (Camoufox + CF bypass) ===")
    
    with Camoufox(headless=True) as browser:
        page = browser.new_page()
        
        # Set up route handler BEFORE navigating
        def handle_route(route):
            body = json.loads(route.request.post_data)
            body['minSaleableArea'] = MIN_AREA
            body['maxSaleableArea'] = MAX_AREA
            body['minRentPrice'] = MIN_PRICE
            body['maxRentPrice'] = MAX_PRICE
            body['pageCount'] = 50
            # Try to filter for HK Island via region code
            body['regionCode'] = 'HK01'
            route.continue_(post_data=json.dumps(body))
        
        page.route('**/Property/QueryProperty', handle_route)
        
        page_num = 0
        total_count = None
        
        while page_num < MAX_PAGES:
            page_num += 1
            api_responses = []
            
            def capture_response(response):
                if 'QueryProperty' in response.url:
                    try:
                        api_responses.append(response.json())
                    except:
                        pass
            
            page.on('response', capture_response)
            
            if page_num == 1:
                page.goto('https://www.house730.com/rent/t1/', timeout=30000)
            else:
                # Click page number via Playwright locator (Vue renders .page-step <p> elements)
                # nth(page_num - 1) because .page-step[0] = page 1, [1] = page 2, etc.
                page_btn = page.locator('.page-step').nth(page_num - 1)
                if page_btn.count() > 0:
                    page_btn.click()
                else:
                    print(f"  Page {page_num}: no .page-step button found, stopping")
                    break
            
            page.wait_for_timeout(8000)
            
            if not api_responses:
                print(f"  Page {page_num}: No API response")
                break
            
            data = api_responses[0]
            result = data.get('result', {})
            items = result.get('data', [])
            
            if total_count is None:
                total_count = result.get('count', 0)
                print(f"  Total matching: {total_count}")
            
            if not items:
                print(f"  Page {page_num}: No items")
                break
            
            # Filter for HK Island and normalize
            page_listings = []
            for item in items:
                region = item.get('regionCode', '')
                if region != HK_ISLAND_REGION:
                    continue
                
                listing = normalize_listing(item)
                if listing is None:
                    continue  # Mid-Levels excluded
                
                pid = listing.get('property_id')
                if pid and pid not in seen_ids:
                    seen_ids.add(pid)
                    page_listings.append(listing)
                elif not pid:
                    key = f"{listing['building']}-{listing['price']}-{listing['area_sqft']}"
                    if key not in seen_ids:
                        seen_ids.add(key)
                        page_listings.append(listing)
            
            all_listings.extend(page_listings)
            hk_total = sum(1 for i in items if i.get('regionCode') == HK_ISLAND_REGION)
            print(f"  Page {page_num}: {len(items)} items ({hk_total} HK Island) → kept {len(page_listings)} (running total: {len(all_listings)})")
            
            # Remove listener for next iteration
            page.remove_listener('response', capture_response)
            
            if len(items) < 50:
                break  # Last page
            
            time.sleep(1)
        
        page.unroute('**/Property/QueryProperty', handle_route)
    
    print(f"\nTotal House730: {len(all_listings)} HK Island listings")
    
    # Save results
    with open(RESULTS_PATH, 'w') as f:
        json.dump(all_listings, f, indent=2, ensure_ascii=False)
    print(f"Results saved to {RESULTS_PATH}")
    
    # Print summary
    districts = {}
    for l in all_listings:
        d = l.get('district', '?')
        districts[d] = districts.get(d, 0) + 1
    
    print("\nDistricts:")
    for d, c in sorted(districts.items(), key=lambda x: -x[1]):
        print(f"  {d}: {c}")
    
    # Print top 5
    print("\nTop listings:")
    for l in all_listings[:5]:
        age_str = f"{l['building_age']}yr" if l.get('building_age') else '?yr'
        print(f"  {l.get('building', '?')} | {l.get('area_sqft', '?')}sqft | ${l.get('price', 0):,}/mo | {l.get('bedrooms', '?')}BR | {l.get('floor_text', '?')} | {age_str}")
    
    return all_listings


if __name__ == '__main__':
    scrape_house730()
