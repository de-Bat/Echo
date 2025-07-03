import logging
from bs4 import BeautifulSoup
from typing import Optional

from price_tracker_app.scraping.base_scraper import BaseScraper, ScrapeResult

logger = logging.getLogger(__name__)

class QuotesToScrapeScraper(BaseScraper):
    """
    A scraper for author pages on quotes.toscrape.com.
    Each "product" is an author's page, and the "price" (primary_value)
    can be the number of quotes by that author on the page.
    """
    SHOP_NAME = "QuotesToScrape"

    def __init__(self):
        super().__init__(shop_name=self.SHOP_NAME, shop_home_url="http://quotes.toscrape.com/")

    def parse_product_data(self, html_content: str, product_url: str) -> ScrapeResult:
        """
        Parses the HTML content from a quotes.toscrape.com author page.
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        result = ScrapeResult()

        # Extract Author Name (as Product Name)
        author_name_selector = self.selectors.get("author_name")
        if author_name_selector:
            author_element = soup.select_one(author_name_selector)
            if author_element:
                result.product_name = author_element.get_text(strip=True)
            else:
                logger.warning(f"Author name element not found using selector '{author_name_selector}' on {product_url} for shop {self.SHOP_NAME}")
        else:
            logger.warning(f"Author name selector not configured for shop {self.SHOP_NAME}")

        # Count Quotes (as Price/Primary Value)
        quote_block_selector = self.selectors.get("quote_block")
        num_quotes = 0
        if quote_block_selector:
            quote_elements = soup.select(quote_block_selector)
            num_quotes = len(quote_elements)
            # Use result.primary_value as per refactor
            result.primary_value = float(num_quotes)
            logger.debug(f"Found {num_quotes} quotes on page {product_url} for shop {self.SHOP_NAME}. Set as primary_value.")
        else:
            logger.warning(f"Quote block selector not configured for shop {self.SHOP_NAME}. Cannot count quotes.")
            result.primary_value = 0.0 # Default if selector is missing

        # value_currency is not applicable here for number of quotes.
        result.value_currency = None # Renamed

        # Stock Status / Availability
        # Consider "Available" if quotes were found and product_name (author) was found.
        if result.product_name and num_quotes > 0:
            result.stock_status = "Available"
        elif result.product_name and num_quotes == 0:
            result.stock_status = "No Quotes Found"
        else:
            result.stock_status = "Not Available" # If author name couldn't be parsed.

        # Optional: Extract all quote texts into a description or other field
        # For now, this is out of scope for the main ScrapeResult fields.
        # We could log them or store them in a custom field if ScrapeResult is extended.
        # quote_text_selector = self.selectors.get("quote_text_inner")
        # if quote_text_selector and quote_elements:
        #     all_texts = []
        #     for q_el in quote_elements:
        #         text_el = q_el.select_one(quote_text_selector)
        #         if text_el:
        #             all_texts.append(text_el.get_text(strip=True))
        #     logger.debug(f"Extracted texts: {all_texts[:2]}...") # Log first few
            # result.description = " | ".join(all_texts) # Example

        return result

if __name__ == '__main__':
    # Setup basic logging if run directly
    from price_tracker_app.logging_config import setup_logging
    setup_logging(level=logging.DEBUG)

    logger.info(f"--- Testing {QuotesToScrapeScraper.SHOP_NAME} Scraper ---")

    test_author_url = "http://quotes.toscrape.com/author/Albert-Einstein/"
    scraper = QuotesToScrapeScraper()

    logger.info(f"Attempting to scrape: {test_author_url}")

    scraped_data = scraper.scrape_product(test_author_url)

    if scraped_data:
        logger.info("Scraped Data (Live Test):")
        logger.info(f"  Product Name (Author): {scraped_data.product_name}")
        logger.info(f"  Primary Value (Num Quotes): {scraped_data.primary_value}")
        logger.info(f"  Value Currency: {scraped_data.value_currency}")
        logger.info(f"  Stock Status: {scraped_data.stock_status}")
    else:
        logger.error(f"Failed to scrape data from {test_author_url}.")

    logger.info(f"--- {QuotesToScrapeScraper.SHOP_NAME} Scraper Test Finished ---")
