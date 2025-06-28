import logging
import sys

# Define a custom formatter
LOG_FORMAT = "%(asctime)s - %(levelname)s - [%(name)s] - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Basic configuration
def setup_logging(level=logging.INFO):
    """
    Sets up basic logging configuration for the application.
    - Logs to console (stdout).
    - Uses a defined format for log messages.
    """
    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
        datefmt=DATE_FORMAT,
        handlers=[logging.StreamHandler(sys.stdout)] # Ensure logs go to stdout
    )
    # You can add file handlers here if needed:
    # file_handler = logging.FileHandler("app.log")
    # file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    # logging.getLogger().addHandler(file_handler)

    # Example: Set specific log levels for noisy libraries if necessary
    # logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    # logging.getLogger("requests.packages.urllib3").setLevel(logging.WARNING)

if __name__ == '__main__':
    # Example usage:
    setup_logging(level=logging.DEBUG) # Setup with DEBUG level for this example

    logger = logging.getLogger("my_app_main") # Get a logger for the current module
    logger.debug("This is a debug message.")
    logger.info("This is an info message.")
    logger.warning("This is a warning message.")
    logger.error("This is an error message.")

    sub_logger = logging.getLogger("my_app_main.sub_module")
    sub_logger.info("Info message from sub_module.")

    try:
        x = 1 / 0
    except ZeroDivisionError:
        logger.exception("An exception occurred!") # Logs error with traceback

    print("\nLogging setup complete. Check console for log messages.")
    print(f"Root logger level: {logging.getLogger().getEffectiveLevel()} (DEBUG=10, INFO=20)")
    print(f"Logger 'my_app_main' effective level: {logger.getEffectiveLevel()}")
    print(f"Logger 'sqlalchemy.engine' effective level: {logging.getLogger('sqlalchemy.engine').getEffectiveLevel()}")
