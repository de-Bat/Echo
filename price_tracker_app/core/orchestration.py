# price_tracker_app/core/orchestration.py

import uuid
from datetime import datetime
from typing import Optional, Type
import logging

from price_tracker_app.core.models import Item as CoreItem, PriceEntry as CorePriceEntry, Recommendation as CoreRecommendation, Shop as CoreShop
from price_tracker_app.database import crud
from price_tracker_app.database.db_setup import SessionLocal
from price_tracker_app.scraping.base_scraper import BaseScraper, ScrapeResult
from price_tracker_app.scraping.scrapers.example_shop import ExampleShopScraper
from price_tracker_app.scraping.scrapers.books_to_scrape_scraper import BooksToScrapeScraper
from price_tracker_app.scraping.scrapers.quotes_to_scrape_scraper import QuotesToScrapeScraper
from price_tracker_app.ai.predictor import PricePredictor

logger = logging.getLogger(__name__)

# --- Scraper Registry (Simplified) ---
SCRAPER_REGISTRY: dict[str, Type[BaseScraper]] = {
    "ExampleShop": ExampleShopScraper,
    "BooksToScrape": BooksToScrapeScraper,
    "QuotesToScrape": QuotesToScrapeScraper, # Added new scraper
}

# Placeholder names for registry and CLI help text
EXAMPLE_SHOP_NAME_FOR_REGISTRY = "ExampleShop"
BOOKSTOSCRAPE_SHOP_NAME_FOR_REGISTRY = "BooksToScrape"
QUOTESTOSCRAPE_SHOP_NAME_FOR_REGISTRY = "QuotesToScrape"


def get_scraper_for_shop(shop_name: str) -> Optional[BaseScraper]:
    scraper_class = SCRAPER_REGISTRY.get(shop_name)
    if scraper_class:
        try:
            return scraper_class()
        except Exception as e:
            logger.exception(f"Error instantiating scraper for {shop_name}:")
            return None
    logger.warning(f"No scraper registered for shop name: {shop_name}")
    return None


