# Celery Guide for Price Tracker App

This guide explains how to run the Celery worker and Celery Beat scheduler for the Price Tracker application to enable background task processing and scheduled tracking.

## Prerequisites

1.  **Install Dependencies:**
    Make sure all project dependencies, including `celery` and `redis`, are installed:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Running Message Broker (Redis):**
    Celery requires a message broker to send and receive messages (tasks). This application is configured to use Redis by default.
    *   Ensure you have a Redis server installed and running.
    *   By default, the application expects Redis to be available at `redis://localhost:6379`.
    *   You can typically start a local Redis server (if installed via Homebrew on macOS, for example) with:
        ```bash
        redis-server
        ```
        Or follow instructions specific to your OS and Redis installation.
    *   The Redis host and port can be configured via environment variables `REDIS_HOST` and `REDIS_PORT` if needed (see `price_tracker_app/celery_app.py`).

## Running the Celery Worker

The Celery worker is responsible for executing the tasks, such as scraping individual product URLs.

To start a Celery worker, navigate to the project's root directory (the one containing the `price_tracker_app` package) and run:

```bash
celery -A price_tracker_app.celery_app worker -l INFO
```

Explanation of command options:
*   `-A price_tracker_app.celery_app`: Specifies the Celery application instance. `price_tracker_app.celery_app` points to the `app` object in `price_tracker_app/celery_app.py`.
*   `worker`: Command to start a worker process.
*   `-l INFO`: Sets the log level for the worker to INFO. You can use `DEBUG` for more verbose output. Other levels include `WARNING`, `ERROR`, `CRITICAL`.

You should see output indicating the worker has started, connected to the broker, and is ready to receive tasks (it will list the discovered tasks like `price_tracker_app.tasks.track_single_url_task`).

## Running Celery Beat (Scheduler)

Celery Beat is a scheduler. It's responsible for sending tasks at regular intervals based on the defined schedule (e.g., running the `schedule_all_items_tracking_task` every 4 hours).

To start Celery Beat, in a separate terminal, navigate to the project's root directory and run:

```bash
celery -A price_tracker_app.celery_app beat -l INFO --scheduler celery.beat:PersistentScheduler
```

Explanation of command options:
*   `-A price_tracker_app.celery_app`: Specifies the Celery application instance.
*   `beat`: Command to start the Beat scheduler.
*   `-l INFO`: Sets the log level.
*   `--scheduler celery.beat:PersistentScheduler`: (Optional but recommended for standalone Beat) Uses a persistent scheduler that stores the last run times in a local file (default: `celerybeat-schedule`). This helps Beat resume correctly after restarts. If you are using a setup like `django-celery-beat` in a Django project, the scheduler might be different (e.g., `django_celery_beat.schedulers:DatabaseScheduler`). For our current setup, the default persistent scheduler is fine.

You should see Beat start up and log when it sends scheduled tasks to the broker.

**Important:**
*   Both the Celery worker(s) and the Celery Beat service need to be running concurrently for scheduled tasks to be dispatched and executed.
*   The message broker (Redis) must be running and accessible *before* starting the worker or Beat.

## Monitoring and Logs

*   **Worker Logs:** The terminal where you started the Celery worker will show logs for task execution, including successes, failures, and any `logger` messages from within your tasks.
*   **Beat Logs:** The terminal for Celery Beat will show logs related to scheduling tasks (e.g., "Scheduler: Sending due task track-all-items-every-4-hours (...)").
*   **Task Results (Optional):** If tasks return values and you have a result backend configured (like Redis in our case), you can inspect task states and results programmatically or using tools like Flower (a web-based monitoring tool for Celery). For now, checking logs is the primary way.

## Triggering Tasks Manually (for Testing)

You can use the CLI commands to manually dispatch tasks to the worker:

*   To trigger the main scheduling task (which then dispatches individual URL tasks):
    ```bash
    python -m price_tracker_app.cli task trigger-track-all
    ```
*   To trigger tracking for a single URL:
    ```bash
    python -m price_tracker_app.cli task trigger-single-url --item-id <item_uuid> --shop-id <shop_uuid> --url <product_url>
    ```

This allows you to test the task execution flow without waiting for the Beat schedule. Remember, a Celery worker must be running to process these manually triggered tasks.
