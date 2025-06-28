import click
import uuid
from typing import Optional
import logging
import time # Added for sleep

from price_tracker_app.logging_config import setup_logging
from price_tracker_app.database import crud
from price_tracker_app.database.db_setup import SessionLocal, init_db as initialize_database
from price_tracker_app.core import models as core_models
from price_tracker_app.core.orchestration import process_item_url_for_recommendation, EXAMPLE_SHOP_NAME_FOR_REGISTRY

# Helper to get a DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@click.group()
@click.option('--log-level', default='INFO', type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], case_sensitive=False), help='Set the logging level.')
def cli(log_level: str):
    """Price Tracker App CLI"""
    setup_logging(level=getattr(logging, log_level.upper()))

@cli.command("initdb")
def initdb_command():
    """Initializes the database and creates tables."""
    logger = logging.getLogger(__name__)
    logger.info("Command 'initdb' invoked.")
    try:
        initialize_database()
        logger.info("Database initialized successfully.")
        click.secho("Database initialized successfully.", fg="green")
    except Exception as e:
        logger.exception("Error during 'initdb' command:")
        click.secho(f"Error initializing database: {e}", fg="red")

# --- Shop Commands ---
@cli.group("shop")
def shop_group():
    """Manage shops."""
    pass

@shop_group.command("add")
@click.option("--name", required=True, help="Name of the shop (e.g., Amazon, ExampleShop).")
@click.option("--url", required=True, help="Homepage URL of the shop (e.g., https://www.amazon.com).")
def add_shop(name: str, url: str):
    """Adds a new shop to the database."""
    logger = logging.getLogger(__name__)
    logger.info(f"Command 'shop add' invoked: Name='{name}', URL='{url}'")
    db_gen = get_db()
    db = next(db_gen)
    try:
        existing_shop = crud.get_shop_by_name(db, name)
        if existing_shop:
            logger.warning(f"Shop '{name}' already exists with ID {existing_shop.id}.")
            click.secho(f"Shop '{name}' already exists.", fg="yellow")
            return

        new_shop_core = core_models.Shop(name=name, home_url=url)
        db_shop = crud.create_shop(db, new_shop_core)
        logger.info(f"Shop '{db_shop.name}' added successfully with ID: {db_shop.id}")
        click.secho(f"Shop '{db_shop.name}' added successfully with ID: {db_shop.id}", fg="green")
    except Exception as e:
        logger.exception(f"Error adding shop '{name}':")
        click.secho(f"Error adding shop: {e}", fg="red")
    finally:
        next(db_gen, None)

@shop_group.command("list")
def list_shops():
    """Lists all shops in the database."""
    logger = logging.getLogger(__name__)
    logger.info("Command 'shop list' invoked.")
    db_gen = get_db()
    db = next(db_gen)
    try:
        shops = crud.get_all_shops(db)
        if not shops:
            click.echo("No shops found.")
            logger.info("No shops found in database.")
            return
        click.echo("Shops:")
        for shop_item in shops: # Renamed to avoid conflict with shop_group
            click.echo(f"- ID: {shop_item.id}, Name: {shop_item.name}, URL: {shop_item.home_url}")
        logger.info(f"Listed {len(shops)} shops.")
    except Exception as e:
        logger.exception("Error listing shops:")
        click.secho(f"Error listing shops: {e}", fg="red")
    finally:
        next(db_gen, None)

# --- Item Commands ---
@cli.group("item")
def item_group():
    """Manage items."""
    pass