def process_item_url_for_recommendation(
    item_id: uuid.UUID,
    shop_id: uuid.UUID,
    product_url: str,
    db_session_factory=SessionLocal,
    address_id: Optional[uuid.UUID] = None
) -> Optional[CoreRecommendation]:
    db = db_session_factory()
    recommendation_to_return = None

    logger.info(f"Starting recommendation process for item ID {item_id}, shop ID {shop_id}, URL: {product_url}")

    try:
        db_shop = crud.get_shop(db, shop_id)
        if not db_shop:
            logger.error(f"Shop with ID {shop_id} not found.")
            return None

        logger.debug(f"Processing for shop '{db_shop.name}' (ID: {shop_id}).")

        scraper = get_scraper_for_shop(db_shop.name)
        scraped_data: Optional[ScrapeResult] = None

        if scraper:
            logger.info(f"Using scraper '{type(scraper).__name__}' for shop '{db_shop.name}'.")
            if isinstance(scraper, ExampleShopScraper): #This specific check might become cumbersome
                import os
                test_html_file = "price_tracker_app/scraping/scrapers/example_shop_page.html"
                logger.debug(f"ExampleShopScraper: Attempting to use local file '{test_html_file}'.")
                try:
                    with open(test_html_file, 'r', encoding='utf-8') as f:
                        html_content = f.read()
                    scraped_data = scraper.parse_product_data(html_content, product_url=product_url)
                    logger.info(f"ExampleShopScraper successfully used local file. Scraped: Name='{scraped_data.product_name}', Price='{scraped_data.price}'")
                except FileNotFoundError:
                    logger.error(f"Test HTML file '{test_html_file}' not found for ExampleShopScraper.")
                    return None
                except Exception:
                    logger.exception("ExampleShopScraper failed processing local file.")
                    return None
            else:
                scraped_data = scraper.scrape_product(product_url)
        else:
            logger.error(f"No scraper found for shop '{db_shop.name}' (ID: {shop_id}).")
            return None

        # Check if primary_value is None.
        if not scraped_data or scraped_data.primary_value is None:
            logger.warning(f"Failed to scrape data or essential 'primary_value' field missing for {product_url} from shop '{db_shop.name}'. Scraped data: {scraped_data}")
            return None

        logger.info(f"Successfully scraped data for {product_url}: Primary Value={scraped_data.primary_value}, Name='{scraped_data.product_name}', Currency='{scraped_data.value_currency}'")

        new_price_entry_core = CorePriceEntry(
            item_id=item_id,
            shop_id=shop_id,
            timestamp=datetime.now(),
            primary_value=scraped_data.primary_value, # Updated
            value_currency=scraped_data.value_currency, # Updated
            shipping_cost=scraped_data.shipping_cost,
            taxes=None,
            url_scraped_from=product_url
        )
        new_price_entry_core.calculate_adjusted_value() # Updated method call

        db_new_price_entry = crud.create_price_entry(db, new_price_entry_core) # crud.create_price_entry needs update
        logger.info(f"New PriceEntry saved: ID {db_new_price_entry.id}, ItemID {item_id}, PrimaryValue {db_new_price_entry.primary_value}, AdjustedValue {db_new_price_entry.adjusted_value}")

        db_item = crud.get_item(db, item_id)
        if db_item and scraped_data.product_name and db_item.name != scraped_data.product_name:
            if "placeholder" in db_item.name.lower() or not db_item.name or "Quotes by" in scraped_data.product_name: # Condition for update
                original_name = db_item.name
                db_item.name = scraped_data.product_name
                db.commit()
                db.refresh(db_item)
                logger.info(f"Item {item_id} name updated from '{original_name}' to '{db_item.name}'.")

        logger.debug(f"Initializing PricePredictor for item {item_id}")
        predictor = PricePredictor(db_session_factory=db_session_factory)
        recommendation = predictor.generate_recommendation(
            item_id=item_id,
            current_price_entry=new_price_entry_core,
            address_id=address_id
        )

        if recommendation:
            db_recommendation = crud.create_recommendation(db, recommendation)
            logger.info(f"New Recommendation generated and saved: ID {db_recommendation.id}, ItemID {item_id}, Action: {recommendation.predicted_action.value}")
            recommendation_to_return = recommendation
        else:
            logger.warning(f"Failed to generate recommendation for item {item_id} after scraping.")

    except Exception:
        logger.exception(f"Critical error in recommendation process for item {item_id}, URL {product_url}:")
    finally:
        db.close()

    return recommendation_to_return


