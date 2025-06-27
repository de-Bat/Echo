from bs4 import BeautifulSoup
from typing import Optional
import re

from price_tracker_app.scraping.base_scraper import BaseScraper, ScrapeResult

class BooksToScrapeScraper(BaseScraper):
    """
    A scraper for the website books.toscrape.com.
    """
    SHOP_NAME = "BooksToScrape" # Must match the key in the JSON config file

    def __init__(self):
        # The shop_home_url is for reference, BaseScraper loads config based on SHOP_NAME
        super().__init__(shop_name=self.SHOP_NAME, shop_home_url="http://books.toscrape.com")

    def parse_product_data(self, html_content: str, product_url: str) -> ScrapeResult:
        """
        Parses the HTML content from a books.toscrape.com product page.
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        result = ScrapeResult()

        # Extract Product Name (Title)
        name_selector = self.selectors.get("product_name")
        if name_selector:
            name_element = soup.select_one(name_selector)
            if name_element:
                result.product_name = name_element.get_text(strip=True)
            else:
                print(f"Warning: Product name element not found using selector '{name_selector}' on {product_url}")

        # Extract Price and Currency
        price_selector = self.selectors.get("price")
        if price_selector:
            price_element = soup.select_one(price_selector)
            if price_element:
                price_text = price_element.get_text(strip=True)
                # Price text is like "£51.77". Use the robust cleaner from BaseScraper.
                result.price = self._clean_price_string(price_text)

                # Determine currency from symbol
                if "£" in price_text:
                    result.currency = "GBP"
                elif "€" in price_text:
                    result.currency = "EUR"
                elif "$" in price_text:
                    result.currency = "USD"
                # Add more currency detections if needed
            else:
                print(f"Warning: Price element not found using selector '{price_selector}' on {product_url}")

        # Extract Availability (Stock Status)
        availability_selector = self.selectors.get("availability")
        if availability_selector:
            availability_element = soup.select_one(availability_selector)
            if availability_element:
                # Text is like "In stock (22 available)" -> extract "In stock" and optionally the count
                availability_text = availability_element.get_text(strip=True)

                # Simple extraction of the main status part (e.g., "In stock")
                match = re.search(r"^(.*?)(?:\s*\(|$)", availability_text)
                if match:
                    result.stock_status = match.group(1).strip()
                else:
                    result.stock_status = availability_text # Fallback to full text

                # Optional: extract count if needed later
                # count_match = re.search(r'\((\d+)\s+available\)', availability_text)
                # if count_match:
                #     result.stock_count = int(count_match.group(1))
            else:
                print(f"Warning: Availability element not found using selector '{availability_selector}' on {product_url}")

        # Extract Product Description (Optional)
        # description_selector = self.selectors.get("product_description")
        # if description_selector:
        #     description_element = soup.select_one(description_selector)
        #     if description_element:
        #         result.product_description = description_element.get_text(strip=True)
        #     # else: print(f"Warning: Description element not found...")

        return result

if __name__ == '__main__':
    print(f"--- Testing {BooksToScrapeScraper.SHOP_NAME} Scraper ---")

    # Test with a specific product URL from books.toscrape.com
    # Example: "A Light in the Attic"
    test_product_url = "http://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"

    scraper = BooksToScrapeScraper()

    # This will make a live HTTP request
    print(f"Attempting to scrape: {test_product_url}")
    # Ensure your machine has internet access for this test to run.

    # Option 1: Call scrape_product (fetches and parses)
    scraped_data_live = scraper.scrape_product(test_product_url)

    # Option 2: Fetch content first, then parse (for more control or if content is already available)
    # html_content = scraper.fetch_page_content(test_product_url)
    # if html_content:
    #     scraped_data_live = scraper.parse_product_data(html_content, test_product_url)
    # else:
    #     scraped_data_live = None

    if scraped_data_live:
        print("\nScraped Data (Live Test):")
        print(f"  Name: {scraped_data_live.product_name}")
        print(f"  Price: {scraped_data_live.price}")
        print(f"  Currency: {scraped_data_live.currency}")
        print(f"  Stock Status: {scraped_data_live.stock_status}")
        # print(f"  Description: {scraped_data_live.product_description}")
    else:
        print(f"Failed to scrape data from {test_product_url}. Check network connection or if site structure changed.")

    print(f"\n--- {BooksToScrapeScraper.SHOP_NAME} Scraper Test Finished ---")
