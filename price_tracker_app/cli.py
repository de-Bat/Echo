import click
import uuid
from typing import Optional

from price_tracker_app.database import crud
from price_tracker_app.database.db_setup import SessionLocal, init_db as initialize_database
from price_tracker_app.core import models as core_models
from price_tracker_app.core.orchestration import process_item_url_for_recommendation, EXAMPLE_SHOP_NAME_FOR_REGISTRY # For track command

# Helper to get a DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@click.group()
def cli():
    """Price Tracker App CLI"""
    pass

@cli.command("initdb")
def initdb_command():
    """Initializes the database and creates tables."""
    click.echo("Initializing database...")
    try:
        initialize_database()
        click.secho("Database initialized successfully.", fg="green")
    except Exception as e:
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
    db_gen = get_db()
    db = next(db_gen)
    try:
        existing_shop = crud.get_shop_by_name(db, name)
        if existing_shop:
            click.secho(f"Shop '{name}' already exists.", fg="yellow")
            return

        new_shop_core = core_models.Shop(name=name, home_url=url)
        db_shop = crud.create_shop(db, new_shop_core)
        click.secho(f"Shop '{db_shop.name}' added successfully with ID: {db_shop.id}", fg="green")
    except Exception as e:
        click.secho(f"Error adding shop: {e}", fg="red")
    finally:
        next(db_gen, None) # Close DB

@shop_group.command("list")
def list_shops():
    """Lists all shops in the database."""
    db_gen = get_db()
    db = next(db_gen)
    try:
        shops = crud.get_all_shops(db)
        if not shops:
            click.echo("No shops found.")
            return
        click.echo("Shops:")
        for shop in shops:
            click.echo(f"- ID: {shop.id}, Name: {shop.name}, URL: {shop.home_url}")
    except Exception as e:
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
@click.option("--product-url", "product_urls", multiple=True, required=True, help="Full URL of the product on a shop's site. Can be specified multiple times for different shops.")
@click.option("--shop-name", "shop_names", multiple=True, required=True, help="Name of the shop for each corresponding product URL. Order should match product URLs if multiple.")
def add_item(name: str, product_urls: tuple[str], shop_names: tuple[str]):
    """Adds a new item to track."""
    db_gen = get_db()
    db = next(db_gen)
    try:
        if len(product_urls) != len(shop_names):
            click.secho("Error: The number of product URLs must match the number of shop names.", fg="red")
            return

        target_shop_ids = []
        for shop_name_for_url in shop_names:
            shop_db = crud.get_shop_by_name(db, shop_name_for_url)
            if not shop_db:
                click.secho(f"Error: Shop '{shop_name_for_url}' not found. Please add it first using 'shop add'.", fg="red")
                return
            target_shop_ids.append(shop_db.id)

        # For simplicity, the Pydantic Item model takes a list of HttpUrl for product_urls
        # and list of UUIDs for target_shops_ids.
        # The CLI provides strings, so they need conversion. Pydantic handles HttpUrl conversion.

        new_item_core = core_models.Item(
            name=name,
            product_urls=list(product_urls), # Pydantic will validate these as HttpUrl
            target_shops_ids=target_shop_ids # List of UUIDs
        )
        db_item = crud.create_item(db, new_item_core)
        click.secho(f"Item '{db_item.name}' added successfully with ID: {db_item.id}", fg="green")
        click.echo(f"  Product URLs: {db_item.product_urls}")
        click.echo(f"  Target Shop IDs: {db_item.target_shops_ids}")

    except Exception as e:
        click.secho(f"Error adding item: {e}", fg="red")
        import traceback
        traceback.print_exc()
    finally:
        next(db_gen, None)


@item_group.command("list")
def list_items():
    """Lists all tracked items."""
    db_gen = get_db()
    db = next(db_gen)
    try:
        items = crud.get_all_items(db)
        if not items:
            click.echo("No items found.")
            return
        click.echo("Tracked Items:")
        for item in items:
            # product_urls and target_shops_ids are stored as JSON in DB
            click.echo(f"- ID: {item.id}, Name: {item.name}")
            click.echo(f"  Product URLs: {item.product_urls}") # Will print the JSON string/list
            click.echo(f"  Target Shop IDs: {item.target_shops_ids}") # Will print the JSON string/list
    except Exception as e:
        click.secho(f"Error listing items: {e}", fg="red")
    finally:
        next(db_gen, None)


@item_group.command("prices")
@click.argument("item_identifier", type=str) # Can be ID or name
def item_prices(item_identifier: str):
    """Shows recent price history for an item (by ID or name)."""
    db_gen = get_db()
    db = next(db_gen)
    try:
        item_db = None
        try:
            # Try to parse as UUID first
            item_uuid = uuid.UUID(item_identifier)
            item_db = crud.get_item(db, item_uuid)
        except ValueError:
            # If not a UUID, assume it's a name (this is a simplification, names may not be unique)
            # For a real app, you might list matches or require ID for non-unique names.
            from price_tracker_app.database.models import Item as DbItem # SQLAlchemy model
            item_db = db.query(DbItem).filter(DbItem.name == item_identifier).first()

        if not item_db:
            click.secho(f"Item '{item_identifier}' not found.", fg="red")
            return

        prices = crud.get_price_entries_for_item(db, item_db.id, limit=10)
        if not prices:
            click.echo(f"No price entries found for item '{item_db.name}'.")
            return

        click.echo(f"Recent Prices for '{item_db.name}' (ID: {item_db.id}):")
        for p_entry in prices:
            shop = crud.get_shop(db, p_entry.shop_id)
            shop_name = shop.name if shop else "Unknown Shop"
            click.echo(
                f"  - Date: {p_entry.timestamp.strftime('%Y-%m-%d %H:%M')}, "
                f"Price: {p_entry.currency} {p_entry.price:.2f} "
                f"(Total: {p_entry.total_price:.2f} if available), "
                f"Shop: {shop_name}, URL: {p_entry.url_scraped_from}"
            )
    except Exception as e:
        click.secho(f"Error fetching prices: {e}", fg="red")
        import traceback
        traceback.print_exc()
    finally:
        next(db_gen, None)


