from sqlalchemy.orm import Session
from typing import List, Optional
import uuid

from . import models as db_models # SQLAlchemy models
from price_tracker_app.core import models as core_models # Pydantic models

# Helper to convert Pydantic UUIDs and lists of UUIDs to strings for JSON storage if needed
def pydantic_to_db_item_fields(item_data: core_models.Item) -> dict:
    db_item_dict = item_data.model_dump(exclude={"id"}) # Exclude ID if it's auto-generated or handled separately
    if item_data.product_urls:
        db_item_dict["product_urls"] = [str(url) for url in item_data.product_urls]
    if item_data.target_shops_ids:
        db_item_dict["target_shops_ids"] = [str(shop_id) for shop_id in item_data.target_shops_ids]
    return db_item_dict

# --- Shop CRUD ---
def create_shop(db: Session, shop_data: core_models.Shop) -> db_models.Shop:
    db_shop = db_models.Shop(
        id=shop_data.id, # Use Pydantic model's ID
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
        id=item_data.id, # Use Pydantic model's ID
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
    # Ensure total_price is calculated if not explicitly provided
    if price_entry_data.total_price is None:
        price_entry_data.calculate_total_price()

    db_price_entry = db_models.PriceEntry(
        id=price_entry_data.id, # Use Pydantic model's ID
        item_id=price_entry_data.item_id,
        shop_id=price_entry_data.shop_id,
        timestamp=price_entry_data.timestamp,
        price=price_entry_data.price,
        currency=price_entry_data.currency,
        shipping_cost=price_entry_data.shipping_cost,
        taxes=price_entry_data.taxes,
        _total_price=price_entry_data.total_price, # Set the backing field
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
        id=address_data.id, # Use Pydantic model's ID
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
        id=recommendation_data.id, # Use Pydantic model's ID
        item_id=recommendation_data.item_id,
        address_id=recommendation_data.address_id,
        timestamp=recommendation_data.timestamp,
        predicted_action=recommendation_data.predicted_action.value, # Store enum value
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
    # Initialize DB (create tables if they don't exist)
    init_db()

    print("Running CRUD operations test...")
    db: Session = SessionLocal()

    try:
        # Test Shop CRUD
        print("\n--- Testing Shop CRUD ---")
        amazon_core = core_models.Shop(name="Amazon CRUD Test", home_url="https://www.amazon.com")
        db_amazon = create_shop(db, amazon_core)
        print(f"Created shop: {db_amazon.name}, ID: {db_amazon.id}")
        retrieved_amazon = get_shop_by_name(db, "Amazon CRUD Test")
        if retrieved_amazon:
            print(f"Retrieved shop: {retrieved_amazon.name}")

        # Test Item CRUD
        print("\n--- Testing Item CRUD ---")
        item_core = core_models.Item(
            name="Test Product CRUD",
            product_urls=["http://amazon.com/dp/B0CRUDTEST"],
            target_shops_ids=[db_amazon.id] # Link to the shop created above
        )
        db_item = create_item(db, item_core)
        print(f"Created item: {db_item.name}, ID: {db_item.id}, Target Shops: {db_item.target_shops_ids}")
        retrieved_item = get_item(db, db_item.id)
        if retrieved_item:
            print(f"Retrieved item: {retrieved_item.name}")

        # Test PriceEntry CRUD
        print("\n--- Testing PriceEntry CRUD ---")
        price_entry_core = core_models.PriceEntry(
            item_id=db_item.id,
            shop_id=db_amazon.id,
            price=199.99,
            shipping_cost=10.0,
            taxes=5.50,
            url_scraped_from="http://amazon.com/dp/B0CRUDTEST"
        )
        # total_price will be calculated by core_models.PriceEntry or crud function
        db_price_entry = create_price_entry(db, price_entry_core)
        print(f"Created price entry: ID {db_price_entry.id}, Price {db_price_entry.price}, Total Price {db_price_entry.total_price}")

        item_prices = get_price_entries_for_item(db, db_item.id)
        print(f"Retrieved {len(item_prices)} price entries for item {db_item.id}:")
        for pe in item_prices:
            print(f"  Price: {pe.price}, Total: {pe.total_price}, Timestamp: {pe.timestamp}")

        # Test Address CRUD
        print("\n--- Testing Address CRUD ---")
        address_core = core_models.Address(
            street_address="123 Test St",
            city="Testville",
            state_province="TS",
            postal_code="12345",
            country="Testland",
            nickname="Test Home"
        )
        db_address = create_address(db, address_core)
        print(f"Created address: {db_address.nickname}, ID: {db_address.id}")
        retrieved_address = get_address(db, db_address.id)
        if retrieved_address:
             print(f"Retrieved address: {retrieved_address.nickname}")

        # Test Recommendation CRUD
        print("\n--- Testing Recommendation CRUD ---")
        recommendation_core = core_models.Recommendation(
            item_id=db_item.id,
            address_id=db_address.id,
            predicted_action=core_models.RecommendationAction.BUY,
            accuracy_rank=0.9,
            certainty_rank=0.85,
            reasoning="Test buy recommendation"
        )
        db_recommendation = create_recommendation(db, recommendation_core)
        print(f"Created recommendation: {db_recommendation.predicted_action} for item {db_recommendation.item_id}")

        item_recommendations = get_recommendations_for_item(db, db_item.id)
        print(f"Retrieved {len(item_recommendations)} recommendations for item {db_item.id}:")
        for rec in item_recommendations:
            print(f"  Action: {rec.predicted_action}, Reason: {rec.reasoning}")

        print("\nCRUD operations test completed.")

    except Exception as e:
        print(f"An error occurred during CRUD tests: {e}")
        db.rollback() # Rollback in case of error
    finally:
        db.close()
        print("Database session closed.")
