#!/usr/bin/env node
/**
 * Centanet (中原地產) HK Rental Scraper
 * Scrapes hk.centanet.com for rental listings on HK Island.
 * Uses SSR __NUXT__ data from the Nuxt.js frontend.
 * 
 * Output: centanet_results.json (listings array)
 */

const https = require('https');
const fs = require('fs');
const path = require('path');

// District search URLs — Chinese neighborhood names as path segments
// Each returns ~20-500 listings covering specific HK Island areas
const SEARCH_URLS = {
    'Wan Chai / Admiralty': '灣仔',
    'Causeway Bay / Happy Valley': '銅鑼灣',
    'Happy Valley': '跑馬地',
    'Tin Hau / Tai Hang': '天后',
    'Central / Sheung Wan': '半山',
    'Sai Ying Pun (HKU area)': '西營盤',
    'Kennedy Town (HKU area)': '堅尼地城',
};

// HK Island district names for filtering
const HK_ISLAND_DISTRICTS = new Set(['中西區', '灣仔區', '東區', '南區']);

// Filters (match main scraper)
const MIN_AREA = 400;
const PREFER_MIN_AREA = 500;
const MAX_AREA = 850;
const MIN_PRICE = 25000;
const MAX_PRICE = 55000;
const MAX_BUILDING_AGE = 25;
const MAX_PAGES = 20; // max pages per district search (24 items/page)

const BASE_URL = 'https://hk.centanet.com';
const RESULTS_PATH = path.join(process.env.HOME, '.hermes/scripts/centanet_results.json');

function fetchPage(url) {
    return new Promise((resolve, reject) => {
        https.get(url, {
            headers: {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml',
                'Accept-Language': 'zh-HK,zh;q=0.9,en;q=0.8',
            },
            timeout: 30000,
        }, (res) => {
            let data = '';
            res.on('data', chunk => data += chunk);
            res.on('end', () => {
                if (res.statusCode !== 200) {
                    return reject(new Error(`HTTP ${res.statusCode}`));
                }
                const match = data.match(/window\.__NUXT__=(.+?)<\/script>/s);
                if (!match) return reject(new Error('No __NUXT__ data'));
                try {
                    const nuxtData = eval(match[1]);
                    const rentList = nuxtData?.state?.rent?.rentList;
                    resolve({
                        count: rentList?.count || 0,
                        data: rentList?.data || [],
                    });
                } catch (e) {
                    reject(new Error(`Parse error: ${e.message}`));
                }
            });
        }).on('error', reject);
    });
}

function normalizeListing(item) {
    const area = item.areaInfo?.nSize;
    const rent = item.priceInfo?.rent;
    const unitRent = item.unitPriceInfo?.nUnitRent;
    
    // Build building name from estateName + buildingName
    let building = item.estateName || '';
    if (item.buildingName) {
        building = building ? `${building} ${item.buildingName}` : item.buildingName;
    }
    
    // District info
    const district = item.scope?.db || '';
    const hma = item.scope?.hma || '';
    const terr = item.scope?.terr || '';
    
    // Address
    const addr = item.displayText?.addr || {};
    const address = addr.line1 || item.address || '';
    
    // Floor direction from display text
    const direction = item.direction || '';
    
    return {
        source: 'centanet',
        district: `${district} / ${hma}`,
        building: building,
        address: address,
        floor: null, // Centanet doesn't consistently show floor in list data
        price: rent,
        area_sqft: area,
        price_per_sqft: unitRent || (rent && area ? Math.round(rent / area) : null),
        bedrooms: item.bedroomCount || null,
        bathrooms: null,
        direction: direction,
        description: null,
        posted: null,
        url: item.cestcode ? `${BASE_URL}/findproperty/detail/${encodeURIComponent(building)}_${item.cestcode}?theme=rent` : null,
        building_age: item.buildingAge || null,
        territory: terr,
        hma: hma,
        estate_code: item.cestcode || null,
    };
}

async function scrapeDistrict(districtName, searchPath) {
    const allListings = [];
    let offset = 0;
    let totalCount = null;
    
    for (let page = 0; page < MAX_PAGES; page++) {
        const encoded = encodeURIComponent(searchPath);
        const url = `${BASE_URL}/findproperty/list/rent/${encoded}?adsource=DMK-G0011&offset=${offset}`;
        
        try {
            const result = await fetchPage(url);
            if (totalCount === null) totalCount = result.count;
            if (!result.data.length) break;
            
            for (const item of result.data) {
                // Only include HK Island listings
                if (item.scope?.terr !== '港島') continue;
                
                const listing = normalizeListing(item);
                if (listing.price && listing.area_sqft) {
                    allListings.push(listing);
                }
            }
            
            offset += 24;
            if (offset >= totalCount) break;
            
            // Polite delay
            await new Promise(r => setTimeout(r, 500));
        } catch (e) {
            console.error(`  Error page ${page + 1}: ${e.message}`);
            break;
        }
    }
    
    console.log(`  ${districtName}: ${allListings.length} listings (total: ${totalCount})`);
    return allListings;
}

async function main() {
    console.log('=== Centanet.com (中原地產) ===');
    
    const allListings = [];
    const seenIds = new Set();
    
    for (const [districtName, searchPath] of Object.entries(SEARCH_URLS)) {
        console.log(`Scraping: ${districtName} (${searchPath})`);
        const listings = await scrapeDistrict(districtName, searchPath);
        
        // Deduplicate by estate_code or building+price+area
        for (const l of listings) {
            const id = l.estate_code || `${l.building}-${l.price}-${l.area_sqft}`;
            if (!seenIds.has(id)) {
                seenIds.add(id);
                allListings.push(l);
            }
        }
        
        await new Promise(r => setTimeout(r, 1000));
    }
    
    console.log(`\nTotal Centanet: ${allListings.length} unique listings`);
    
    // Write results
    fs.writeFileSync(RESULTS_PATH, JSON.stringify(allListings, null, 2));
    console.log(`Results saved to ${RESULTS_PATH}`);
}

main().catch(e => {
    console.error('Fatal error:', e);
    process.exit(1);
});
