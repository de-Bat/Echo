import logging
import uuid
import time # For potential delays between dispatching tasks

from price_tracker_app.celery_app import app # Import the Celery app instance
from price_tracker_app.core.orchestration import process_item_url_for_recommendation
from price_tracker_app.database import crud
from price_tracker_app.database.db_setup import SessionLocal # For creating a DB session if needed directly in tasks

logger = logging.getLogger(__name__)

@app.task(bind=True, name="price_tracker_app.tasks.track_single_url_task")
def track_single_url_task(self, item_id_str: str, shop_id_str: str, product_url: str):
    """
    Celery task to process a single product URL for an item.
    It calls the orchestration logic to scrape, save price, and generate recommendation.
    """
    logger.info(f"Task track_single_url_task started. Task ID: {self.request.id}, Item ID: {item_id_str}, Shop ID: {shop_id_str}, URL: {product_url}")

    try:
        item_id = uuid.UUID(item_id_str)
        shop_id = uuid.UUID(shop_id_str)
    except ValueError as e:
        logger.error(f"Invalid UUID format for item_id or shop_id. Item ID: '{item_id_str}', Shop ID: '{shop_id_str}'. Error: {e}")
        # Optionally, re-raise or handle as a permanent failure if desired.
        # For now, just logging and letting the task complete (as failed if this were critical).
        return {"status": "error", "message": "Invalid UUID format"}

    try:
        # process_item_url_for_recommendation handles its own DB session
        recommendation = process_item_url_for_recommendation(
            item_id=item_id,
            shop_id=shop_id,
            product_url=product_url
        )

        if recommendation:
            logger.info(f"Task track_single_url_task completed successfully for Item ID: {item_id_str}, URL: {product_url}. Recommendation: {recommendation.predicted_action.value}")
            return {"status": "success", "item_id": item_id_str, "url": product_url, "recommendation_action": recommendation.predicted_action.value}
        else:
            logger.warning(f"Task track_single_url_task for Item ID: {item_id_str}, URL: {product_url} did not yield a recommendation or failed in orchestration.")
            return {"status": "warning", "item_id": item_id_str, "url": product_url, "message": "Orchestration did not yield a recommendation or failed."}

    except Exception as e:
        logger.exception(f"Unhandled exception in track_single_url_task for Item ID: {item_id_str}, URL: {product_url}:")
        # Celery can retry tasks. Configure retry behavior if needed (e.g., self.retry(exc=e, countdown=60))
        # For now, just re-raising will mark the task as FAILED.
        raise # Re-raise the exception to mark the task as failed in Celery

@app.task(bind=True, name="price_tracker_app.tasks.schedule_all_items_tracking_task")
def schedule_all_items_tracking_task(self, inter_task_delay_seconds: float = 0.1):
    """
    Celery task that fetches all items and dispatches individual tracking tasks
    for each of their product URLs.
    """
    logger.info(f"Task schedule_all_items_tracking_task started. Task ID: {self.request.id}")

    db = SessionLocal() # Create a session for this task to read items
    items_dispatched_count = 0
    urls_dispatched_count = 0

    try:
        all_items = crud.get_all_items(db)
        if not all_items:
            logger.info("No items found in the database to schedule for tracking.")
            return {"status": "success", "message": "No items to track."}

        total_items = len(all_items)
        logger.info(f"Found {total_items} items. Dispatching individual tracking tasks...")

        for i, item in enumerate(all_items):
            logger.debug(f"Dispatching tasks for item {i+1}/{total_items}: '{item.name}' (ID: {item.id})")

            item_urls = item.product_urls
            item_shop_ids_str = item.target_shops_ids # These are strings from DB JSON

            if not item_urls or not item_shop_ids_str or len(item_urls) != len(item_shop_ids_str):
                logger.warning(f"Item '{item.name}' (ID: {item.id}) has mismatched or missing URLs/Shop IDs. Skipping. URLs: {item_urls}, ShopIDs: {item_shop_ids_str}")
                continue

            for url_idx, product_url_str in enumerate(item_urls):
                shop_id_str = item_shop_ids_str[url_idx]

                # Dispatch the track_single_url_task
                # Using .delay() is a shortcut for .apply_async()
                logger.debug(f"Dispatching track_single_url_task for Item ID: {str(item.id)}, Shop ID: {shop_id_str}, URL: {product_url_str}")
                track_single_url_task.delay(str(item.id), shop_id_str, product_url_str)
                urls_dispatched_count += 1

                if inter_task_delay_seconds > 0:
                    time.sleep(inter_task_delay_seconds) # Small delay to avoid overwhelming the broker or workers too quickly

            items_dispatched_count += 1

        logger.info(f"schedule_all_items_tracking_task completed. Dispatched {urls_dispatched_count} URL tracking tasks for {items_dispatched_count} items.")
        return {"status": "success", "items_processed": items_dispatched_count, "urls_dispatched": urls_dispatched_count}

    except Exception as e:
        logger.exception("Error in schedule_all_items_tracking_task:")
        raise # Re-raise to mark as FAILED
    finally:
        db.close()

if __name__ == '__main__':
    # For testing individual tasks locally without Celery worker (not a full Celery execution)
    # You would typically run a Celery worker and then trigger tasks via `task.delay()` or `task.apply_async()`.

    # Setup basic logging if run directly
    from price_tracker_app.logging_config import setup_logging
    setup_logging(level=logging.DEBUG)

    logger.info("Running tasks.py directly for basic checks (not a full Celery execution environment).")

    # Example: How you might manually call a task for testing (simulates what Celery does)
    # This requires DB to be set up and have some data.
    # Ensure you have an item and shop in your DB, then get their IDs.

    # mock_item_id = "your-item-uuid-string"
    # mock_shop_id = "your-shop-uuid-string"
    # mock_url = "http://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"

    # if mock_item_id != "your-item-uuid-string":
    #     logger.info(f"Simulating direct call to track_single_url_task for Item ID: {mock_item_id}")
    #     # Create a mock Celery request object for the 'bind=True' task
    #     class MockRequest:
    #         id = "mock_task_id_direct_call"
    #     mock_self = MockRequest()
    #     result = track_single_url_task(mock_self, mock_item_id, mock_shop_id, mock_url)
    #     logger.info(f"Direct call result: {result}")
    # else:
    #     logger.info("Skipping direct call to track_single_url_task as mock IDs are not set.")

    # To test schedule_all_items_tracking_task, you'd need items in DB.
    # logger.info("Simulating direct call to schedule_all_items_tracking_task.")
    # class MockRequestAll:
    #     id = "mock_schedule_all_task_id"
    # mock_self_all = MockRequestAll()
    # schedule_result = schedule_all_items_tracking_task(mock_self_all, inter_task_delay_seconds=0.01)
    # logger.info(f"Direct call schedule_all_items_tracking_task result: {schedule_result}")
    # Note: This direct call to schedule_all_items_tracking_task will actually try to call
    # track_single_url_task.delay(), which would require a running Celery broker.
    # For true local testing of task logic without full Celery, you'd refactor the core logic
    # out of the @app.task decorated functions.

    logger.info("To test Celery tasks, run a Celery worker and beat, then trigger tasks via CLI or schedule.")
