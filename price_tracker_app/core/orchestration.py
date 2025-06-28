# price_tracker_app/core/orchestration.py

import uuid
from datetime import datetime
from typing import Optional, Type
import logging # Added for logging

from price_tracker_app.core.models import Item as CoreItem, PriceEntry as CorePriceEntry, Recommendation as CoreRecommendation, Shop as CoreShop
from price_tracker_app.database import crud
from price_tracker_app.database.db_setup import SessionLocal
from price_tracker_app.scraping.base_scraper import BaseScraper, ScrapeResult
from price_tracker_app.scraping.scrapers.example_shop import ExampleShopScraper
from price_tracker_app.scraping.scrapers.books_to_scrape_scraper import BooksToScrapeScraper
from price_tracker_app.ai.predictor import PricePredictor

logger = logging.getLogger(__name__)

# --- Scraper Registry (Simplified) ---
SCRAPER_REGISTRY: dict[str, Type[BaseScraper]] = {
    "ExampleShop": ExampleShopScraper,
    "BooksToScrape": BooksToScrapeScraper,
}

EXAMPLE_SHOP_NAME_FOR_REGISTRY = "ExampleShop"
BOOKSTOSCRAPE_SHOP_NAME_FOR_REGISTRY = "BooksToScrape"


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
            if isinstance(scraper, ExampleShopScraper):
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

        if not scraped_data or scraped_data.price is None:
            logger.warning(f"Failed to scrape data or price missing for {product_url} from shop '{db_shop.name}'.")
            return None

        logger.info(f"Successfully scraped data for {product_url}: Price {scraped_data.price}, Name '{scraped_data.product_name}'")

        new_price_entry_core = CorePriceEntry(
            item_id=item_id,
            shop_id=shop_id,
            timestamp=datetime.now(),
            price=scraped_data.price,
            currency=scraped_data.currency or "USD",
            shipping_cost=scraped_data.shipping_cost, # Now included in ScrapeResult
            taxes=None, # Still placeholder
            url_scraped_from=product_url
        )
        new_price_entry_core.calculate_total_price()

        db_new_price_entry = crud.create_price_entry(db, new_price_entry_core)
        logger.info(f"New PriceEntry saved: ID {db_new_price_entry.id}, ItemID {item_id}, Price {db_new_price_entry.price}, Total {db_new_price_entry.total_price}")

        db_item = crud.get_item(db, item_id)
        if db_item and scraped_data.product_name and db_item.name != scraped_data.product_name:
            if "placeholder" in db_item.name.lower() or not db_item.name: # Simple condition to update
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

    setup_logging(logging.DEBUG) # Setup logging for direct script run
    logger.info("--- Testing Orchestration Logic ---")
    init_db()

    db = SessionLocal()
    try:
        example_shop_name = EXAMPLE_SHOP_NAME_FOR_REGISTRY
        test_shop = crud.get_shop_by_name(db, example_shop_name)
        if not test_shop:
            core_shop = CoreShop(name=example_shop_name, home_url="http://example.com")
            test_shop = crud.create_shop(db, core_shop)
            logger.info(f"Created '{example_shop_name}' for orchestration test.")

        test_item_name = "OrchestrationTest Product"
        # Using a fixed UUID for the test item for predictability if DB is wiped.
        test_item_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, test_item_name)
        test_item = crud.get_item(db, test_item_uuid)

        if not test_item:
            from price_tracker_app.database.models import Item as DbItem # SQLAlchemy model
            test_item_db_by_name = db.query(DbItem).filter(DbItem.name == test_item_name).first()
            if test_item_db_by_name:
                 test_item = test_item_db_by_name # if it exists by name but not expected UUID
            else:
                core_item = CoreItem(
                    id=test_item_uuid,
                    name=test_item_name,
                    product_urls=[f"http://{example_shop_name.lower()}.com/orchestration_product"],
                    target_shops_ids=[test_shop.id]
                )
                test_item = crud.create_item(db, core_item)
                logger.info(f"Created item '{test_item.name}' (ID: {test_item.id}) for orchestration test.")

        product_url_to_test = f"http://{example_shop_name.lower()}.com/product/12345"

        logger.info(f"Processing item '{test_item.name}' (ID: {test_item.id}) from shop '{test_shop.name}' (ID: {test_shop.id})")
        logger.info(f"URL to process: {product_url_to_test}")

        final_recommendation = process_item_url_for_recommendation(
            item_id=test_item.id,
            shop_id=test_shop.id,
            product_url=product_url_to_test
        )

        if final_recommendation:
            logger.info("--- Orchestration Test Successful ---")
            logger.info(f"  Recommendation Action: {final_recommendation.predicted_action.value}")
            logger.info(f"  Reasoning: {final_recommendation.reasoning}")
        else:
            logger.warning("--- Orchestration Test Failed or No Recommendation ---")

    except Exception:
        logger.exception("Error in orchestration test setup or execution:")
    finally:
        db.close()
        logger.info("Orchestration logic test finished.")
