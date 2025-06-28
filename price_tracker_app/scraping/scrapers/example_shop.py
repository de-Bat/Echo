from bs4 import BeautifulSoup
from typing import Optional
import logging # Added for logging

from price_tracker_app.scraping.base_scraper import BaseScraper, ScrapeResult
# Selectors are now loaded from JSON config by BaseScraper

logger = logging.getLogger(__name__)

class ExampleShopScraper(BaseScraper):
    """
    A scraper for the fictional "ExampleShop".
    This scraper is intended for testing the scraping framework.
    It can be used with the `example_shop_page.html` file.
    """
    SHOP_NAME = "ExampleShop" # Used to fetch selectors

    def __init__(self):
        # For a real shop, this would be its main URL, e.g., "https://www.exampleshop.com"
        # For this test scraper, we can use a placeholder or the file path.
        super().__init__(shop_name=self.SHOP_NAME, shop_home_url="file://./example_shop_page.html")

    def parse_product_data(self, html_content: str, product_url: str) -> ScrapeResult:
        """
        Parses the HTML content from ExampleShop to extract product data.
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        result = ScrapeResult()

        # Extract Product Name
        name_selector = self.selectors.get("product_name")
        if name_selector:
            name_element = soup.select_one(name_selector)
            if name_element:
                result.product_name = name_element.get_text(strip=True)
            else:
                logger.warning(f"Product name element not found using selector '{name_selector}' on {product_url} for shop {self.SHOP_NAME}")
        else:
            logger.warning(f"Product name selector not configured for shop {self.SHOP_NAME}.")

        # Extract Price
        price_selector = self.selectors.get("price")
        raw_price_str: Optional[str] = None
        if price_selector:
            price_element = soup.select_one(price_selector)
            if price_element:
                raw_price_str = price_element.get_text(strip=True)
                result.price = self._clean_price_string(raw_price_str) # Use inherited cleaner
            else:
                logger.warning(f"Price element not found using selector '{price_selector}' on {product_url} for shop {self.SHOP_NAME}")
        else:
            logger.warning(f"Price selector not configured for shop {self.SHOP_NAME}.")

        # Extract Currency Symbol (optional, can help validate or determine currency if not fixed)
        currency_selector = self.selectors.get("currency_symbol")
        if currency_selector:
            currency_element = soup.select_one(currency_selector)
            if currency_element:
                currency_symbol = currency_element.get_text(strip=True)
                # Basic symbol to code mapping (can be expanded)
                if currency_symbol == "$":
                    result.currency = "USD"
                elif currency_symbol == "€":
                    result.currency = "EUR"
                elif currency_symbol == "£":
                    result.currency = "GBP"
                else:
                    result.currency = "UNKNOWN" # Or keep default USD
            # else:
                # print(f"Warning: Currency symbol element not found using selector '{currency_selector}' on {product_url}")
        # else:
            # print("Warning: Currency selector not configured for ExampleShop.")

        # Extract Shipping Cost
        shipping_selector = self.selectors.get("shipping_cost")
        if shipping_selector:
            shipping_element = soup.select_one(shipping_selector)
            if shipping_element:
                result.shipping_cost = self._clean_price_string(shipping_element.get_text(strip=True))
            else:
                logger.warning(f"Shipping cost element not found using selector '{shipping_selector}' on {product_url} for shop {self.SHOP_NAME}")
        else:
            logger.warning(f"Shipping cost selector not configured for shop {self.SHOP_NAME}.")

        # Extract Stock Status
        stock_selector = self.selectors.get("stock_status")
        if stock_selector:
            stock_element = soup.select_one(stock_selector)
            if stock_element:
                result.stock_status = stock_element.get_text(strip=True)
            else:
                logger.warning(f"Stock status element not found using selector '{stock_selector}' on {product_url} for shop {self.SHOP_NAME}")
        else:
            logger.warning(f"Stock status selector not configured for shop {self.SHOP_NAME}.")

        return result

# Example of how to use this scraper (typically done by a manager or main script)
if __name__ == '__main__':
    scraper = ExampleShopScraper()

    # --- Test with the local HTML file ---
    # Construct the file path relative to this script's location or project root
    import os
    # This assumes the script is run from price_tracker_app/scraping/scrapers/
    # Adjust if running from project root or elsewhere.
    # For simplicity, let's assume it's run from the directory where example_shop_page.html is.
    # A better way would be to use absolute paths or a fixed test resource location.

    # Path assuming execution from project root `price_tracker_app`
    # file_path = "scraping/scrapers/example_shop_page.html"

    # Path assuming execution from `price_tracker_app/scraping/scrapers/`
    # current_dir = os.path.dirname(os.path.abspath(__file__))
    # file_path = os.path.join(current_dir, "example_shop_page.html")

    # For consistency in testing, let's try to make the path relative to the project root.
    # This is a bit tricky to do reliably without knowing the CWD.
    # For now, let's assume the AGENT runs commands from the repo root.
    file_path_for_testing = "price_tracker_app/scraping/scrapers/example_shop_page.html"

    # The scraper's fetch_page_content expects a URL.
    # For local files, use file:/// URI scheme.
    # Note: requests library doesn't directly support file:// URLs.
    # We need to read the file content manually for this test.

    print(f"Attempting to test with local file: {file_path_for_testing}")

    try:
        with open(file_path_for_testing, 'r', encoding='utf-8') as f:
            html_content_for_test = f.read()

        print(f"\n--- Scraping local file: {file_path_for_testing} ---")
        # We pass the content directly to parse_product_data for this local test
        # The 'product_url' argument is for context, can be the file path here.
        scraped_data = scraper.parse_product_data(html_content_for_test, product_url=f"file:///{file_path_for_testing}")

        if scraped_data:
            print("Scraped Data:")
            print(f"  Name: {scraped_data.product_name}")
            print(f"  Price: {scraped_data.price}")
            print(f"  Currency: {scraped_data.currency}")
            print(f"  Shipping Cost: {scraped_data.shipping_cost}")
            print(f"  Stock Status: {scraped_data.stock_status}")
        else:
            print("Failed to scrape data from local file.")

    except FileNotFoundError:
        print(f"Error: Test HTML file not found at '{file_path_for_testing}'. Make sure the path is correct.")
    except Exception as e:
        print(f"An error occurred during local file test: {e}")

    # --- Test with a (non-existent) web URL to see fetch_page_content behavior ---
    # print("\n--- Attempting to scrape a non-existent web URL ---")
    # non_existent_url = "http://thisurldoesnotexist.invalid/product123"
    # web_scraped_data = scraper.scrape_product(non_existent_url) # This uses fetch_page_content
    # if web_scraped_data:
    #     print("Scraped Data (Web):")
    #     print(f"  Name: {web_scraped_data.product_name}")
    #     print(f"  Price: {web_scraped_data.price}")
    #     print(f"  Currency: {web_scraped_data.currency}")
    # else:
    #     print(f"Failed to scrape data from {non_existent_url} (as expected).")

    print("\nNote: The ExampleShop selectors are placeholders. Update them in 'selectors.py' if needed.")
    print("ExampleShop 'shop_home_url' is set to a local file for this test scraper.")
