from sqlalchemy.orm import Session
from typing import List, Optional
import uuid
import logging # Added for logging

from . import models as db_models # SQLAlchemy models
from price_tracker_app.core import models as core_models # Pydantic models

logger = logging.getLogger(__name__)

# Helper to convert Pydantic UUIDs and lists of UUIDs to strings for JSON storage if needed
def pydantic_to_db_item_fields(item_data: core_models.Item) -> dict:
    db_item_dict = item_data.model_dump(exclude={"id"})
    if item_data.product_urls:
        db_item_dict["product_urls"] = [str(url) for url in item_data.product_urls]
    if item_data.target_shops_ids:
        db_item_dict["target_shops_ids"] = [str(shop_id) for shop_id in item_data.target_shops_ids]
    return db_item_dict

# --- Shop CRUD ---
def create_shop(db: Session, shop_data: core_models.Shop) -> db_models.Shop:
    db_shop = db_models.Shop(
        id=shop_data.id,
        name=shop_data.name,
        home_url=str(shop_data.home_url)
    )
    db.add(db_shop)
    db.commit()
    db.refresh(db_shop)
    return db_shop

def get_shop(db: Session, shop_id: uuid.UUID) -> Optional[db_models.Shop]:
    return db.query(db_models.Shop).filter(db_models.Shop.id == shop_id).first()

def get_shop_by_name(db: Session, name: str) -> Optional[db_models.Shop]:
    return db.query(db_models.Shop).filter(db_models.Shop.name == name).first()

def get_all_shops(db: Session) -> List[db_models.Shop]:
    return db.query(db_models.Shop).all()

# --- Item CRUD ---
def create_item(db: Session, item_data: core_models.Item) -> db_models.Item:
    item_fields = pydantic_to_db_item_fields(item_data)
    db_item = db_models.Item(
        id=item_data.id,
        **item_fields
    )
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item

def get_item(db: Session, item_id: uuid.UUID) -> Optional[db_models.Item]:
    return db.query(db_models.Item).filter(db_models.Item.id == item_id).first()

def get_all_items(db: Session) -> List[db_models.Item]:
    return db.query(db_models.Item).all()

# --- PriceEntry CRUD ---
def create_price_entry(db: Session, price_entry_data: core_models.PriceEntry) -> db_models.PriceEntry:
    # Ensure adjusted_value is calculated using Pydantic model's logic before saving
    if price_entry_data.adjusted_value is None and price_entry_data.primary_value is not None:
        price_entry_data.calculate_adjusted_value()

    db_price_entry = db_models.PriceEntry(
        id=price_entry_data.id,
        item_id=price_entry_data.item_id,
        shop_id=price_entry_data.shop_id,
        timestamp=price_entry_data.timestamp,
        primary_value=price_entry_data.primary_value,     # Renamed
        value_currency=price_entry_data.value_currency, # Renamed
        shipping_cost=price_entry_data.shipping_cost,
        taxes=price_entry_data.taxes,
        _adjusted_value=price_entry_data.adjusted_value, # Renamed, set the backing field for SQLAlchemy model
        url_scraped_from=str(price_entry_data.url_scraped_from)
    )
    db.add(db_price_entry)
    db.commit()
    db.refresh(db_price_entry)
    return db_price_entry

def get_price_entries_for_item(db: Session, item_id: uuid.UUID, limit: int = 100) -> List[db_models.PriceEntry]:
    return db.query(db_models.PriceEntry)\
             .filter(db_models.PriceEntry.item_id == item_id)\
             .order_by(db_models.PriceEntry.timestamp.desc())\
             .limit(limit)\
             .all()

# --- Address CRUD ---
def create_address(db: Session, address_data: core_models.Address) -> db_models.Address:
    db_address = db_models.Address(
        id=address_data.id,
        **address_data.model_dump(exclude={"id"})
    )
    db.add(db_address)
    db.commit()
    db.refresh(db_address)
    return db_address

def get_address(db: Session, address_id: uuid.UUID) -> Optional[db_models.Address]:
    return db.query(db_models.Address).filter(db_models.Address.id == address_id).first()

def get_all_addresses(db: Session) -> List[db_models.Address]:
    return db.query(db_models.Address).all()


# --- Recommendation CRUD ---
def create_recommendation(db: Session, recommendation_data: core_models.Recommendation) -> db_models.Recommendation:
    db_recommendation = db_models.Recommendation(
        id=recommendation_data.id,
        item_id=recommendation_data.item_id,
        address_id=recommendation_data.address_id,
        timestamp=recommendation_data.timestamp,
        predicted_action=recommendation_data.predicted_action.value,
        accuracy_rank=recommendation_data.accuracy_rank,
        certainty_rank=recommendation_data.certainty_rank,
        reasoning=recommendation_data.reasoning
    )
    db.add(db_recommendation)
    db.commit()
    db.refresh(db_recommendation)
    return db_recommendation

