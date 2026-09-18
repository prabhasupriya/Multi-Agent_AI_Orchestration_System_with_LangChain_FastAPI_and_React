"""
Celery task wrappers.

These are the boundary that offloads potentially slow, I/O-heavy tool
work (HTTP calls to third-party APIs) onto Celery workers so the FastAPI
event loop - which is also responsible for keeping WebSocket connections
alive - never blocks on them.
"""
from app.core.celery_app import celery_app
from app.tools.logic import run_calculation, run_weather_lookup, run_web_search


@celery_app.task(name="tools.web_search", bind=True, max_retries=2)
def web_search_task(self, query: str, max_results: int = 3) -> str:
    try:
        return run_web_search(query=query, max_results=max_results)
    except Exception as exc:  # noqa: BLE001 - last-resort safety net
        return f"Error: web_search_task failed unexpectedly ({exc})."


@celery_app.task(name="tools.weather_lookup", bind=True, max_retries=2)
def weather_lookup_task(self, location: str, units: str = "metric") -> str:
    try:
        return run_weather_lookup(location=location, units=units)
    except Exception as exc:  # noqa: BLE001
        return f"Error: weather_lookup_task failed unexpectedly ({exc})."


@celery_app.task(name="tools.calculation", bind=True, max_retries=2)
def calculation_task(self, expression: str) -> str:
    try:
        return run_calculation(expression=expression)
    except Exception as exc:  # noqa: BLE001
        return f"Error: calculation_task failed unexpectedly ({exc})."
