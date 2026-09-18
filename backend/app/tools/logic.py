"""
The actual "hands" of the agents.

Every function here is deliberately defensive: network calls, missing API
keys, bad status codes, and malformed expressions are all caught and turned
into a descriptive error STRING rather than a raised exception. This lets
the calling agent see the failure as part of its context and decide how to
recover (retry, use a different tool, or tell the user), instead of the
whole Python process crashing.
"""
import simpleeval
import httpx

from app.core.config import get_settings

settings = get_settings()


def run_web_search(query: str, max_results: int = 3) -> str:
    """Search the web using the Brave Search API.

    Falls back to a clear, agent-readable error message if the API key is
    missing, the request fails, or the response is malformed - the agent
    can then decide to proceed without this data or adjust its plan.
    """
    if not settings.BRAVE_SEARCH_API_KEY:
        return (
            "Error: Web search is not configured (missing BRAVE_SEARCH_API_KEY). "
            "Suggest proceeding with general knowledge or asking the user for "
            "more specific details instead of live search results."
        )
    try:
        response = httpx.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": max_results},
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": settings.BRAVE_SEARCH_API_KEY,
            },
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
        results = data.get("web", {}).get("results", [])[:max_results]
        if not results:
            return f"No web results found for query: '{query}'."
        formatted = "\n".join(
            f"- {r.get('title', 'Untitled')}: {r.get('description', '')} ({r.get('url', '')})"
            for r in results
        )
        return f"Web search results for '{query}':\n{formatted}"
    except httpx.HTTPStatusError as exc:
        return (
            f"Error: The web search API returned HTTP {exc.response.status_code}. "
            "Suggest retrying with a simpler query or continuing without this data."
        )
    except httpx.RequestError:
        return (
            "Error: The web search API is currently unreachable (network error). "
            "Suggest continuing the plan without live search data."
        )
    except Exception as exc:  # noqa: BLE001 - deliberate catch-all boundary
        return f"Error: Unexpected failure while searching the web ({exc}). Suggest an alternative strategy."


def run_weather_lookup(location: str, units: str = "metric") -> str:
    """Fetch current weather conditions from the OpenWeatherMap API."""
    if not settings.OPENWEATHER_API_KEY:
        return (
            "Error: Weather lookup is not configured (missing OPENWEATHER_API_KEY). "
            "Suggest informing the user that live weather data is unavailable."
        )
    try:
        response = httpx.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={
                "q": location,
                "units": units,
                "appid": settings.OPENWEATHER_API_KEY,
            },
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
        desc = data["weather"][0]["description"]
        temp = data["main"]["temp"]
        feels_like = data["main"]["feels_like"]
        unit_symbol = "°C" if units == "metric" else "°F"
        return (
            f"Current weather in {location}: {desc}, {temp}{unit_symbol} "
            f"(feels like {feels_like}{unit_symbol})."
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return f"Error: Location '{location}' was not found by the weather API. Suggest asking the user to clarify the city name."
        return (
            f"Error: The weather API returned HTTP {exc.response.status_code}. "
            "Suggest retrying or informing the user weather data is temporarily unavailable."
        )
    except httpx.RequestError:
        return "Error: The weather API is currently unreachable. Suggest an alternative strategy."
    except (KeyError, IndexError):
        return "Error: The weather API returned an unexpected response format. Suggest retrying."
    except Exception as exc:  # noqa: BLE001
        return f"Error: Unexpected failure while fetching weather ({exc}). Suggest an alternative strategy."


_ALLOWED_FUNCTIONS = {
    "sum": sum,
    "min": min,
    "max": max,
    "round": round,
    "abs": abs,
    "len": len,
}


def run_calculation(expression: str) -> str:
    """Safely evaluate a math/data-analysis expression using simpleeval,
    which sandboxes evaluation (no arbitrary code execution like raw eval())."""
    try:
        evaluator = simpleeval.EvalWithCompoundTypes(functions=_ALLOWED_FUNCTIONS)
        result = evaluator.eval(expression)
        return f"Calculation result for '{expression}': {result}"
    except simpleeval.InvalidExpression as exc:
        return f"Error: Invalid expression '{expression}' ({exc}). Suggest rewriting the expression using only numbers and basic operators."
    except ZeroDivisionError:
        return f"Error: Division by zero in expression '{expression}'. Suggest checking the inputs."
    except Exception as exc:  # noqa: BLE001
        return f"Error: Could not evaluate expression '{expression}' ({exc}). Suggest simplifying it."