def get_recommendations_for_item(db: Session, item_id: uuid.UUID, limit: int = 10) -> List[db_models.Recommendation]:
    return db.query(db_models.Recommendation)\
             .filter(db_models.Recommendation.item_id == item_id)\
             .order_by(db_models.Recommendation.timestamp.desc())\
             .limit(limit)\
             .all()


if __name__ == "__main__":
    from price_tracker_app.database.db_setup import SessionLocal, init_db
    from price_tracker_app.logging_config import setup_logging
    setup_logging(logging.DEBUG) # Setup logging for direct script run

    init_db()

    logger.info("Running CRUD operations test (refactored for generic value)...")
    db: Session = SessionLocal()

    try:
        logger.info("\n--- Testing Shop CRUD ---")
        amazon_core = core_models.Shop(name="Amazon CRUD Test", home_url="https://www.amazon.com")
        db_amazon = create_shop(db, amazon_core)
        logger.info(f"Created shop: {db_amazon.name}, ID: {db_amazon.id}")

        logger.info("\n--- Testing Item CRUD ---")
        item_core = core_models.Item(
            name="Test Product CRUD",
            product_urls=["http://amazon.com/dp/B0CRUDTEST"],
            target_shops_ids=[db_amazon.id]
        )
        db_item = create_item(db, item_core)
        logger.info(f"Created item: {db_item.name}, ID: {db_item.id}")

        logger.info("\n--- Testing PriceEntry CRUD (Monetary) ---")
        price_entry_core = core_models.PriceEntry(
            item_id=db_item.id,
            shop_id=db_amazon.id,
            primary_value=199.99,
            value_currency="USD",
            shipping_cost=10.0,
            taxes=5.50,
            url_scraped_from="http://amazon.com/dp/B0CRUDTEST"
        )
        db_price_entry = create_price_entry(db, price_entry_core) # Pydantic model calculates adjusted_value
        logger.info(f"Created monetary entry: ID {db_price_entry.id}, PrimaryVal {db_price_entry.primary_value}, AdjustedVal {db_price_entry.adjusted_value}, Currency {db_price_entry.value_currency}")

        item_entries = get_price_entries_for_item(db, db_item.id)
        logger.info(f"Retrieved {len(item_entries)} entries for item {db_item.id}:")
        for pe in item_entries:
            logger.info(f"  PrimaryVal: {pe.primary_value}, AdjustedVal: {pe.adjusted_value}, Currency: {pe.value_currency}, Timestamp: {pe.timestamp}")

        logger.info("\n--- Testing PriceEntry CRUD (Non-Monetary) ---")
        non_monetary_entry_core = core_models.PriceEntry(
            item_id=db_item.id,
            shop_id=db_amazon.id,
            primary_value=25.0,
            value_currency=None,
            url_scraped_from="http://example.com/product/nonmonetary"
        )
        db_non_monetary_entry = create_price_entry(db, non_monetary_entry_core)
        logger.info(f"Created non-monetary entry: ID {db_non_monetary_entry.id}, PrimaryVal {db_non_monetary_entry.primary_value}, AdjustedVal {db_non_monetary_entry.adjusted_value}, Currency {db_non_monetary_entry.value_currency}")

        logger.info("\n--- Testing Address CRUD ---")
        address_core = core_models.Address(
            street_address="123 Test St", city="Testville", state_province="TS",
            postal_code="12345", country="Testland", nickname="Test Home"
        )
        db_address = create_address(db, address_core)
        logger.info(f"Created address: {db_address.nickname}, ID: {db_address.id}")

        logger.info("\n--- Testing Recommendation CRUD ---")
        recommendation_core = core_models.Recommendation(
            item_id=db_item.id, address_id=db_address.id,
            predicted_action=core_models.RecommendationAction.BUY,
            accuracy_rank=0.9, certainty_rank=0.85, reasoning="Test buy recommendation"
        )
        db_recommendation = create_recommendation(db, recommendation_core)
        logger.info(f"Created recommendation: {db_recommendation.predicted_action} for item {db_recommendation.item_id}")

        logger.info("\nCRUD operations test completed.")

    except Exception:
        logger.exception("An error occurred during CRUD tests:")
        db.rollback()
    finally:
        db.close()
        logger.info("Database session closed.")
