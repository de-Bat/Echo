# price_tracker_app/ai/predictor.py

from typing import List, Optional
import uuid # For Item ID, Address ID if needed for recommendation context
from datetime import datetime

from price_tracker_app.core.models import Item as CoreItem, PriceEntry as CorePriceEntry, Recommendation, RecommendationAction
from price_tracker_app.database.crud import get_price_entries_for_item # To fetch history
from price_tracker_app.database.db_setup import SessionLocal # To create a DB session

from .features import extract_features
from .models.simple_heuristic_model import SimpleHeuristicModel # Our first model

class PricePredictor:
    def __init__(self, model_instance=None, db_session_factory=None):
        """
        Initializes the PricePredictor.

        Args:
            model_instance: An instance of a prediction model (e.g., SimpleHeuristicModel).
                            If None, a default SimpleHeuristicModel is created.
            db_session_factory: A callable that returns a new SQLAlchemy Session.
                                If None, SessionLocal from db_setup will be used.
        """
        self.model = model_instance if model_instance else SimpleHeuristicModel()
        self.db_session_factory = db_session_factory if db_session_factory else SessionLocal

    def generate_recommendation(
        self,
        item_id: uuid.UUID,
        current_price_entry: CorePriceEntry, # The latest price entry, just scraped
        address_id: Optional[uuid.UUID] = None, # For address-specific considerations
        history_limit: int = 90 # Number of past price entries to consider (e.g., 90 days)
    ) -> Optional[Recommendation]:
        """
        Generates a buy/wait/hold recommendation for a given item.

        Args:
            item_id: The UUID of the item to generate a recommendation for.
            current_price_entry: The most recent PriceEntry object for the item.
                                 Ensure its total_price is calculated.
            address_id: Optional UUID of the address for context (e.g., if shipping varies).
            history_limit: Max number of historical price entries to fetch for feature calculation.

        Returns:
            A Recommendation object, or None if a recommendation cannot be generated.
        """

        db = self.db_session_factory()
        try:
            # 1. Fetch historical price data for the item
            # get_price_entries_for_item returns sorted by timestamp desc. We need asc for some features.
            historical_entries_db = get_price_entries_for_item(db, item_id, limit=history_limit)
            if not historical_entries_db:
                # If no history, we might still proceed with current price against general knowledge,
                # but features relying on history (like MAs) will be None.
                # For now, let's include the current price as the only history point.
                price_history_for_features = [current_price_entry]
            else:
                # Convert DB models to CorePriceEntry models if necessary, or ensure compatibility.
                # For now, assuming they are compatible enough or features.py handles DB models.
                # The PriceEntry in features.py is from core.models, so this should be fine.
                # We need them sorted chronologically (oldest to newest) for features.py
                price_history_for_features = [pe_db_to_core(pe) for pe in reversed(historical_entries_db)]
                # Add the current price entry to the end of the history if it's newer or not included
                if not price_history_for_features or current_price_entry.timestamp > price_history_for_features[-1].timestamp:
                     price_history_for_features.append(current_price_entry)
                elif current_price_entry.timestamp == price_history_for_features[-1].timestamp and \
                     current_price_entry.id != price_history_for_features[-1].id:
                     # If timestamp is same but different entry (e.g. different shop price at same time), replace last
                     price_history_for_features[-1] = current_price_entry


            # Ensure current_price_entry has total_price calculated.
            # The crud.create_price_entry does this, but if this is a "live" non-DB entry:
            if current_price_entry.total_price is None:
                current_price_entry.calculate_total_price()
                if current_price_entry.total_price is None and current_price_entry.price is not None:
                    # Fallback if calculate_total_price didn't set it but price exists
                    current_price_entry.total_price = current_price_entry.price


            # 2. Extract features
            # The current_price_entry should be the one for which features are centered if it's distinct
            # from the latest in history.
            features = extract_features(price_history_for_features, current_price_entry)
            if not features: # Should not happen if current_price_entry is always provided
                print(f"Warning: Could not extract features for item {item_id}.")
                return None

            # 3. Get prediction from the model
            action, accuracy, certainty, reasoning = self.model.predict(features)

            # 4. Create Recommendation object
            recommendation = Recommendation(
                item_id=item_id,
                address_id=address_id,
                timestamp=datetime.now(), # Timestamp of when the recommendation was generated
                predicted_action=action,  # Already a RecommendationAction enum from the model
                accuracy_rank=accuracy,
                certainty_rank=certainty,
                reasoning=reasoning
                # We could also store the features used, or model version, etc.
            )
            return recommendation

        except Exception as e:
            # Log the error appropriately
            print(f"Error generating recommendation for item {item_id}: {e}")
            return None
        finally:
            db.close()