@item_group.command("add")
@click.option("--name", required=True, help="User-defined name for the item.")
@click.option("--product-url", "product_urls", multiple=True, required=True, help="Full URL of the product on a shop's site.")
@click.option("--shop-name", "shop_names", multiple=True, required=True, help="Name of the shop for each corresponding product URL.")
def add_item(name: str, product_urls: tuple[str], shop_names: tuple[str]):
    """Adds a new item to track."""
    logger = logging.getLogger(__name__)
    logger.info(f"Command 'item add' invoked: Name='{name}', URLs='{product_urls}', Shops='{shop_names}'")
    db_gen = get_db()
    db = next(db_gen)
    try:
        if len(product_urls) != len(shop_names):
            logger.error("Number of product URLs does not match number of shop names during item add.")
            click.secho("Error: The number of product URLs must match the number of shop names.", fg="red")
            return

        target_shop_ids = []
        for shop_name_for_url in shop_names:
            shop_db = crud.get_shop_by_name(db, shop_name_for_url)
            if not shop_db:
                logger.error(f"Shop '{shop_name_for_url}' not found during item add for item '{name}'.")
                click.secho(f"Error: Shop '{shop_name_for_url}' not found. Please add it first using 'shop add'.", fg="red")
                return
            target_shop_ids.append(shop_db.id)

        new_item_core = core_models.Item(
            name=name,
            product_urls=list(product_urls),
            target_shops_ids=target_shop_ids
        )
        db_item = crud.create_item(db, new_item_core)
        logger.info(f"Item '{db_item.name}' (ID: {db_item.id}) added successfully.")
        click.secho(f"Item '{db_item.name}' added successfully with ID: {db_item.id}", fg="green")
        click.echo(f"  Product URLs: {db_item.product_urls}")
        click.echo(f"  Target Shop IDs: {db_item.target_shops_ids}")

    except Exception as e:
        logger.exception(f"Error adding item '{name}':")
        click.secho(f"Error adding item: {e}", fg="red")
    finally:
        next(db_gen, None)

@item_group.command("list")
def list_items():
    """Lists all tracked items."""
    logger = logging.getLogger(__name__)
    logger.info("Command 'item list' invoked.")
    db_gen = get_db()
    db = next(db_gen)
    try:
        items = crud.get_all_items(db)
        if not items:
            click.echo("No items found.")
            logger.info("No items found in database.")
            return
        click.echo("Tracked Items:")
        for item_obj in items: # Renamed to avoid conflict
            click.echo(f"- ID: {item_obj.id}, Name: {item_obj.name}")
            click.echo(f"  Product URLs: {item_obj.product_urls}")
            click.echo(f"  Target Shop IDs: {item_obj.target_shops_ids}")
        logger.info(f"Listed {len(items)} items.")
    except Exception as e:
        logger.exception("Error listing items:")
        click.secho(f"Error listing items: {e}", fg="red")
    finally:
        next(db_gen, None)

@item_group.command("prices")
@click.argument("item_identifier", type=str)
def item_prices(item_identifier: str):
    """Shows recent price history for an item (by ID or name)."""
    logger = logging.getLogger(__name__)
    logger.info(f"Command 'item prices' invoked for identifier: '{item_identifier}'")
    db_gen = get_db()
    db = next(db_gen)
    try:
        item_db = None
        try:
            item_uuid = uuid.UUID(item_identifier)
            item_db = crud.get_item(db, item_uuid)
            logger.debug(f"Identifier '{item_identifier}' parsed as UUID {item_uuid}.")
        except ValueError:
            logger.debug(f"Identifier '{item_identifier}' is not a UUID, attempting lookup by name.")
            from price_tracker_app.database.models import Item as DbItem
            item_db = db.query(DbItem).filter(DbItem.name == item_identifier).first()

        if not item_db:
            logger.warning(f"Item '{item_identifier}' not found for 'prices' command.")
            click.secho(f"Item '{item_identifier}' not found.", fg="red")
            return

        prices = crud.get_price_entries_for_item(db, item_db.id, limit=10)
        if not prices:
            click.echo(f"No price entries found for item '{item_db.name}'.")
            logger.info(f"No price entries for item '{item_db.name}' (ID: {item_db.id}).")
            return

        click.echo(f"Recent Prices for '{item_db.name}' (ID: {item_db.id}):")
        for p_entry in prices:
            shop = crud.get_shop(db, p_entry.shop_id)
            shop_name_str = shop.name if shop else "Unknown Shop" # Renamed
            click.echo(
                f"  - Date: {p_entry.timestamp.strftime('%Y-%m-%d %H:%M')}, "
                f"Price: {p_entry.currency} {p_entry.price:.2f} "
                f"(Total: {p_entry.total_price:.2f} if available), "
                f"Shop: {shop_name_str}, URL: {p_entry.url_scraped_from}"
            )
        logger.info(f"Displayed {len(prices)} price entries for item '{item_db.name}'.")
    except Exception as e:
        logger.exception(f"Error fetching prices for '{item_identifier}':")
        click.secho(f"Error fetching prices: {e}", fg="red")
    finally:
        next(db_gen, None)

