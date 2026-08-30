import asyncio
from datetime import date, datetime
from typing import List, Dict, Any
from playwright.async_api import async_playwright
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OTAScraper:
    def __init__(self, headless: bool = True):
        self.headless = headless

    async def scrape_route(self, origin: str, destination: str, travel_date: date) -> List[Dict[str, Any]]:
        """Scrape flight prices for a given route and date."""
        formatted_date = travel_date.strftime("%d/%m/%Y")
        
        # Example URL for Cleartrip
        url = f"https://www.cleartrip.com/flights/results?adults=1&childs=0&infants=0&class=Economy&depart_date={formatted_date}&from={origin}&to={destination}"
        
        flights = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = await context.new_page()
            
            logger.info(f"Navigating to {url}")
            try:
                # Go to the search results page
                await page.goto(url, timeout=60000, wait_until="domcontentloaded")
                
                # Wait for the flight results container to load
                # Note: These selectors are subject to change based on the OTA's UI updates
                await page.wait_for_selector('div[data-testid="tupple"]', timeout=30000)
                
                # Extract flight elements
                flight_elements = await page.query_selector_all('div[data-testid="tupple"]')
                logger.info(f"Found {len(flight_elements)} flights on page.")
                
                for el in flight_elements:
                    try:
                        # Extract airline name
                        airline_el = await el.query_selector('p.fw-500.fs-2.c-neutral-900')
                        airline = await airline_el.inner_text() if airline_el else "Unknown"
                        
                        # Extract price
                        price_el = await el.query_selector('p.m-0.fs-5.fw-700.c-neutral-900')
                        if price_el:
                            price_text = await price_el.inner_text()
                            # Clean price (e.g., "₹ 5,432" -> 5432)
                            price = int("".join(filter(str.isdigit, price_text)))
                        else:
                            price = 0
                            
                        # Extract departure time
                        dept_el = await el.query_selector('p.m-0.fs-4.fw-700.c-neutral-900')
                        departure_time = await dept_el.inner_text() if dept_el else ""
                        
                        if price > 0:
                            flights.append({
                                'collection_date': date.today().isoformat(),
                                'travel_date': travel_date.isoformat(),
                                'origin': origin,
                                'destination': destination,
                                'airline': airline,
                                'price': price,
                                'currency': 'INR',
                                'departure_time': departure_time,
                                'fare_type': 'quoted_fare'
                            })
                    except Exception as e:
                        logger.warning(f"Error parsing a flight element: {e}")
                        continue
                        
            except Exception as e:
                logger.error(f"Failed to scrape {origin}-{destination} on {formatted_date}: {e}")
            finally:
                await browser.close()
                
        return flights

async def test_scraper():
    scraper = OTAScraper(headless=False)  # Set to False to watch it work
    from datetime import timedelta
    target_date = date.today() + timedelta(days=15)
    results = await scraper.scrape_route("DEL", "BOM", target_date)
    print(f"Scraped {len(results)} flights:")
    for r in results[:3]:
        print(r)

if __name__ == "__main__":
    asyncio.run(test_scraper())
