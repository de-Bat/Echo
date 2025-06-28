# price_tracker_app/ai/predictor.py

from typing import List, Optional
import uuid # For Item ID, Address ID if needed for recommendation context
from datetime import datetime
import logging

from price_tracker_app.core.models import Item as CoreItem, PriceEntry as CorePriceEntry, Recommendation, RecommendationAction
from price_tracker_app.database.crud import get_price_entries_for_item # To fetch history
from price_tracker_app.database.db_setup import SessionLocal # To create a DB session

from .features import extract_features
from .models.simple_heuristic_model import SimpleHeuristicModel # Our first model

logger = logging.getLogger(__name__)

class PricePredictor:
    def __init__(self, model_instance=None, db_session_factory=None):
        self.model = model_instance if model_instance else SimpleHeuristicModel()
        self.db_session_factory = db_session_factory if db_session_factory else SessionLocal
        logger.debug(f"PricePredictor initialized with model: {type(self.model).__name__}")

    def generate_recommendation(
        self,
        item_id: uuid.UUID,
        current_price_entry: CorePriceEntry,
        address_id: Optional[uuid.UUID] = None,
        history_limit: int = 90
    ) -> Optional[Recommendation]:
        db = self.db_session_factory()
        try:
            logger.info(f"Generating recommendation for item_id: {item_id}, current price entry timestamp: {current_price_entry.timestamp}, price: {current_price_entry.price}")

            historical_entries_db = get_price_entries_for_item(db, item_id, limit=history_limit)
            logger.debug(f"Fetched {len(historical_entries_db)} historical price entries for item {item_id}.")

            if not historical_entries_db:
                price_history_for_features = [current_price_entry]
                logger.debug("No historical entries found, using current price entry as history.")
            else:
                price_history_for_features = [pe_db_to_core(pe) for pe in reversed(historical_entries_db)]
                # Ensure current_price_entry is the most recent in the list for feature calculation
                if not price_history_for_features or current_price_entry.timestamp > price_history_for_features[-1].timestamp:
                    price_history_for_features.append(current_price_entry)
                    logger.debug("Appended current price entry to historical list as it's newest.")
                elif current_price_entry.timestamp == price_history_for_features[-1].timestamp:
                    # If timestamps are identical, replace the last one from DB with the current one,
                    # assuming current_price_entry is fresher or more relevant for this exact moment.
                    # Check by ID if they are truly different entries.
                    if current_price_entry.id != price_history_for_features[-1].id:
                        price_history_for_features[-1] = current_price_entry
                        logger.debug("Replaced last historical entry with current due to same timestamp but different ID.")
                    else:
                        logger.debug("Current price entry is identical to the last historical entry. Using as is.")
                else:
                    # This case (current older than last historical) should ideally not happen if data is consistent.
                    logger.warning(f"Current price entry timestamp {current_price_entry.timestamp} is older than last historical entry {price_history_for_features[-1].timestamp}. Appending anyway.")
                    price_history_for_features.append(current_price_entry)


            if current_price_entry.total_price is None:
                current_price_entry.calculate_total_price()
                if current_price_entry.total_price is None and current_price_entry.price is not None:
                    # Fallback if total_price is still None but base price exists
                    current_price_entry.total_price = current_price_entry.price
                logger.debug(f"Calculated total_price for current_price_entry: {current_price_entry.total_price}")

            logger.debug(f"Extracting features with {len(price_history_for_features)} entries in history for features.")
            features = extract_features(price_history_for_features, current_price_entry)

            if not features: # Should ideally not be empty if current_price_entry is valid
                logger.warning(f"Could not extract features for item {item_id}. Features dict is empty.")
                return None
            logger.debug(f"Features extracted for item {item_id}: {features}")

            action, accuracy, certainty, reasoning = self.model.predict(features)
            logger.info(f"Model prediction for item {item_id}: Action={action.value}, Accuracy={accuracy:.2f}, Certainty={certainty:.2f}, Reason='{reasoning}'")

            recommendation = Recommendation(
                item_id=item_id,
                address_id=address_id,
                timestamp=datetime.now(),
                predicted_action=action,
                accuracy_rank=accuracy,
                certainty_rank=certainty,
                reasoning=reasoning
            )
            return recommendation

        except Exception:
            logger.exception(f"Error generating recommendation for item {item_id}:")
            return None
        finally:
            db.close()

