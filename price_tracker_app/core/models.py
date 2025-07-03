from typing import Optional, List
from pydantic import BaseModel, HttpUrl
from datetime import datetime
import uuid

class Address(BaseModel):
    id: uuid.UUID = uuid.uuid4()
    street_address: str
    city: str
    state_province: str
    postal_code: str
    country: str
    nickname: Optional[str] = None # e.g., "Home", "Work"

class Shop(BaseModel):
    id: uuid.UUID = uuid.uuid4()
    name: str # e.g., "Amazon", "Newegg"
    home_url: HttpUrl
    # We might add shop-specific scraping config IDs or paths here later

class Item(BaseModel):
    id: uuid.UUID = uuid.uuid4()
    name: str # User-defined name or scraped from page title
    product_urls: List[HttpUrl] # List of URLs for the same item on different shops
    target_shops_ids: List[uuid.UUID] # References to Shop objects
    # We could add GTIN (UPC/EAN) or SKU here if available

class PriceEntry(BaseModel):
    id: uuid.UUID = uuid.uuid4()
    item_id: uuid.UUID # Foreign key to Item
    shop_id: uuid.UUID # Foreign key to Shop
    timestamp: datetime = datetime.now()
    primary_value: float # Renamed from price. Can be monetary or other numeric value.
    value_currency: Optional[str] = None # Renamed from currency. E.g., "USD", "GBP", or None if not applicable.
    shipping_cost: Optional[float] = None # Applicable if primary_value is monetary
    taxes: Optional[float] = None # Applicable if primary_value is monetary
    adjusted_value: Optional[float] = None # Renamed from total_price. Calculated (primary_value + shipping + taxes) if monetary.
    url_scraped_from: HttpUrl # The specific URL this value was found at

    def calculate_adjusted_value(self):
        """
        Calculates the adjusted value. If the value is monetary (currency is set)
        and shipping/taxes are present, it adds them. Otherwise, adjusted_value is same as primary_value.
        """
        if self.primary_value is not None:
            if self.value_currency and (self.shipping_cost is not None or self.taxes is not None):
                # Only add shipping/taxes if it's explicitly monetary and costs are present
                self.adjusted_value = self.primary_value + (self.shipping_cost or 0) + (self.taxes or 0)
            else:
                self.adjusted_value = self.primary_value
        else:
            self.adjusted_value = None

class RecommendationAction(str):
    BUY = "BUY"
    WAIT = "WAIT"
    HOLD = "HOLD" # Or some other neutral term

class Recommendation(BaseModel):
    id: uuid.UUID = uuid.uuid4()
    item_id: uuid.UUID # Foreign key to Item
    address_id: Optional[uuid.UUID] = None # Optional: if recommendation is address-specific for shipping
    timestamp: datetime = datetime.now()
    predicted_action: RecommendationAction
    accuracy_rank: float # e.g., 0.0 to 1.0, model's confidence in its prediction structure
    certainty_rank: float # e.g., 0.0 to 1.0, how sure the system is about the data and overall rec
    reasoning: Optional[str] = None # Brief explanation, e.g., "Price dropped 15%", "Seasonal low expected"
    # Could also include predicted future price points or optimal buy date
    # Fields for AI model version, specific shop considered for this rec, etc.

# Example Usage (not part of the file, just for illustration)
if __name__ == "__main__":
    home_address = Address(
        street_address="123 Main St",
        city="Anytown",
        state_province="CA",
        postal_code="90210",
        country="USA",
        nickname="Home"
    )
    print(home_address.model_dump_json(indent=2))

    amazon = Shop(name="Amazon", home_url="https://www.amazon.com")
    print(amazon.model_dump_json(indent=2))

    my_item = Item(
        name="Example Product",
        product_urls=["https://www.amazon.com/dp/B0EXAMPLE"],
        target_shops_ids=[amazon.id]
    )
    print(my_item.model_dump_json(indent=2))

    price_info = PriceEntry(
        item_id=my_item.id,
        shop_id=amazon.id,
        primary_value=99.99, # Renamed
        value_currency="USD", # Renamed
        shipping_cost=5.99,
        taxes=8.00,
        url_scraped_from="https://www.amazon.com/dp/B0EXAMPLE"
    )
    price_info.calculate_adjusted_value() # Renamed method
    print(price_info.model_dump_json(indent=2))

    # Example for a non-monetary item
    non_monetary_item = Item(name="Author Quotes", product_urls=[], target_shops_ids=[])
    quote_value_entry = PriceEntry(
        item_id=non_monetary_item.id,
        shop_id=amazon.id, # Using amazon as dummy shop_id
        primary_value=10.0, # e.g., number of quotes
        value_currency=None, # Non-monetary
        url_scraped_from="http://example.com/author/someauthor"
    )
    quote_value_entry.calculate_adjusted_value()
    print(quote_value_entry.model_dump_json(indent=2))


    buy_recommendation = Recommendation(
        item_id=my_item.id,
        address_id=home_address.id,
        predicted_action=RecommendationAction.BUY,
        accuracy_rank=0.85,
        certainty_rank=0.90,
        reasoning="Price is 10% below 30-day average."
    )
    print(buy_recommendation.model_dump_json(indent=2))
