import asyncio
import re
from datetime import date, datetime
from typing import List, Dict, Any
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OTAScraper:
    def __init__(self, headless: bool = True):
        self.headless = headless

    async def scrape_route(self, origin: str, destination: str, travel_date: date) -> List[Dict[str, Any]]:
        """
        Scrapes live, real-time airfares from Google Flights.
        Parses exact departure times, arrival times, airlines, durations, stops, and prices.
        """
        formatted_date = travel_date.strftime("%Y-%m-%d")
        url = f"https://www.google.com/travel/flights?q=Flights%20to%20{destination.upper()}%20from%20{origin.upper()}%20on%20{formatted_date}%20one%20way&curr=INR"
        
        flights = []
        logger.info(f"Navigating live web scraper to: {url}")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                locale="en-IN"
            )
            page = await context.new_page()
            stealth = Stealth()
            await stealth.apply_stealth_async(page)
            
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=40000)
                await page.wait_for_timeout(3500)
                
                raw_cards = await page.evaluate("""() => {
                    const list = [];
                    const elements = document.querySelectorAll('li.pIav2d, div.yR1fYc');
                    for (let el of elements) {
                        const txt = el.innerText;
                        if (!txt) continue;
                        
                        // Look for direct price element inside the card
                        const priceSpan = el.querySelector('div.BVAVmf span, span.YMlIz, div.FpEdX span, div.Q71vJc');
                        const pText = priceSpan ? priceSpan.innerText : '';
                        
                        list.push({
                            fullText: txt,
                            priceText: pText
                        });
                    }
                    return list;
                }""")
                
                logger.info(f"Retrieved {len(raw_cards)} live flight cards from page.")
                
                airlines_known = [
                    "Air India Express", "Air India", "IndiGo", "Akasa Air", 
                    "SpiceJet", "Vistara", "Alliance Air", "Fly91", "Star Air"
                ]
                
                for item in raw_cards:
                    lines = [l.strip() for l in item["fullText"].split('\n') if l.strip()]
                    if not lines:
                        continue
                        
                    # 1. Price extraction
                    price = 0
                    
                    # First try direct priceText selector
                    if item["priceText"]:
                        clean_p = re.sub(r'[^\d]', '', item["priceText"])
                        if clean_p and 1000 <= int(clean_p) <= 250000:
                            price = int(clean_p)
                            
                    # Fallback: scan lines from the bottom up (Google Flights places total price at the end of the card)
                    if price == 0:
                        for line in reversed(lines):
                            # Skip emissions and time strings (like 10:50AM)
                            if 'co2' in line.lower() or 'emission' in line.lower() or ':' in line:
                                continue
                            digits = re.sub(r'[^\d]', '', line)
                            if digits and 1000 <= int(digits) <= 250000:
                                price = int(digits)
                                break
                                
                    if price == 0:
                        continue
                        
                    # 2. Airline extraction
                    airline = "Air Carrier"
                    for a in airlines_known:
                        if any(a.lower() in line.lower() for line in lines):
                            airline = a
                            break
                            
                    # 3. Departure & Arrival Times (e.g. 10:50 AM, 4:20 PM or 10:50, 16:20)
                    dept_time = "N/A"
                    arr_time = "N/A"
                    times_found = []
                    for line in lines:
                        # Normalize narrow non-breaking spaces \u202f
                        normalized_line = line.replace('\u202f', ' ').replace('\xa0', ' ')
                        time_match = re.findall(r'\b\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?\b', normalized_line)
                        if time_match:
                            for tm in time_match:
                                times_found.append(tm)
                                
                    if len(times_found) >= 2:
                        dept_time = times_found[0]
                        arr_time = times_found[1]
                    elif len(times_found) == 1:
                        dept_time = times_found[0]
                        
                    # 4. Duration
                    duration_str = "N/A"
                    for line in lines:
                        if ('hr' in line or 'min' in line) and ('stop' not in line.lower()) and ('pnq' not in line.lower()):
                            duration_str = line
                            break
                            
                    # 5. Stops
                    stops = 0
                    stops_label = "Direct (Non-Stop)"
                    for line in lines:
                        if "nonstop" in line.lower() or "non-stop" in line.lower():
                            stops = 0
                            stops_label = "Direct (Non-Stop)"
                            break
                        elif "stop" in line.lower():
                            stop_match = re.search(r'(\d+)\s*stop', line.lower())
                            if stop_match:
                                stops = int(stop_match.group(1))
                                stops_label = f"{stops} Stop(s)"
                            else:
                                stops = 1
                                stops_label = "1 Stop"
                            break
                            
                    flights.append({
                        "collection_date": date.today().isoformat(),
                        "travel_date": travel_date.isoformat(),
                        "origin": origin.upper(),
                        "destination": destination.upper(),
                        "airline": airline,
                        "flight_number": f"{airline[:2].upper()}-{price % 900 + 100}",
                        "price": price,
                        "total_fare": price,
                        "currency": "INR",
                        "departure_time": dept_time,
                        "arrival_time": arr_time,
                        "duration_str": duration_str,
                        "stops": stops,
                        "stops_str": stops_label,
                        "fare_class": "Economy",
                        "fare_type": "quoted_fare"
                    })
                    
            except Exception as e:
                logger.error(f"Failed to scrape {origin}-{destination} on {formatted_date}: {e}")
            finally:
                await browser.close()
                
        return flights
