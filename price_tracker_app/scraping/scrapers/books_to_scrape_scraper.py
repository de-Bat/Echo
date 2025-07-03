from bs4 import BeautifulSoup
from typing import Optional
import re
import logging # Added for logging

from price_tracker_app.scraping.base_scraper import BaseScraper, ScrapeResult

logger = logging.getLogger(__name__)

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
                logger.warning(f"Product name element not found using selector '{name_selector}' on {product_url} for shop {self.SHOP_NAME}")
        else:
            logger.warning(f"Product name selector not configured for shop {self.SHOP_NAME}")

        # Extract Price and Currency
        price_selector = self.selectors.get("price")
        if price_selector:
            price_element = soup.select_one(price_selector)
            if price_element:
                price_text = price_element.get_text(strip=True)
                result.primary_value = self._clean_price_string(price_text) # Renamed

                if "£" in price_text:
                    result.value_currency = "GBP" # Renamed
                elif "€" in price_text:
                    result.value_currency = "EUR" # Renamed
                elif "$" in price_text:
                    result.value_currency = "USD" # Renamed
                else:
                    result.value_currency = None # Default if no symbol matches
                    logger.info(f"Unknown currency in '{price_text}' for shop {self.SHOP_NAME} on {product_url}. Setting currency to None.")
            else:
                logger.warning(f"Primary value (price) element not found using selector '{price_selector}' on {product_url} for shop {self.SHOP_NAME}")
        else:
            logger.warning(f"Primary value (price) selector not configured for shop {self.SHOP_NAME}")

        # Extract Availability (Stock Status)
        availability_selector = self.selectors.get("availability")
        if availability_selector:
            availability_element = soup.select_one(availability_selector)
            if availability_element:
                availability_text = availability_element.get_text(strip=True)
                match = re.search(r"^(.*?)(?:\s*\(|$)", availability_text)
                if match:
                    result.stock_status = match.group(1).strip()
                else:
                    result.stock_status = availability_text
            else:
                logger.warning(f"Availability element not found using selector '{availability_selector}' on {product_url} for shop {self.SHOP_NAME}")
        else:
            logger.warning(f"Availability selector not configured for shop {self.SHOP_NAME}")

        return result

if __name__ == '__main__':
    # Setup basic logging if run directly
    from price_tracker_app.logging_config import setup_logging
    setup_logging(level=logging.DEBUG) # Use DEBUG for testing this scraper

    logger.info(f"--- Testing {BooksToScrapeScraper.SHOP_NAME} Scraper ---")

    test_product_url = "http://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
    scraper = BooksToScrapeScraper()

    logger.info(f"Attempting to scrape: {test_product_url}")

    scraped_data_live = scraper.scrape_product(test_product_url)

    if scraped_data_live:
        logger.info("Scraped Data (Live Test):") # Changed print to logger.info
        logger.info(f"  Name: {scraped_data_live.product_name}")
        logger.info(f"  Primary Value: {scraped_data_live.primary_value}") # Updated field name
        logger.info(f"  Value Currency: {scraped_data_live.value_currency}") # Updated field name
        logger.info(f"  Stock Status: {scraped_data_live.stock_status}")
    else:
        logger.error(f"Failed to scrape data from {test_product_url}. Check network or site structure.")

    logger.info(f"--- {BooksToScrapeScraper.SHOP_NAME} Scraper Test Finished ---")
