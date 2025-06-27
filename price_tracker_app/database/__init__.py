# Makes 'database' a Python package
# Expose key elements for easier access from other parts of the application

from .db_setup import engine, SessionLocal, Base, init_db
from . import models as db_models # SQLAlchemy models
from price_tracker_app.core import models as core_models # Pydantic models
from . import crud

# Example:
# def get_db():
#     db = SessionLocal()
#     try:
#         yield db
#     finally:
#         db.close()

# init_db() # You might call this from your main application startup script
