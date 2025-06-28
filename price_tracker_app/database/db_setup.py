from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Define the database URL. For SQLite, it's a file path.
# This will create a file named `price_tracker.db` in the project's root directory.
# For a real application, you might want this path to be configurable.
DATABASE_URL = "sqlite:///./price_tracker.db"

# Create the SQLAlchemy engine
# `connect_args` is needed only for SQLite to support single-threaded access for simplicity in some cases,
# especially if using it with web frameworks that might handle threading differently.
# For general use, it's good practice for SQLite.
engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)

# Create a SessionLocal class, which will be used to create database sessions
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create a Base class for declarative class definitions
# Our SQLAlchemy models will inherit from this class.
Base = declarative_base()

def init_db():
    """
    Initializes the database by creating all tables defined by models
    that inherit from `Base`. This function should be called once at
    application startup.
    """
    # Import all modules here that define models so that
    # they are registered properly on the metadata. Otherwise
    # you will have to import them first before calling init_db()
    from . import models # noqa
    logger.info(f"Initializing database at {DATABASE_URL}...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created (if they didn't exist).")

if __name__ == "__main__":
    # This script can be run directly to initialize the database.
    # Setup basic logging if run directly
    from price_tracker_app.logging_config import setup_logging
    setup_logging(logging.INFO)
    logger.info("Running db_setup directly to initialize database...")
    init_db()
    logger.info("Database initialization process finished.")

    # You can add a small test here to verify session creation
    try:
        db = SessionLocal()
        logger.info("Database session created successfully.")
        # Perform a simple query
        # Using text() for SQLAlchemy 2.0 compatibility if it were a more complex query
        from sqlalchemy import text
        result = db.execute(text("SELECT 1")).scalar_one()
        logger.info(f"Test query result: {result}")
        db.close()
        logger.info("Database session closed.")
    except Exception as e:
        logger.exception(f"Error during database session test:")
