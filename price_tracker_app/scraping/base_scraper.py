import requests
from bs4 import BeautifulSoup
from abc import ABC, abstractmethod
from typing import Optional, Tuple, Dict
import re
import json
import os
import logging # Added for logging
from pydantic import BaseModel # Added for ScrapeResult

from price_tracker_app.scraping import get_random_user_agent # Updated import
# from price_tracker_app.scraping.selectors import get_shop_selectors # Will be removed
from price_tracker_app.core.models import PriceEntry # For type hinting eventually

logger = logging.getLogger(__name__)
SHOP_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "shop_configs")
# Assuming proxy_config.json is in the project root, relative to where the app is typically run from.
# This path might need adjustment based on actual execution context.
# For robustness, an absolute path derived from a known root or env var would be better in a complex app.
PROXY_CONFIG_FILE_PATH = "proxy_config.json"


class ScrapeResult(BaseModel): # Using Pydantic for structured result
    product_name: Optional[str] = None
    primary_value: Optional[float] = None # Renamed from price
    value_currency: Optional[str] = None  # Renamed from currency, and truly optional
    shipping_cost: Optional[float] = None
    stock_status: Optional[str] = None
    # Potentially add: product_description, etc.

class BaseScraper(ABC):
    """
    Abstract base class for shop scrapers.
    """
    def __init__(self, shop_name: str, shop_home_url: str):
        self.shop_name = shop_name
        self.shop_home_url = shop_home_url
        self.selectors = self._load_shop_selectors(shop_name)
        if not self.selectors:
            raise ValueError(f"No selectors found for shop: {shop_name}. Ensure '{shop_name.lower()}.json' exists in {SHOP_CONFIG_PATH} or '{shop_name}' key is in a general config.")

        self.base_headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br", # requests handles decoding
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none", # or "cross-site" if appropriate, or remove
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }
        self.proxies_enabled = False
        self.proxy_list = []
        self.current_proxy_index = 0 # For rotation
        self._load_proxy_config()


    def _load_proxy_config(self):
        if not os.path.exists(PROXY_CONFIG_FILE_PATH):
            logger.info(f"Proxy config file '{PROXY_CONFIG_FILE_PATH}' not found. Proxies will be disabled.")
            self.proxies_enabled = False
            return

        try:
            with open(PROXY_CONFIG_FILE_PATH, 'r') as f:
                config = json.load(f)

            self.proxies_enabled = config.get("enable_proxies", False)
            if self.proxies_enabled:
                self.proxy_list = config.get("proxies", [])
                if not self.proxy_list:
                    logger.warning("Proxies are enabled, but the proxy list is empty in config. Disabling proxies.")
                    self.proxies_enabled = False
                else:
                    logger.info(f"Loaded {len(self.proxy_list)} proxies. Proxy usage is enabled.")
                    # Could implement different rotation strategies based on "rotate_proxies"
                    # For now, we'll just pick one or rotate.
            else:
                logger.info("Proxy usage is disabled via config file.")

        except json.JSONDecodeError:
            logger.error(f"Error decoding JSON from proxy config file '{PROXY_CONFIG_FILE_PATH}'. Proxies disabled.")
            self.proxies_enabled = False
        except Exception as e:
            logger.exception(f"Error loading proxy config file '{PROXY_CONFIG_FILE_PATH}':")
            self.proxies_enabled = False


    def _load_shop_selectors(self, shop_name_key: str) -> Dict:
        """
        Loads selectors for a given shop from a JSON file named '[shop_name_key.lower()].json'
        The JSON file should contain an object where the key is shop_name_key.
        """
        config_file_name = f"{shop_name_key.lower()}.json"
        file_path = os.path.join(CONFIG_PATH, config_file_name)

        if not os.path.exists(file_path):
            logger.warning(f"Selector config file not found: {file_path}")
            return {}

        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            return data.get(shop_name_key, {})
        except json.JSONDecodeError:
            logger.error(f"Could not decode JSON from {file_path}")
            return {}
        except Exception as e:
            logger.exception(f"Error loading selector config file {file_path}:")
            return {}

    def _get_next_proxy(self) -> Optional[str]:
        """Rotates through the proxy list and returns the next proxy."""
        if not self.proxies_enabled or not self.proxy_list:
            return None

        proxy = self.proxy_list[self.current_proxy_index]
        self.current_proxy_index = (self.current_proxy_index + 1) % len(self.proxy_list)
        logger.debug(f"Using proxy: {proxy} (index {self.current_proxy_index -1})")
        return proxy

    def fetch_page_content(self, url: str) -> Optional[str]:
        """
        Fetches the HTML content of a given URL, optionally using a proxy.
        Returns the content as a string, or None if an error occurs.
        """
        request_headers = self.base_headers.copy()
        request_headers["User-Agent"] = get_random_user_agent()

        proxies_to_use = None
        if self.proxies_enabled and self.proxy_list:
            chosen_proxy = self._get_next_proxy()
            if chosen_proxy:
                proxies_to_use = {
                    "http": chosen_proxy,
                    "https": chosen_proxy,
                }
                logger.debug(f"Attempting fetch for {url} using proxy: {chosen_proxy}")

        if not proxies_to_use:
            logger.debug(f"Attempting fetch for {url} without proxy.")

        try:
            response = requests.get(url, headers=request_headers, proxies=proxies_to_use, timeout=20) # Increased timeout for proxies
            response.raise_for_status()
            logger.info(f"Successfully fetched URL {url}, status {response.status_code}" + (f" via proxy {chosen_proxy}" if proxies_to_use else ""))
            return response.text
        except requests.exceptions.RequestException as e:
            proxy_msg = f" via proxy {chosen_proxy}" if proxies_to_use and chosen_proxy else " (direct connection)"
            logger.error(f"Error fetching URL {url}{proxy_msg}: {e}")
            # TODO: Implement more sophisticated error handling for proxies, e.g.,
            # - Mark proxy as bad temporarily or permanently
            # - Retry with a different proxy or without proxy
            return None

    def _clean_price_string(self, price_str: str) -> float:
        """
        Cleans a price string (e.g., "$19.99", "£25.00", "€10,50") and converts it to a float.
        This will likely need to be overridden or made more robust for different formats.
        """
        if price_str is None:
            return 0.0
        # Remove currency symbols, thousands separators, and keep only digits and decimal point
        cleaned_price = re.sub(r'[^\d\.]', '', price_str)
        try:
            return float(cleaned_price)
        except ValueError:
            logger.warning(f"Could not convert cleaned price string '{cleaned_price}' (original: '{price_str}') to float.")
            return 0.0


    @abstractmethod
    def parse_product_data(self, html_content: str, product_url: str) -> ScrapeResult:
        """
        Parses the HTML content to extract product name, price, and other relevant data.
        This method MUST be implemented by subclasses.

        Args:
            html_content: The HTML content of the product page.
            product_url: The URL of the product page (for context or logging).

        Returns:
            A ScrapeResult object containing the extracted data.
        """
        pass

    def scrape_product(self, product_url: str) -> Optional[ScrapeResult]:
        """
        Orchestrates the scraping of a single product page.
        Fetches page content and then calls the parsing logic.
        """
        html_content = self.fetch_page_content(product_url)
        if html_content:
            try:
                logger.debug(f"Parsing product data for {product_url} from {self.shop_name}")
                return self.parse_product_data(html_content, product_url)
            except Exception as e:
                logger.exception(f"Error parsing product data for {product_url} from {self.shop_name}:")
                return None
        else:
            logger.warning(f"No HTML content fetched for {product_url}, cannot parse.")
            return None

