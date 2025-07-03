# price_tracker_app/ai/features.py

from typing import List, Optional, Dict
from datetime import datetime, timedelta
import statistics
import uuid # Added for PriceEntry mock data in __main__

# Assuming core_models.PriceEntry has 'timestamp', 'primary_value', and 'adjusted_value'
from price_tracker_app.core.models import PriceEntry # For type hinting

# --- Configuration for Sale Events ---
# This should ideally be more dynamic or loaded from a config file.
# Sale events are typically relevant for monetary items.
# For now, a simple list of (month, day) tuples for recurring sales.
# More complex sales (e.g., Easter) would need more logic.
KNOWN_SALE_DATES_ANNUAL = [
    (1, 1),   # New Year's Day
    (11, 11), # Singles' Day
    # Last Thursday of Nov for Thanksgiving, then Black Friday, then Cyber Monday - complex to define statically
    # For simplicity, let's approximate Black Friday and Cyber Monday
    (11, 25), # Approximate Black Friday ( Placeholder - real one varies)
    (11, 28), # Approximate Cyber Monday ( Placeholder - real one varies)
    (12, 25), # Christmas Day
    (12, 26), # Boxing Day
]

def get_known_sale_events_for_year(year: int) -> List[datetime]:
    """Generates datetime objects for known sale dates for a given year."""
    events = []
    for month, day in KNOWN_SALE_DATES_ANNUAL:
        try:
            events.append(datetime(year, month, day))
        except ValueError: # Handle cases like Feb 29 on non-leap year if we add it
            pass
    # TODO: Add more complex date calculations (e.g., Black Friday is 4th Friday of Nov)
    return sorted(events)


def calculate_moving_average(prices: List[float], window: int) -> Optional[float]:
    """Calculates the moving average for a list of prices and a given window size."""
    if not prices or len(prices) < window or window <= 0:
        return None
    return statistics.mean(prices[-window:])

def calculate_price_change_percentage(current_price: float, reference_price: float) -> Optional[float]:
    """Calculates the percentage change from a reference price to the current price."""
    if reference_price is None or reference_price == 0: # Avoid division by zero
        return None
    if current_price is None:
        return None
    return ((current_price - reference_price) / reference_price) * 100

def days_since_last_significant_drop(price_entries: List[PriceEntry], drop_percentage_threshold: float = 5.0) -> Optional[int]:
    """
    Calculates the number of days since the price last dropped by a significant percentage.
    Assumes price_entries are sorted chronologically (oldest to newest).
    """
    if len(price_entries) < 2:
        return None

    last_significant_drop_date: Optional[datetime] = None

    for i in range(len(price_entries) - 2, -1, -1):
        current_entry = price_entries[i+1]
        previous_entry = price_entries[i]

        # Use adjusted_value for comparison, as it's the most comparable "final" value
        current_val = current_entry.adjusted_value
        previous_val = previous_entry.adjusted_value

        if current_val is None or previous_val is None:
            continue

        change = calculate_price_change_percentage(current_val, previous_val)
        if change is not None and change < -abs(drop_percentage_threshold):
            last_significant_drop_date = current_entry.timestamp
            break

    if last_significant_drop_date:
        current_date = price_entries[-1].timestamp
        return (current_date - last_significant_drop_date).days
    return None

