# price_tracker_app/core/orchestration.py

import uuid
from datetime import datetime
from typing import Optional, Type

from price_tracker_app.core.models import Item as CoreItem, PriceEntry as CorePriceEntry, Recommendation as CoreRecommendation, Shop as CoreShop
from price_tracker_app.database import crud
from price_tracker_app.database.db_setup import SessionLocal
from price_tracker_app.scraping.base_scraper import BaseScraper, ScrapeResult
from price_tracker_app.scraping.scrapers.example_shop import ExampleShopScraper
from price_tracker_app.scraping.scrapers.books_to_scrape_scraper import BooksToScrapeScraper # Added new scraper
from price_tracker_app.ai.predictor import PricePredictor


# --- Scraper Registry (Simplified) ---
# In a real system, this would be more dynamic, perhaps loading from plugins or config.
# Mapping shop_name or shop_id to scraper class.
SCRAPER_REGISTRY: dict[str, Type[BaseScraper]] = {
    "ExampleShop": ExampleShopScraper,
    "BooksToScrape": BooksToScrapeScraper, # Added new scraper
    # "Amazon": AmazonScraper, # etc.
}

# This is a placeholder ID. In a real system, ExampleShop would be in the DB with a UUID.
EXAMPLE_SHOP_NAME_FOR_REGISTRY = "ExampleShop" # Used in CLI help text, might need update or broader example
BOOKSTOSCRAPE_SHOP_NAME_FOR_REGISTRY = "BooksToScrape"


def get_scraper_for_shop(shop_name: str) -> Optional[BaseScraper]:
    """
    Instantiates and returns a scraper for the given shop ID.
    For now, it uses a hardcoded shop_name mapping.
    """
    scraper_class = SCRAPER_REGISTRY.get(shop_name)
    if scraper_class:
        try:
            # Some scrapers might need shop-specific URLs or configs passed here
            return scraper_class()
        except Exception as e:
            print(f"Error instantiating scraper for {shop_name}: {e}")
            return None
    print(f"No scraper registered for shop name: {shop_name}")
    return None


def process_item_url_for_recommendation(
    item_id: uuid.UUID,
    shop_id: uuid.UUID, # ID of the shop whose URL is being processed
    product_url: str, # The specific URL on the shop's site for the item
    db_session_factory=SessionLocal,
    address_id: Optional[uuid.UUID] = None # For address-specific features in future
) -> Optional[CoreRecommendation]:
    """
    Processes a single item URL: scrapes data, saves price entry, generates and saves recommendation.
    """
    db = db_session_factory()
    recommendation_to_return = None

    try:
        # 1. Get Shop Info (to select scraper)
        db_shop = crud.get_shop(db, shop_id)
        if not db_shop:
            print(f"Orchestration Error: Shop with ID {shop_id} not found.")
            return None

        # 2. Get Scraper and Scrape Data
        # For now, we'll use shop_name from DB to lookup in our simple registry
        scraper = get_scraper_for_shop(db_shop.name)

        scraped_data: Optional[ScrapeResult] = None
        if scraper:
            print(f"Using scraper for {db_shop.name} to process URL: {product_url}")
            # The ExampleShopScraper's scrape_product expects a "real" URL if it were to use requests.
            # Its parse_product_data can take HTML content directly.
            # For this test, if it's ExampleShop, we'll use its local file content.
            if isinstance(scraper, ExampleShopScraper):
                # This is specific to how ExampleShopScraper is set up for testing
                # It reads 'example_shop_page.html'
                # We need to provide the path to that file for the test
                # This is a HACK for testing the orchestration flow
                import os
                # Assuming execution from repo root
                test_html_file = "price_tracker_app/scraping/scrapers/example_shop_page.html"
                try:
                    with open(test_html_file, 'r', encoding='utf-8') as f:
                        html_content = f.read()
                    scraped_data = scraper.parse_product_data(html_content, product_url=product_url)
                    print(f"ExampleShopScraper used local file, Scraped: Name='{scraped_data.product_name}', Price='{scraped_data.price}'")
                except FileNotFoundError:
                    print(f"Orchestration Error: Test HTML file '{test_html_file}' not found for ExampleShopScraper.")
                    return None
                except Exception as e:
                    print(f"Orchestration Error: ExampleShopScraper failed with local file. {e}")
                    return None
            else:
                # For other (future) scrapers that would hit actual URLs
                scraped_data = scraper.scrape_product(product_url)
        else:
            print(f"Orchestration Error: No scraper found for shop {db_shop.name} (ID: {shop_id}).")
            return None

        if not scraped_data or scraped_data.price is None:
            print(f"Orchestration Error: Failed to scrape data or price missing for {product_url}.")
            # Optionally, still generate recommendation if enough historical data exists,
            # but for now, we require current price.
            return None

        # 3. Create and Save PriceEntry
        # TODO: Handle currency conversion if scraped_data.currency differs from a standard.
        # TODO: Scrape/estimate shipping and taxes. For now, they are None.
        new_price_entry_core = CorePriceEntry(
            item_id=item_id,
            shop_id=shop_id,
            timestamp=datetime.now(), # Actual scrape time
            price=scraped_data.price,
            currency=scraped_data.currency or "USD", # Default if not scraped
            shipping_cost=None, # Placeholder
            taxes=None, # Placeholder
            url_scraped_from=product_url
        )
        new_price_entry_core.calculate_total_price() # Total price = price if shipping/taxes are None

        db_new_price_entry = crud.create_price_entry(db, new_price_entry_core)
        print(f"New PriceEntry saved: ID {db_new_price_entry.id}, Price {db_new_price_entry.price}, Total {db_new_price_entry.total_price}")

        # (Optional) Update Item Name if it's generic and scraper found a better one
        db_item = crud.get_item(db, item_id)
        if db_item and scraped_data.product_name:
            # Example: Update if item name is a placeholder or very different
            if "placeholder" in db_item.name.lower() or not db_item.name:
                db_item.name = scraped_data.product_name
                db.commit()
                db.refresh(db_item)
                print(f"Item {item_id} name updated to '{db_item.name}'.")

        # 4. Generate Recommendation
        predictor = PricePredictor(db_session_factory=db_session_factory) # Pass along the session factory
        recommendation = predictor.generate_recommendation(
            item_id=item_id,
            current_price_entry=new_price_entry_core, # Pass the Pydantic model
            address_id=address_id
        )

        if recommendation:
            # 5. (Optional) Save Recommendation to DB
            db_recommendation = crud.create_recommendation(db, recommendation)
            print(f"New Recommendation generated and saved: ID {db_recommendation.id}, Action: {db_recommendation.predicted_action}")
            recommendation_to_return = recommendation # Return the Pydantic model
        else:
            print(f"Orchestration: Failed to generate recommendation for item {item_id} after scraping.")

    except Exception as e:
        print(f"Orchestration Error for item {item_id}, URL {product_url}: {e}")
        import traceback
        traceback.print_exc()
        # db.rollback() # Handled by session context or finally block if using 'with'
    finally:
        db.close()

    return recommendation_to_return


