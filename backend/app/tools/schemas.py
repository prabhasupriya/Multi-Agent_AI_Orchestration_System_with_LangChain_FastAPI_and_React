"""
Strict Pydantic input schemas for every tool.

These docstrings and Field descriptions are not just documentation -
they are what get shown to the LLM so it knows how to call each tool
correctly. Being explicit here measurably reduces hallucinated /
malformed tool calls.
"""
from pydantic import BaseModel, Field


class WebSearchInput(BaseModel):
    """Search the public web for up-to-date information on a topic."""

    query: str = Field(
        description="The precise search query, e.g. 'population of Tokyo 2026'. "
        "Should be specific and not a full sentence question."
    )
    max_results: int = Field(
        default=3, ge=1, le=10, description="Maximum number of results to return."
    )


class WeatherSearchInput(BaseModel):
    """Get the current weather conditions for a specific location."""

    location: str = Field(
        description="The precise city and, if known, ISO country code required by "
        "the OpenWeather API, e.g. 'Tokyo,JP' or 'San Francisco,US'."
    )
    units: str = Field(
        default="metric",
        description="Temperature units to return: 'metric' (Celsius) or 'imperial' (Fahrenheit).",
    )


class CalculationInput(BaseModel):
    """Evaluate a mathematical or data-analysis expression and return the numeric result."""

    expression: str = Field(
        description="A valid arithmetic expression to evaluate, e.g. '(72 - 32) * 5 / 9' "
        "or 'sum([12, 45, 78]) / 3'. Only math operators and a small set of safe "
        "built-in functions (sum, min, max, round, abs, len) are supported."
    )
