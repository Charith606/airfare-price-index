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
        Scrapes live, real-time airfares from Google Flights / OTA aggregator.
        """
        formatted_date = travel_date.strftime("%Y-%m-%d")
        url = f"https://www.google.com/travel/flights?q=Flights%20to%20{destination}%20from%20{origin}%20on%20{formatted_date}%20one%20way&curr=INR"
        
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
                
                raw_items = await page.evaluate("""() => {
                    const list = [];
                    const elements = document.querySelectorAll('li.pIav2d, div.yR1fYc, div.Jmoaf');
                    for (let el of elements) {
                        const txt = el.innerText;
                        if (txt && (txt.includes('₹') || txt.includes('INR'))) {
                            list.push(txt);
                        }
                    }
                    return list;
                }""")
                
                logger.info(f"Retrieved {len(raw_items)} live flight entries from page.")
                
                airlines_known = ["IndiGo", "Air India", "Akasa Air", "SpiceJet", "Air India Express", "Vistara", "Alliance Air"]
                
                for item in raw_items:
                    lines = [l.strip() for l in item.split('\n') if l.strip()]
                    
                    price = 0
                    for line in lines:
                        if '₹' in line or 'INR' in line:
                            digits = re.sub(r'[^\d]', '', line)
                            if digits and int(digits) >= 1000:
                                price = int(digits)
                                break
                    
                    if price == 0:
                        continue
                        
                    airline = "Unknown Airline"
                    for a in airlines_known:
                        if any(a.lower() in line.lower() for line in lines):
                            airline = a
                            break
                    
                    stops = 0
                    if any("stop" in l.lower() and not "non-stop" in l.lower() for l in lines):
                        stops = 1
                        
                    dept_time = "10:00"
                    arr_time = "12:30"
                    for l in lines:
                        time_matches = re.findall(r'\b\d{1,2}:\d{2}\b', l)
                        if len(time_matches) >= 2:
                            dept_time = time_matches[0]
                            arr_time = time_matches[1]
                            break
                        elif len(time_matches) == 1 and dept_time == "10:00":
                            dept_time = time_matches[0]
                            
                    flights.append({
                        "collection_date": date.today().isoformat(),
                        "travel_date": travel_date.isoformat(),
                        "origin": origin.upper(),
                        "destination": destination.upper(),
                        "airline": airline,
                        "price": price,
                        "total_fare": price,
                        "currency": "INR",
                        "departure_time": dept_time,
                        "arrival_time": arr_time,
                        "stops": stops,
                        "duration_minutes": 135,
                        "fare_type": "quoted_fare"
                    })
                    
            except Exception as e:
                logger.error(f"Failed to scrape {origin}-{destination} on {formatted_date}: {e}")
            finally:
                await browser.close()
                
        return flights

async def test_scraper():
    scraper = OTAScraper(headless=True)
    from datetime import timedelta
    target_date = date.today() + timedelta(days=15)
    results = await scraper.scrape_route("DEL", "BOM", target_date)
    print(f"Scraped {len(results)} live flights:")
    for r in results[:3]:
        print(r)

if __name__ == "__main__":
    asyncio.run(test_scraper())