# --- Track Command ---
@cli.command("track")
@click.option("--item-id", "item_id_str", required=True, help="ID of the item to track.")
@click.option("--shop-name", required=True, help=f"Name of the shop to scrape from (e.g., {EXAMPLE_SHOP_NAME_FOR_REGISTRY}, BooksToScrape).")
@click.option("--product-url", required=True, help="The specific product URL on the shop's site to scrape now.")
def track_item_url(item_id_str: str, shop_name: str, product_url: str):
    """Scrapes a specific product URL for an item, updates price, and generates a new recommendation."""
    logger = logging.getLogger(__name__)
    logger.info(f"Command 'track' invoked: ItemID='{item_id_str}', Shop='{shop_name}', URL='{product_url}'")
    db_gen = get_db()
    db = next(db_gen)
    try:
        try:
            item_id_uuid = uuid.UUID(item_id_str) # Renamed
        except ValueError:
            logger.error(f"Invalid Item ID format provided to track command: {item_id_str}")
            click.secho("Invalid Item ID format.", fg="red")
            return

        db_item = crud.get_item(db, item_id_uuid)
        if not db_item:
            logger.warning(f"Item with ID '{item_id_uuid}' not found for tracking.")
            click.secho(f"Item with ID '{item_id_uuid}' not found.", fg="red")
            return

        db_shop = crud.get_shop_by_name(db, shop_name)
        if not db_shop:
            logger.warning(f"Shop '{shop_name}' not found for tracking.")
            click.secho(f"Shop '{shop_name}' not found.", fg="red")
            return

        logger.info(f"CLI: Tracking item '{db_item.name}' from shop '{db_shop.name}' using URL: {product_url}")
        click.echo(f"Tracking item '{db_item.name}' from shop '{db_shop.name}' using URL: {product_url}")

        recommendation = process_item_url_for_recommendation(
            item_id=db_item.id,
            shop_id=db_shop.id,
            product_url=product_url,
        )

        if recommendation:
            logger.info(f"CLI: Tracking complete for item {item_id_uuid}. Recommendation: {recommendation.predicted_action.value}")
            click.secho("\n--- Tracking Complete ---", fg="green")
            click.echo(f"  Recommendation: {recommendation.predicted_action.value}")
            click.echo(f"  Reason: {recommendation.reasoning}")
            click.echo(f"  Accuracy: {recommendation.accuracy_rank:.2f}, Certainty: {recommendation.certainty_rank:.2f}")
        else:
            logger.warning(f"CLI: Tracking failed or no recommendation generated for item {item_id_uuid}, URL {product_url}.")
            click.secho("\n--- Tracking Failed or No Recommendation ---", fg="yellow")
            click.echo("Check logs for errors during scraping or prediction.")

    except Exception as e:
        logger.exception(f"Error during CLI track for item ID '{item_id_str}', shop '{shop_name}':")
        click.secho(f"Error during tracking: {e}", fg="red")
    finally:
        next(db_gen, None)