def pe_db_to_core(db_pe) -> CorePriceEntry:
    """Helper to convert a database PriceEntry model to a Pydantic CorePriceEntry model."""
    # This is needed if the objects from get_price_entries_for_item are SQLAlchemy models
    # and extract_features expects Pydantic models.
    # Assuming db_models.PriceEntry has compatible field names with core_models.PriceEntry
    core_data = {
        "id": db_pe.id,
        "item_id": db_pe.item_id,
        "shop_id": db_pe.shop_id,
        "timestamp": db_pe.timestamp,
        "price": db_pe.price,
        "currency": db_pe.currency,
        "shipping_cost": db_pe.shipping_cost,
        "taxes": db_pe.taxes,
        "url_scraped_from": db_pe.url_scraped_from,
        # total_price from DB model is a hybrid_property, access it directly
        "total_price": db_pe.total_price
    }
    entry = CorePriceEntry(**core_data)
    # Pydantic model's calculate_total_price might be redundant if DB model's hybrid property works,
    # but good to ensure consistency if used.
    # entry.calculate_total_price() # Call if necessary, but db_pe.total_price should be correct
    return entry


if __name__ == "__main__":
    from price_tracker_app.database.db_setup import init_db
    # Moved db_models import higher for use in main test queries
    from price_tracker_app.database import models as db_models
    from price_tracker_app.database.crud import create_item, create_shop, create_price_entry
    from price_tracker_app.core.models import Shop as CoreShop, Item as CoreItem

    print("--- Testing PricePredictor ---")

    # 1. Initialize Database (in-memory for this test for simplicity, or use existing file)
    # For this test, let's assume the db_setup.DATABASE_URL is using a file like 'price_tracker.db'
    # And we run init_db() to ensure tables exist.
    # Note: If DATABASE_URL was "sqlite:///:memory:", each SessionLocal() would be a new DB.
    # We need a persistent DB for this test flow.
    init_db() # Ensures tables are created in 'price_tracker.db'

    # Create a session for test data setup
    db = SessionLocal()

    try:
        # 2. Setup mock data in the database
        # Create a shop
        test_shop_core = CoreShop(name="PredictTestShop", home_url="http://predicttest.com")
        # Check if shop exists to avoid re-creating, or handle unique constraint
        db_shop = db.query(db_models.Shop).filter_by(name=test_shop_core.name).first()
        if not db_shop:
            db_shop = create_shop(db, test_shop_core)

        # Create an item
        test_item_core = CoreItem(
            name="PredictTestProduct",
            product_urls=["http://predicttest.com/product1"],
            target_shops_ids=[db_shop.id]
        )
        db_item = db.query(db_models.Item).filter_by(name=test_item_core.name).first()
        if not db_item:
            db_item = create_item(db, test_item_core)

        # Add some historical price entries
        # Ensure these are added only once if script is run multiple times
        if not get_price_entries_for_item(db, db_item.id, limit=1):
            base_time = datetime(2023, 10, 1)
            prices_data = [
                (110.0, 10.0, 5.0), (108.0, 10.0, 4.9), (105.0, 9.0, 4.5),
                (106.0, 9.0, 4.6), (100.0, 8.0, 4.0), # Price drop
                (98.0, 8.0, 3.9),  (99.0, 8.0, 3.95)  # Current is 99
            ]
            for i, (price, ship, tax) in enumerate(prices_data):
                pe_core = CorePriceEntry(
                    item_id=db_item.id, shop_id=db_shop.id,
                    timestamp=base_time + timedelta(days=i),
                    price=price, shipping_cost=ship, taxes=tax,
                    url_scraped_from="http://predicttest.com/product1"
                )
                create_price_entry(db, pe_core) # This calculates and stores total_price
            print(f"Added {len(prices_data)} mock price entries for item {db_item.name}.")
        else:
            print(f"Mock price entries already exist for item {db_item.name}.")

        # 3. Create a current PriceEntry (as if it was just scraped)
        current_pe_core = CorePriceEntry(
            item_id=db_item.id, shop_id=db_shop.id,
            timestamp=datetime(2023, 10, 1) + timedelta(days=len(prices_data)), # Newest
            price=95.0, shipping_cost=7.0, taxes=3.5, # A new, lower price
            url_scraped_from="http://predicttest.com/product1"
        )
        current_pe_core.calculate_total_price() # Ensure total_price is set: 95+7+3.5 = 105.5
        print(f"Current Price Entry for test: Price={current_pe_core.price}, Total={current_pe_core.total_price} at {current_pe_core.timestamp}")

        # 4. Initialize Predictor
        predictor = PricePredictor()

        # 5. Generate Recommendation
        print(f"\nGenerating recommendation for item: {db_item.name} (ID: {db_item.id})")
        recommendation = predictor.generate_recommendation(db_item.id, current_pe_core)

        if recommendation:
            print("\n--- Generated Recommendation ---")
            print(f"  Action: {recommendation.predicted_action.value}")
            print(f"  Accuracy: {recommendation.accuracy_rank:.2f}")
            print(f"  Certainty: {recommendation.certainty_rank:.2f}")
            print(f"  Reasoning: {recommendation.reasoning}")
            print(f"  Timestamp: {recommendation.timestamp}")

            # Optionally, save the recommendation to DB
            # from .crud import create_recommendation
            # db_recommendation = create_recommendation(db, recommendation)
            # print(f"Recommendation saved with ID: {db_recommendation.id}")
        else:
            print("Failed to generate recommendation.")

    except Exception as e:
        print(f"An error occurred during PricePredictor test: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()
        print("\nPricePredictor test finished. Database session closed.")

    # from price_tracker_app.database import models as db_models # Moved to top of __main__
    print("Finished importing for main test section.")