if __name__ == '__main__':
    # This is for basic illustration; direct instantiation of BaseScraper will fail
    # because of the abstract method.
    print("BaseScraper defined. Subclasses should implement parse_product_data.")

    # Example of how ScrapeResult can be used
    result = ScrapeResult(product_name="Test Product", price=19.99, currency="USD")
    print(f"Example ScrapeResult: {result.model_dump_json(indent=2)}")

    # Test the cleaner (can be moved to a test file)
    class DummyScraper(BaseScraper): # Create a dummy for testing _clean_price_string
        def __init__(self):
            super().__init__("ExampleShop", "http://example.com")

        def parse_product_data(self, html_content: str, product_url: str) -> ScrapeResult:
            return ScrapeResult() # Dummy implementation

    ds = DummyScraper()
    print(f"' $19.99 ' -> {ds._clean_price_string(' $19.99 ')}")
    print(f"'£25.00' -> {ds._clean_price_string('£25.00')}")
    print(f"'€10,50' -> {ds._clean_price_string('€10,50')}") # This will fail with current regex, needs improvement for comma decimal
    print(f"'1,234.56' -> {ds._clean_price_string('1,234.56')}") # This might also need adjustment if comma is for thousands

    # A more robust cleaner for price strings
    def robust_clean_price_string(price_str: str) -> float:
        if price_str is None:
            return 0.0
        # Remove common currency symbols and whitespace
        price_str = re.sub(r'[$\s€£¥]', '', price_str).strip()

        # Check if comma is used as a decimal separator (common in Europe)
        if ',' in price_str and '.' in price_str:
            # Ambiguous, e.g., "1.234,56" or "1,234.56"
            # If comma is last, assume it's decimal
            if price_str.rfind(',') > price_str.rfind('.'):
                price_str = price_str.replace('.', '').replace(',', '.') # "1.234,56" -> "1234.56"
            else: # Assume dot is decimal, comma is thousand separator
                price_str = price_str.replace(',', '') # "1,234.56" -> "1234.56"
        elif ',' in price_str: # Only comma present, assume it's decimal
             price_str = price_str.replace(',', '.')

        # price_str should now only have digits and at most one decimal point
        try:
            return float(price_str)
        except ValueError:
            print(f"Warning: Could not convert cleaned price string '{price_str}' to float.")
            return 0.0

    print("--- Robust Cleaner ---")
    print(f"' $19.99 ' -> {robust_clean_price_string(' $19.99 ')}")
    print(f"'£25.00' -> {robust_clean_price_string('£25.00')}")
    print(f"'€10,50' -> {robust_clean_price_string('€10,50')}")
    print(f"'1,234.56' -> {robust_clean_price_string('1,234.56')}")
    print(f"'1.234,56' -> {robust_clean_price_string('1.234,56')}")
    print(f"'R$ 19,90' -> {robust_clean_price_string('R$ 19,90')}") # Example with other symbols

    # I will replace the _clean_price_string with the robust one.
    BaseScraper._clean_price_string = robust_clean_price_string
    print("Replaced _clean_price_string with robust_clean_price_string in BaseScraper.")