# --- Recommendation Command ---
@cli.command("recommend")
@click.argument("item_identifier", type=str)
def get_recommendation(item_identifier: str):
    """Shows the latest recommendation for an item (by ID or name) from the database."""
    logger = logging.getLogger(__name__)
    logger.info(f"Command 'recommend' invoked for identifier: '{item_identifier}'")
    db_gen = get_db()
    db = next(db_gen)
    try:
        item_db = None
        try:
            item_uuid = uuid.UUID(item_identifier)
            item_db = crud.get_item(db, item_uuid)
            logger.debug(f"Identifier '{item_identifier}' parsed as UUID {item_uuid}.")
        except ValueError:
            logger.debug(f"Identifier '{item_identifier}' is not a UUID, attempting lookup by name.")
            from price_tracker_app.database.models import Item as DbItem
            item_db = db.query(DbItem).filter(DbItem.name == item_identifier).first()

        if not item_db:
            logger.warning(f"Item '{item_identifier}' not found for 'recommend' command.")
            click.secho(f"Item '{item_identifier}' not found.", fg="red")
            return

        logger.debug(f"Found item '{item_db.name}' (ID: {item_db.id}). Fetching latest recommendation.")
        recommendations_db = crud.get_recommendations_for_item(db, item_db.id, limit=1)

        if not recommendations_db:
            logger.info(f"No recommendations found in DB for item '{item_db.name}'.")
            click.echo(f"No recommendations found in the database for item '{item_db.name}'.")
            click.echo("You might need to run the 'track' command first for a specific URL of this item.")
            return

        latest_rec_db = recommendations_db[0]
        logger.info(f"Displaying latest recommendation for item '{item_db.name}': Action={latest_rec_db.predicted_action}")
        click.echo(f"Latest Recommendation for '{item_db.name}' (ID: {item_db.id}):")
        click.echo(f"  Action: {latest_rec_db.predicted_action}")
        click.echo(f"  Reason: {latest_rec_db.reasoning}")
        click.echo(f"  Accuracy: {latest_rec_db.accuracy_rank:.2f}")
        click.echo(f"  Certainty: {latest_rec_db.certainty_rank:.2f}")
        click.echo(f"  Generated at: {latest_rec_db.timestamp.strftime('%Y-%m-%d %H:%M')}")
        if latest_rec_db.address_id:
            address = crud.get_address(db, latest_rec_db.address_id)
            address_info_str = f" for address '{address.nickname or address.id}'" if address else "" # Renamed
            click.echo(f"  Context: Specific to address {latest_rec_db.address_id}{address_info_str}")

    except Exception as e:
        logger.exception(f"Error fetching recommendation for '{item_identifier}':")
        click.secho(f"Error fetching recommendation: {e}", fg="red")
    finally:
        next(db_gen, None)

if __name__ == "__main__":
    cli()

