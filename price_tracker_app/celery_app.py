from celery import Celery
import os

# --- Configuration ---
# It's better to use environment variables for sensitive info or deployment-specific settings.
# For local development, we can use defaults.
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
CELERY_BROKER_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"
CELERY_RESULT_BACKEND = f"redis://{REDIS_HOST}:{REDIS_PORT}/1" # Using a different DB for results

# Define the Celery application instance
# The first argument is the name of the current module, important for Celery's auto-discovery.
# Using 'price_tracker_app' as the main package name.
app = Celery(
    "price_tracker_app", # Name of the project package
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=["price_tracker_app.tasks"]  # List of modules to import when the worker starts.
                                        # This is where our tasks will be defined.
)

# Optional Celery configuration
app.conf.update(
    task_serializer="json", # Using JSON for task serialization
    accept_content=["json"],  # Specify accepted content types
    result_serializer="json", # Using JSON for result serialization
    timezone="UTC", # It's good practice to use UTC
    enable_utc=True,
    # Optional: Configure a default task execution time limit
    # task_time_limit=300,  # 5 minutes
    # Optional: Configure a default task retry policy
    # task_acks_late = True, # if you want tasks to be acknowledged after completion/failure
    # worker_prefetch_multiplier = 1, # if tasks are long running
)

# --- Celery Beat Schedule (Periodic Tasks) ---
# This will be configured here or loaded from settings.
# We'll add the schedule for `schedule_all_items_tracking_task` later in this file
# once the task itself is defined.
from datetime import timedelta # Added for beat_schedule

# Example structure:
app.conf.beat_schedule = {
    'track-all-items-every-4-hours': {
        'task': 'price_tracker_app.tasks.schedule_all_items_tracking_task', # Task name as defined in tasks.py
        'schedule': timedelta(hours=4), # Run every 4 hours
        'args': (0.5,), # Example: pass 0.5 seconds as inter_task_delay_seconds
                       # Ensure the task signature matches if args are provided.
                       # schedule_all_items_tracking_task(self, inter_task_delay_seconds: float = 0.1)
                       # So, this (0.5,) is correct for that argument.
    },
    # For easier testing, you might want a shorter schedule:
    # 'track-all-items-every-60-seconds': {
    #     'task': 'price_tracker_app.tasks.schedule_all_items_tracking_task',
    #     'schedule': 60.0, # Run every 60 seconds (can be float or timedelta)
    #     'args': (0.1,)
    # },
}


if __name__ == "__main__":
    # This allows running celery directly using `python -m price_tracker_app.celery_app ...`
    # e.g., `python -m price_tracker_app.celery_app worker -l info`
    # However, the standard way is `celery -A price_tracker_app.celery_app worker ...`
    app.start()
