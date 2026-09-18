"""
Single factory function for obtaining the chat model used by every agent.

Switching LLM_PROVIDER in the environment (openai | anthropic | groq) changes
the reasoning engine for the entire graph without touching any agent/node
code — every agent only ever calls get_llm().
"""
from functools import lru_cache

from app.core.config import get_settings

settings = get_settings()


@lru_cache
def get_llm(temperature: float = 0.2):
    provider = settings.LLM_PROVIDER.lower()

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=settings.LLM_MODEL or "claude-3-5-sonnet-latest",
            api_key=settings.LLM_API_KEY,
            temperature=temperature,
        )

    if provider == "groq":
        # Groq hosts open models (Llama, etc.) behind a very fast,
        # OpenAI-compatible API. langchain-groq is a thin dedicated wrapper
        # around it (equivalent to pointing ChatOpenAI at Groq's base_url,
        # but with Groq's own request/response quirks handled for us).
        from langchain_groq import ChatGroq

        return ChatGroq(
            model=settings.LLM_MODEL or "llama-3.3-70b-versatile",
            api_key=settings.LLM_API_KEY,
            temperature=temperature,
        )

    # default: openai (also covers any OpenAI-compatible endpoint)
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=settings.LLM_MODEL or "gpt-4o-mini",
        api_key=settings.LLM_API_KEY,
        temperature=temperature,
    )