# --- Track All Command ---
@cli.command("track-all")
@click.option("--delay-per-url", type=float, default=1.0, help="Delay in seconds after processing each URL.", show_default=True)
@click.option("--delay-per-item", type=float, default=5.0, help="Delay in seconds after processing all URLs for an item.", show_default=True)
def track_all_items(delay_per_url: float, delay_per_item: float):
    """
    Tracks all items in the database by processing their associated product URLs.
    Generates new price entries and recommendations.
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Command 'track-all' invoked. Delay per URL: {delay_per_url}s, Delay per item: {delay_per_item}s")
    click.echo("Starting 'track-all' process...")

    db_gen = get_db()
    db = next(db_gen)

    items_processed_count = 0
    urls_processed_count = 0
    errors_count = 0

    try:
        all_items = crud.get_all_items(db)
        if not all_items:
            logger.info("No items found in the database to track.")
            click.echo("No items found to track.")
            return

        total_items = len(all_items)
        logger.info(f"Found {total_items} items to process.")
        click.echo(f"Found {total_items} items. Starting processing...")

        for i, item in enumerate(all_items):
            logger.info(f"Processing item {i+1}/{total_items}: '{item.name}' (ID: {item.id})")
            click.echo(f"\nProcessing item {i+1}/{total_items}: '{item.name}' (ID: {item.id})")

            item_urls = item.product_urls
            item_shop_ids = item.target_shops_ids

            if not item_urls or not item_shop_ids or len(item_urls) != len(item_shop_ids):
                logger.warning(f"Item '{item.name}' (ID: {item.id}) has mismatched or missing URLs/Shop IDs. Skipping. URLs: {item_urls}, ShopIDs: {item_shop_ids}")
                click.secho(f"  Skipping item '{item.name}': Mismatched or missing URLs/Shop IDs.", fg="yellow")
                errors_count +=1
                continue

            urls_for_item_count = 0
            for url_idx, product_url_str in enumerate(item_urls):
                shop_id_str = item_shop_ids[url_idx] # This is likely a string from JSON
                try:
                    shop_id = uuid.UUID(shop_id_str) # Convert string to UUID
                except ValueError:
                    logger.error(f"  Invalid Shop ID format '{shop_id_str}' for URL '{product_url_str}' of item '{item.name}'. Skipping this URL.")
                    click.secho(f"  Error: Invalid Shop ID format '{shop_id_str}'. Skipping URL: {product_url_str}", fg="red")
                    errors_count += 1
                    if float(delay_per_url) > 0:
                        time.sleep(delay_per_url)
                    continue

                try:
                    db_shop = crud.get_shop(db, shop_id) # shop_id is now a UUID
                    if not db_shop:
                        logger.error(f"  Shop with ID '{shop_id}' not found for URL '{product_url_str}' of item '{item.name}'. Skipping this URL.")
                        click.secho(f"  Error: Shop with ID '{shop_id}' not found. Skipping URL: {product_url_str}", fg="red")
                        errors_count +=1
                        if float(delay_per_url) > 0:
                            time.sleep(delay_per_url)
                        continue

                    click.echo(f"  Processing URL: {product_url_str} (Shop: {db_shop.name})")
                    logger.debug(f"  Calling process_item_url_for_recommendation for item '{item.name}', shop '{db_shop.name}', URL '{product_url_str}'")

                    recommendation = process_item_url_for_recommendation(
                        item_id=item.id,
                        shop_id=db_shop.id,
                        product_url=product_url_str
                    )

                    if recommendation:
                        logger.info(f"    Successfully processed URL '{product_url_str}'. Recommendation: {recommendation.predicted_action.value}")
                        click.secho(f"    Success. Recommendation: {recommendation.predicted_action.value}", fg="green")
                    else:
                        logger.warning(f"    Failed to get recommendation for URL '{product_url_str}'.")
                        click.secho(f"    Failed or no recommendation. Check logs.", fg="yellow")
                        errors_count +=1

                    urls_processed_count += 1
                    urls_for_item_count += 1

                except Exception as e_url: # Catch errors for a single URL processing
                    errors_count += 1
                    logger.exception(f"  Error processing URL '{product_url_str}' for item '{item.name}':")
                    click.secho(f"  Error processing URL {product_url_str}: {e_url}", fg="red")

                if float(delay_per_url) > 0 and urls_for_item_count < len(item_urls) : # Delay between URLs of the same item
                    logger.debug(f"Delaying {delay_per_url}s before next URL.")
                    time.sleep(delay_per_url)

            items_processed_count +=1
            if float(delay_per_item) > 0 and i < total_items -1: # Delay between items
                logger.debug(f"Delaying {delay_per_item}s before next item.")
                click.echo(f"  --- Item '{item.name}' processing complete. Delaying {delay_per_item}s... ---")
                time.sleep(delay_per_item)
            else:
                click.echo(f"  --- Item '{item.name}' processing complete. ---")


    except Exception as e_main:
        logger.exception("Critical error during 'track-all' execution:")
        click.secho(f"A critical error occurred: {e_main}", fg="red")
    finally:
        next(db_gen, None)
        logger.info(f"'track-all' finished. Items processed: {items_processed_count}. URLs processed: {urls_processed_count}. Errors: {errors_count}.")
        click.echo(f"\n--- 'track-all' process finished ---")
        click.echo(f"Total items attempted: {items_processed_count}")
        click.echo(f"Total URLs attempted: {urls_processed_count}")
        click.echo(f"Total errors encountered: {errors_count}")
