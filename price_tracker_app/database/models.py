import uuid
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID # Using PostgreSQL UUID for broader compatibility, works with SQLite too
from sqlalchemy.types import TypeDecorator, CHAR
from sqlalchemy.ext.hybrid import hybrid_property


from price_tracker_app.database.db_setup import Base
from datetime import datetime

# Custom UUID type for SQLAlchemy to ensure we're working with Python UUID objects
class GUID(TypeDecorator):
    """Platform-independent GUID type.

    Uses PostgreSQL's UUID type, otherwise uses
    CHAR(32), storing as string.
    """
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(UUID(as_uuid=True))
        else:
            return dialect.type_descriptor(CHAR(32))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        elif dialect.name == 'postgresql':
            return str(value) # Pass as string to PG UUID type
        else:
            if not isinstance(value, uuid.UUID):
                return "%.32x" % uuid.UUID(value).int
            else:
                # hexstring
                return "%.32x" % value.int

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if not isinstance(value, uuid.UUID):
            value = uuid.UUID(value)
        return value

class Address(Base):
    __tablename__ = "addresses"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    street_address = Column(String, nullable=False)
    city = Column(String, nullable=False)
    state_province = Column(String, nullable=False)
    postal_code = Column(String, nullable=False)
    country = Column(String, nullable=False)
    nickname = Column(String, nullable=True)

    recommendations = relationship("Recommendation", back_populates="address")

class Shop(Base):
    __tablename__ = "shops"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, nullable=False, index=True)
    home_url = Column(String, nullable=False) # HttpUrl is validated by Pydantic, stored as String

    price_entries = relationship("PriceEntry", back_populates="shop")
    # If we use an association table for Item.target_shops_ids:
    # items = relationship("Item", secondary="item_shops_association", back_populates="target_shops")


class Item(Base):
    __tablename__ = "items"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False, index=True)
    # Storing list of URLs as JSON string array
    product_urls = Column(JSON) # Expects a list of strings: e.g., ['http://url1', 'http://url2']
    # Storing list of shop UUIDs as JSON string array
    target_shops_ids = Column(JSON) # Expects a list of UUID strings: e.g., [str(uuid1), str(uuid2)]

    price_entries = relationship("PriceEntry", back_populates="item", cascade="all, delete-orphan")
    recommendations = relationship("Recommendation", back_populates="item", cascade="all, delete-orphan")

    # If using an association table for target_shops:
    # target_shops = relationship("Shop", secondary="item_shops_association", back_populates="items")

# Association table for many-to-many between Item and Shop (Optional, if not using JSON for target_shops_ids)
# class ItemShopsAssociation(Base):
#     __tablename__ = "item_shops_association"
#     item_id = Column(GUID, ForeignKey("items.id"), primary_key=True)
#     shop_id = Column(GUID, ForeignKey("shops.id"), primary_key=True)


class PriceEntry(Base):
    __tablename__ = "price_entries"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    item_id = Column(GUID, ForeignKey("items.id"), nullable=False, index=True)
    shop_id = Column(GUID, ForeignKey("shops.id"), nullable=False, index=True)

    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    primary_value = Column(Float, nullable=False) # Renamed from price
    value_currency = Column(String(10), nullable=True) # Renamed from currency, increased length, nullable
    shipping_cost = Column(Float, nullable=True)
    taxes = Column(Float, nullable=True)
    _adjusted_value = Column("adjusted_value", Float, nullable=True) # Renamed from _total_price

    url_scraped_from = Column(Text, nullable=False) # HttpUrl validated by Pydantic

    item = relationship("Item", back_populates="price_entries")
    shop = relationship("Shop", back_populates="price_entries")

    @hybrid_property
    def adjusted_value(self):
        if self._adjusted_value is not None:
            return self._adjusted_value # Use pre-calculated if available

        if self.primary_value is not None:
            # Only add shipping/taxes if currency is present (implies monetary value)
            if self.value_currency and (self.shipping_cost is not None or self.taxes is not None):
                return self.primary_value + (self.shipping_cost or 0) + (self.taxes or 0)
            return self.primary_value # For non-monetary or when no shipping/taxes
        return None

    @adjusted_value.setter
    def adjusted_value(self, value):
        self._adjusted_value = value

    @adjusted_value.expression
    def adjusted_value(cls):
        from sqlalchemy.sql.functions import coalesce
        from sqlalchemy.sql import case

        # If value_currency is present, consider shipping and taxes. Otherwise, just primary_value.
        # This SQL expression might become complex depending on how strictly we define "monetary".
        # For simplicity, if value_currency is not NULL, we assume it's monetary and add costs.
        # A more robust way might involve checking value_currency against a list of known currency codes.
        return case(
            (cls.value_currency != None, cls.primary_value + coalesce(cls.shipping_cost, 0) + coalesce(cls.taxes, 0)),
            else_ = cls.primary_value
        )


class Recommendation(Base):
    __tablename__ = "recommendations"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    item_id = Column(GUID, ForeignKey("items.id"), nullable=False, index=True)
    address_id = Column(GUID, ForeignKey("addresses.id"), nullable=True, index=True) # Optional address link

    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    # RecommendationAction is an Enum in Pydantic, store as string here.
    predicted_action = Column(String, nullable=False) # e.g., "BUY", "WAIT", "HOLD"
    accuracy_rank = Column(Float, nullable=False)
    certainty_rank = Column(Float, nullable=False)
    reasoning = Column(Text, nullable=True)

    item = relationship("Item", back_populates="recommendations")
    address = relationship("Address", back_populates="recommendations")


if __name__ == "__main__":
    # This section is for illustration and won't run when imported.
    # To initialize the database, run db_setup.py directly or call init_db() from your app.
    print("SQLAlchemy models defined.")
    print("To create these tables in the database, run price_tracker_app/database/db_setup.py")
    # Example:
    # from .db_setup import init_db
    # init_db()
    # print("Database tables should be created now.")