if __name__ == "__main__":
    from price_tracker_app.database.db_setup import init_db
    from price_tracker_app.logging_config import setup_logging

    setup_logging(logging.DEBUG)
    logger.info("--- Testing Orchestration Logic ---")
    init_db()

    db = SessionLocal()
    try:
        # Test with ExampleShop
        example_shop_name_main = EXAMPLE_SHOP_NAME_FOR_REGISTRY # Renamed for clarity in this scope
        test_shop_example = crud.get_shop_by_name(db, example_shop_name_main)
        if not test_shop_example:
            core_shop_example = CoreShop(name=example_shop_name_main, home_url="http://example.com")
            test_shop_example = crud.create_shop(db, core_shop_example)
            logger.info(f"Created '{example_shop_name_main}' for orchestration test.")

        test_item_name_example = "OrchestrationTest Product Example"
        test_item_uuid_example = uuid.uuid5(uuid.NAMESPACE_DNS, test_item_name_example)
        test_item_example = crud.get_item(db, test_item_uuid_example)

        if not test_item_example:
            from price_tracker_app.database.models import Item as DbItem
            test_item_db_by_name_example = db.query(DbItem).filter(DbItem.name == test_item_name_example).first()
            if test_item_db_by_name_example:
                 test_item_example = test_item_db_by_name_example
            else:
                core_item_example = CoreItem(
                    id=test_item_uuid_example,
                    name=test_item_name_example,
                    product_urls=[f"http://{example_shop_name_main.lower()}.com/orchestration_product"],
                    target_shops_ids=[test_shop_example.id]
                )
                test_item_example = crud.create_item(db, core_item_example)
                logger.info(f"Created item '{test_item_example.name}' (ID: {test_item_example.id}) for ExampleShop.")

        if test_item_example:
            product_url_to_test_example = f"http://{example_shop_name_main.lower()}.com/product/12345" # This URL is not actually scraped by ExampleShopScraper
            logger.info(f"Processing ExampleShop item '{test_item_example.name}' (Value should be price-like)")
            rec_example = process_item_url_for_recommendation(
                item_id=test_item_example.id,
                shop_id=test_shop_example.id,
                product_url=product_url_to_test_example
            )
            if rec_example: logger.info(f"ExampleShop rec: {rec_example.predicted_action.value}")
        else:
            logger.error("Could not get or create ExampleShop test item.")

        # Test with QuotesToScrape
        quotes_shop_name_main = QUOTESTOSCRAPE_SHOP_NAME_FOR_REGISTRY
        test_shop_quotes = crud.get_shop_by_name(db, quotes_shop_name_main)
        if not test_shop_quotes:
            core_shop_quotes = CoreShop(name=quotes_shop_name_main, home_url="http://quotes.toscrape.com/")
            test_shop_quotes = crud.create_shop(db, core_shop_quotes)
            logger.info(f"Created '{quotes_shop_name_main}' for orchestration test.")

        # The item name for QuotesToScrape will be dynamically set by the scraper from "Author Name"
        # So, we can use a generic placeholder name for the item initially.
        # The product_url is the author's page.
        quotes_test_item_initial_name = "Einstein Quotes Placeholder"
        quotes_test_item_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, quotes_test_item_initial_name)

        test_item_quotes = crud.get_item(db, quotes_test_item_uuid)
        if not test_item_quotes:
            core_item_quotes = CoreItem(
                id=quotes_test_item_uuid,
                name=quotes_test_item_initial_name,
                product_urls=["http://quotes.toscrape.com/author/Albert-Einstein/"],
                target_shops_ids=[test_shop_quotes.id] # Link to QuotesToScrape shop
            )
            test_item_quotes = crud.create_item(db, core_item_quotes)
            logger.info(f"Created placeholder item '{test_item_quotes.name}' (ID: {test_item_quotes.id}) for QuotesToScrape.")

        if test_item_quotes:
            # Assuming the first URL is the one we want to test for this item
            product_url_to_test_quotes = test_item_quotes.product_urls[0] if test_item_quotes.product_urls else "http://quotes.toscrape.com/author/Albert-Einstein/"

            logger.info(f"Processing QuotesToScrape item '{test_item_quotes.name}' (Value should be quote count)")
            final_recommendation_quotes = process_item_url_for_recommendation(
                item_id=test_item_quotes.id,
                shop_id=test_shop_quotes.id, # Ensure this is the QuotesToScrape shop ID
                product_url=product_url_to_test_quotes
            )
            if final_recommendation_quotes:
                logger.info(f"--- QuotesToScrape Orchestration Test Successful for item '{test_item_quotes.name}' ---")
                logger.info(f"  Recommendation Action: {final_recommendation_quotes.predicted_action.value}")
                # Check if item name was updated by orchestration
                updated_item_quotes = crud.get_item(db, test_item_quotes.id)
                if updated_item_quotes: logger.info(f"  Item name after scraping: '{updated_item_quotes.name}'")
            else:
                logger.warning(f"--- QuotesToScrape Orchestration Test Failed or No Recommendation for item '{test_item_quotes.name}' ---")
        else:
            logger.error("Could not get or create QuotesToScrape test item.")

    except Exception:
        logger.exception("Error in orchestration test __main__ block:")
    finally:
        db.close()
        logger.info("Orchestration logic test finished.")