def days_to_next_known_sale(current_date: datetime, item_is_monetary: bool, future_look_days: int = 90) -> Optional[int]:
    """
    Calculates the number of days from current_date to the next known sale event.
    Only relevant if item_is_monetary is True.
    """
    if not item_is_monetary:
        return None # Sales events not applicable for non-monetary items

    current_year = current_date.year
    sale_events = get_known_sale_events_for_year(current_year)
    if current_date.month > (12 - future_look_days // 30):
         sale_events.extend(get_known_sale_events_for_year(current_year + 1))

    upcoming_sales = [event for event in sale_events if event > current_date]

    if not upcoming_sales:
        return None

    next_sale_date = min(upcoming_sales)
    delta = (next_sale_date - current_date).days

    if delta <= future_look_days:
        return delta
    return None


def extract_features(price_history: List[PriceEntry], current_price_entry: PriceEntry) -> Dict[str, any]:
    """
    Extracts a set of features from the price history for a given item.
    Args:
        price_history: A list of PriceEntry objects, sorted chronologically (oldest to newest).
                       This list should ideally include the current_price_entry as its last element.
        current_price_entry: The most recent PriceEntry for the item.
    """
    features = {}

    if not price_history: # Should include at least current_price_entry
        return { # Return default/empty features if no history
            "current_price": current_price_entry.total_price,
            "moving_avg_7d": None,
            "moving_avg_30d": None,
            "change_from_7d_avg": None,
            "change_from_30d_avg": None,
            "days_since_last_drop": None,
            "days_to_next_sale": None,
            "price_std_dev_30d": None,
            "min_price_30d": None,
            "max_price_30d": None,
        }

    # Ensure current_price_entry is the last one in price_history for consistency
    # Or, ensure price_history does not include current_price_entry and it's passed separately.
    # For this implementation, let's assume price_history *ends* with current_price_entry.
    # If not, it should be added or handled.

    # Use total_price for calculations if available, otherwise base price.
    # For simplicity, let's assume all entries have total_price calculated or we prioritize it.
    prices = [p.total_price for p in price_history if p.total_price is not None]
    if not prices: # Fallback if no total_prices
        prices = [p.price for p in price_history if p.price is not None]

    current_price = current_price_entry.total_price if current_price_entry.total_price is not None else current_price_entry.price
    features["current_price"] = current_price

    # Moving Averages
    features["moving_avg_7d"] = calculate_moving_average(prices, 7)
    features["moving_avg_30d"] = calculate_moving_average(prices, 30)

    # Price change from MAs
    features["change_from_7d_avg_pct"] = calculate_price_change_percentage(current_price, features["moving_avg_7d"])
    features["change_from_30d_avg_pct"] = calculate_price_change_percentage(current_price, features["moving_avg_30d"])

    # Volatility / Price Range (last 30 days or available data)
    recent_prices_30d = prices[-30:] if len(prices) >= 30 else prices
    if len(recent_prices_30d) > 1 :
        features["price_std_dev_30d"] = statistics.stdev(recent_prices_30d)
        features["min_price_30d"] = min(recent_prices_30d)
        features["max_price_30d"] = max(recent_prices_30d)
    else:
        features["price_std_dev_30d"] = 0
        features["min_price_30d"] = current_price
        features["max_price_30d"] = current_price


    # Days since last significant drop
    # Ensure price_history is properly sorted by timestamp if not already guaranteed
    # sorted_history = sorted(price_history, key=lambda p: p.timestamp) # Uncomment if sorting is needed
    features["days_since_last_drop"] = days_since_last_significant_drop(price_history, drop_percentage_threshold=5.0)

    # Days to next known sale
    features["days_to_next_sale"] = days_to_next_known_sale(current_price_entry.timestamp)

    # Could add more:
    # - Number of price changes in last X days
    # - Trend indicators (e.g., slope of price line)
    # - Comparison to similar items (very advanced)

    return features


if __name__ == "__main__":
    print("--- Testing Feature Extraction Functions ---")

    # Mock PriceEntry data
    # For monetary item
    mock_monetary_entries = [
        PriceEntry(id=uuid.uuid4(), item_id=uuid.uuid4(), shop_id=uuid.uuid4(), timestamp=datetime(2023, 1, 1), primary_value=100.0, value_currency="USD", url_scraped_from="http://example.com/p1"),
        PriceEntry(id=uuid.uuid4(), item_id=uuid.uuid4(), shop_id=uuid.uuid4(), timestamp=datetime(2023, 1, 2), primary_value=102.0, value_currency="USD", url_scraped_from="http://example.com/p1"),
        PriceEntry(id=uuid.uuid4(), item_id=uuid.uuid4(), shop_id=uuid.uuid4(), timestamp=datetime(2023, 1, 3), primary_value=101.0, value_currency="USD", url_scraped_from="http://example.com/p1"),
        PriceEntry(id=uuid.uuid4(), item_id=uuid.uuid4(), shop_id=uuid.uuid4(), timestamp=datetime(2023, 1, 4), primary_value=95.0,  value_currency="USD", url_scraped_from="http://example.com/p1"),
        PriceEntry(id=uuid.uuid4(), item_id=uuid.uuid4(), shop_id=uuid.uuid4(), timestamp=datetime(2023, 1, 5), primary_value=96.0,  value_currency="USD", url_scraped_from="http://example.com/p1"),
        PriceEntry(id=uuid.uuid4(), item_id=uuid.uuid4(), shop_id=uuid.uuid4(), timestamp=datetime(2023, 1, 6), primary_value=90.0,  value_currency="USD", url_scraped_from="http://example.com/p1"),
        PriceEntry(id=uuid.uuid4(), item_id=uuid.uuid4(), shop_id=uuid.uuid4(), timestamp=datetime(2023, 1, 7), primary_value=88.0,  value_currency="USD", url_scraped_from="http://example.com/p1"),
    ]
    for entry in mock_monetary_entries: entry.calculate_adjusted_value() # Calculate adjusted_value

    # For non-monetary item
    mock_non_monetary_entries = [
        PriceEntry(id=uuid.uuid4(), item_id=uuid.uuid4(), shop_id=uuid.uuid4(), timestamp=datetime(2023, 1, 1), primary_value=10.0, value_currency=None, url_scraped_from="http://example.com/q1"),
        PriceEntry(id=uuid.uuid4(), item_id=uuid.uuid4(), shop_id=uuid.uuid4(), timestamp=datetime(2023, 1, 2), primary_value=12.0, value_currency=None, url_scraped_from="http://example.com/q1"),
    ]
    for entry in mock_non_monetary_entries: entry.calculate_adjusted_value()

    logger.info("--- Testing Feature Extraction Functions ---")

    values_only = [p.adjusted_value for p in mock_monetary_entries if p.adjusted_value is not None]
    logger.info(f"Adjusted Values (Monetary): {values_only}")
    logger.info(f"Moving Average (3-day window, Monetary): {calculate_moving_average(values_only, 3)}")

    logger.info(f"Value change from 100 to 88: {calculate_price_change_percentage(88.0, 100.0)}%")

    logger.info(f"Days since last significant drop (Monetary, threshold 5%): {days_since_last_significant_drop(mock_monetary_entries, 5.0)}")

    current_test_date = datetime(2023, 11, 1)
    logger.info(f"Days to next known sale from {current_test_date.date()} (Monetary Item): {days_to_next_known_sale(current_test_date, item_is_monetary=True)}")
    logger.info(f"Days to next known sale from {current_test_date.date()} (Non-Monetary Item): {days_to_next_known_sale(current_test_date, item_is_monetary=False)}")


    logger.info("\n--- Full Feature Extraction (Monetary) ---")
    if mock_monetary_entries:
        current_entry_monetary = mock_monetary_entries[-1]
        extracted_ft_monetary = extract_features(mock_monetary_entries, current_entry_monetary)
        logger.info("Extracted Features (Monetary):")
        for k, v in extracted_ft_monetary.items(): logger.info(f"  {k}: {v}")

    logger.info("\n--- Full Feature Extraction (Non-Monetary) ---")
    if mock_non_monetary_entries:
        current_entry_non_monetary = mock_non_monetary_entries[-1]
        extracted_ft_non_monetary = extract_features(mock_non_monetary_entries, current_entry_non_monetary)
        logger.info("Extracted Features (Non-Monetary):")
        for k, v in extracted_ft_non_monetary.items(): logger.info(f"  {k}: {v}")

    logger.info("\nDone testing features.py")