if __name__ == "__main__":
    from price_tracker_app.database.db_setup import init_db

    print("--- Testing Orchestration Logic ---")
    init_db() # Ensure DB and tables exist

    db = SessionLocal()
    try:
        # Setup: Ensure "ExampleShop" exists for the test
        example_shop_name = EXAMPLE_SHOP_NAME_FOR_REGISTRY
        test_shop = crud.get_shop_by_name(db, example_shop_name)
        if not test_shop:
            core_shop = CoreShop(name=example_shop_name, home_url="http://example.com")
            test_shop = crud.create_shop(db, core_shop)
            print(f"Created '{example_shop_name}' for orchestration test.")

        # Setup: Ensure an Item exists
        test_item_name = "OrchestrationTest Product"
        test_item = crud.get_item(db, uuid.uuid5(uuid.NAMESPACE_DNS, test_item_name)) # Get by a predictable ID or query
        if not test_item: # A bit of a hack to get/create item for test
             # Try to query by name
            existing_items_by_name = db.query(CoreItem).filter(CoreItem.name == test_item_name).first()
            if existing_items_by_name: # This query won't work directly, CoreItem is pydantic
                 # Correct query for SQLAlchemy model:
                 from price_tracker_app.database.models import Item as DbItem
                 existing_items_by_name = db.query(DbItem).filter(DbItem.name == test_item_name).first()
                 test_item = existing_items_by_name

            if not test_item:
                core_item = CoreItem(
                    id=uuid.uuid5(uuid.NAMESPACE_DNS, test_item_name), # Predictable ID for test
                    name=test_item_name,
                    product_urls=[f"http://{example_shop_name.lower()}.com/orchestration_product"],
                    target_shops_ids=[test_shop.id]
                )
                test_item = crud.create_item(db, core_item)
                print(f"Created item '{test_item.name}' for orchestration test.")

        # The product URL for ExampleShopScraper doesn't really matter due to local file hack,
        # but we pass one for realism.
        product_url_to_test = f"http://{example_shop_name.lower()}.com/product/12345"

        print(f"\nProcessing item '{test_item.name}' (ID: {test_item.id}) from shop '{test_shop.name}' (ID: {test_shop.id})")
        print(f"URL to process: {product_url_to_test}")

        # Make sure the item has some history for better recommendation, or predictor handles it
        # (predictor test already adds history, but this orchestration test might use a different item or clean DB)
        # For simplicity, we rely on predictor to handle sparse history.

        final_recommendation = process_item_url_for_recommendation(
            item_id=test_item.id,
            shop_id=test_shop.id,
            product_url=product_url_to_test
        )

        if final_recommendation:
            print("\n--- Orchestration Test Successful ---")
            print(f"  Recommendation Action: {final_recommendation.predicted_action.value}")
            print(f"  Reasoning: {final_recommendation.reasoning}")
        else:
            print("\n--- Orchestration Test Failed or No Recommendation ---")

    except Exception as e:
        print(f"Error in orchestration test setup or execution: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()
        print("\nOrchestration logic test finished.")