# --- Track Command ---
@cli.command("track")
@click.option("--item-id", "item_id_str", required=True, help="ID of the item to track.")
@click.option("--shop-name", required=True, help=f"Name of the shop to scrape from (e.g., {EXAMPLE_SHOP_NAME_FOR_REGISTRY}, BooksToScrape).")
@click.option("--product-url", required=True, help="The specific product URL on the shop's site to scrape now.")
# @click.option("--address-id", "address_id_str", default=None, help="Optional ID of the address for context.") # Future
def track_item_url(item_id_str: str, shop_name: str, product_url: str):
    """Scrapes a specific product URL for an item, updates price, and generates a new recommendation."""
    db_gen = get_db()
    db = next(db_gen)
    try:
        try:
            item_id = uuid.UUID(item_id_str)
        except ValueError:
            click.secho("Invalid Item ID format.", fg="red")
            return

        db_item = crud.get_item(db, item_id)
        if not db_item:
            click.secho(f"Item with ID '{item_id}' not found.", fg="red")
            return

        db_shop = crud.get_shop_by_name(db, shop_name)
        if not db_shop:
            click.secho(f"Shop '{shop_name}' not found.", fg="red")
            return

        # address_id = uuid.UUID(address_id_str) if address_id_str else None # Future

        click.echo(f"Tracking item '{db_item.name}' from shop '{db_shop.name}' using URL: {product_url}")

        recommendation = process_item_url_for_recommendation(
            item_id=db_item.id,
            shop_id=db_shop.id,
            product_url=product_url,
            # address_id=address_id # Future
        )

        if recommendation:
            click.secho("\n--- Tracking Complete ---", fg="green")
            click.echo(f"  Recommendation: {recommendation.predicted_action.value}")
            click.echo(f"  Reason: {recommendation.reasoning}")
            click.echo(f"  Accuracy: {recommendation.accuracy_rank:.2f}, Certainty: {recommendation.certainty_rank:.2f}")
        else:
            click.secho("\n--- Tracking Failed or No Recommendation ---", fg="yellow")
            click.echo("Check logs or previous messages for errors during scraping or prediction.")

    except Exception as e:
        click.secho(f"Error during tracking: {e}", fg="red")
        import traceback
        traceback.print_exc()
    finally:
        next(db_gen, None)


# --- Recommendation Command ---
@cli.command("recommend")
@click.argument("item_identifier", type=str) # Can be ID or name
# @click.option("--recalculate", is_flag=True, help="Force recalculation instead of fetching latest from DB.") # Future
def get_recommendation(item_identifier: str):
    """Shows the latest recommendation for an item (by ID or name) from the database."""
    db_gen = get_db()
    db = next(db_gen)
    try:
        item_db = None
        try:
            item_uuid = uuid.UUID(item_identifier)
            item_db = crud.get_item(db, item_uuid)
        except ValueError:
            from price_tracker_app.database.models import Item as DbItem # SQLAlchemy model
            item_db = db.query(DbItem).filter(DbItem.name == item_identifier).first()

        if not item_db:
            click.secho(f"Item '{item_identifier}' not found.", fg="red")
            return

        recommendations_db = crud.get_recommendations_for_item(db, item_db.id, limit=1)
        if not recommendations_db:
            click.echo(f"No recommendations found in the database for item '{item_db.name}'.")
            click.echo("You might need to run the 'track' command first for a specific URL of this item.")
            return

        latest_rec_db = recommendations_db[0]
        click.echo(f"Latest Recommendation for '{item_db.name}' (ID: {item_db.id}):")
        click.echo(f"  Action: {latest_rec_db.predicted_action}") # Stored as string value
        click.echo(f"  Reason: {latest_rec_db.reasoning}")
        click.echo(f"  Accuracy: {latest_rec_db.accuracy_rank:.2f}")
        click.echo(f"  Certainty: {latest_rec_db.certainty_rank:.2f}")
        click.echo(f"  Generated at: {latest_rec_db.timestamp.strftime('%Y-%m-%d %H:%M')}")
        if latest_rec_db.address_id:
            address = crud.get_address(db, latest_rec_db.address_id)
            address_info = f" for address '{address.nickname or address.id}'" if address else ""
            click.echo(f"  Context: Specific to address {latest_rec_db.address_id}{address_info}")

    except Exception as e:
        click.secho(f"Error fetching recommendation: {e}", fg="red")
    finally:
        next(db_gen, None)


if __name__ == "__main__":
    # To make the CLI runnable for development:
    # python -m price_tracker_app.cli --help
    # This setup allows `python price_tracker_app/cli.py ...` if price_tracker_app is in PYTHONPATH
    # or if a setup.py entry_points is configured.
    cli()
