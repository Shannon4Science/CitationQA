"""
LLM shared configuration.

Centralizes the backend model name so search-based features and fallback
evaluation stay on the same GPT version by default.
"""

from typing import Dict, List

from backend.config import LLM_SETTINGS


DEFAULT_LLM_MODEL = LLM_SETTINGS["model"]
DEFAULT_API_KEY = LLM_SETTINGS["api_key"]
PRIMARY_BASE_URL = LLM_SETTINGS["primary_base_url"]
SECONDARY_BASE_URL = LLM_SETTINGS["secondary_base_url"]
DEFAULT_SEARCH_TIMEOUT = int(LLM_SETTINGS.get("search_timeout", 180))


def build_search_llm_config() -> Dict[str, str]:
    return {
        "base_url": PRIMARY_BASE_URL,
        "api_key": DEFAULT_API_KEY,
        "model": DEFAULT_LLM_MODEL,
    }


def build_llm_configs() -> List[Dict[str, str]]:
    return [
        {
            "name": "direct",
            "base_url": PRIMARY_BASE_URL,
            "api_key": DEFAULT_API_KEY,
            "model": DEFAULT_LLM_MODEL,
        },
        {
            "name": "gcp",
            "base_url": SECONDARY_BASE_URL,
            "api_key": DEFAULT_API_KEY,
            "model": DEFAULT_LLM_MODEL,
        },
    ]