def pe_db_to_core(db_pe) -> CorePriceEntry:
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
        "total_price": db_pe.total_price
    }
    entry = CorePriceEntry(**core_data)
    # Ensure total_price is calculated if it somehow ended up None from DB model
    if entry.total_price is None:
        entry.calculate_total_price()
    return entry


if __name__ == "__main__":
    from price_tracker_app.database.db_setup import init_db
    from price_tracker_app.database import models as db_models
    from price_tracker_app.database.crud import create_item, create_shop, create_price_entry
    from price_tracker_app.core.models import Shop as CoreShop, Item as CoreItem
    from price_tracker_app.logging_config import setup_logging

    setup_logging(logging.DEBUG) # Setup logging for direct script run
    logger.info("--- Testing PricePredictor ---")

    init_db()
    db = SessionLocal()

    try:
        test_shop_core = CoreShop(name="PredictTestShop", home_url="http://predicttest.com")
        db_shop = db.query(db_models.Shop).filter_by(name=test_shop_core.name).first()
        if not db_shop:
            db_shop = create_shop(db, test_shop_core)
            logger.info(f"Created shop '{db_shop.name}' for test.")

        test_item_core = CoreItem(
            name="PredictTestProduct",
            product_urls=["http://predicttest.com/product1"],
            target_shops_ids=[db_shop.id]
        )
        # Use a fixed UUID for predictability in tests if DB is reset
        test_item_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, test_item_core.name)
        test_item_core.id = test_item_uuid

        db_item = db.query(db_models.Item).filter_by(id=test_item_uuid).first()
        if not db_item:
             db_item_by_name = db.query(db_models.Item).filter_by(name=test_item_core.name).first()
             if db_item_by_name: # If exists by name, use it (e.g. after schema change without ID)
                 db_item = db_item_by_name
                 logger.info(f"Found item '{db_item.name}' by name for test.")
             else:
                db_item = create_item(db, test_item_core)
                logger.info(f"Created item '{db_item.name}' for test.")
        else:
            logger.info(f"Using existing item '{db_item.name}' for test.")


        if not get_price_entries_for_item(db, db_item.id, limit=1):
            base_time = datetime(2023, 10, 1)
            prices_data = [
                (110.0, 10.0, 5.0), (108.0, 10.0, 4.9), (105.0, 9.0, 4.5),
                (106.0, 9.0, 4.6), (100.0, 8.0, 4.0),
                (98.0, 8.0, 3.9),  (99.0, 8.0, 3.95)
            ]
            logger.info(f"Adding {len(prices_data)} mock price entries for item {db_item.name}.")
            for i, (price, ship, tax) in enumerate(prices_data):
                pe_core = CorePriceEntry(
                    item_id=db_item.id, shop_id=db_shop.id,
                    timestamp=base_time + timedelta(days=i),
                    price=price, shipping_cost=ship, taxes=tax,
                    url_scraped_from="http://predicttest.com/product1"
                )
                create_price_entry(db, pe_core)
        else:
            logger.info(f"Mock price entries already exist for item {db_item.name}.")

        current_pe_core = CorePriceEntry(
            item_id=db_item.id, shop_id=db_shop.id,
            timestamp=datetime(2023, 10, 1) + timedelta(days=len(prices_data) if 'prices_data' in locals() else 7), # Newest
            price=95.0, shipping_cost=7.0, taxes=3.5,
            url_scraped_from="http://predicttest.com/product1"
        )
        current_pe_core.calculate_total_price()
        logger.info(f"Current Price Entry for test: Price={current_pe_core.price}, Total={current_pe_core.total_price} at {current_pe_core.timestamp}")

        predictor = PricePredictor()
        logger.info(f"Generating recommendation for item: {db_item.name} (ID: {db_item.id})")
        recommendation = predictor.generate_recommendation(db_item.id, current_pe_core)

        if recommendation:
            logger.info("--- Generated Recommendation ---")
            logger.info(f"  Action: {recommendation.predicted_action.value}")
            logger.info(f"  Accuracy: {recommendation.accuracy_rank:.2f}")
            logger.info(f"  Certainty: {recommendation.certainty_rank:.2f}")
            logger.info(f"  Reasoning: {recommendation.reasoning}")
            logger.info(f"  Timestamp: {recommendation.timestamp}")
        else:
            logger.warning("Failed to generate recommendation.")

    except Exception:
        logger.exception("An error occurred during PricePredictor test:")
        db.rollback()
    finally:
        db.close()
        logger.info("PricePredictor test finished. Database session closed.")

    logger.info("Finished importing for main test section.")
