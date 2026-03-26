"""
LLM shared configuration.

All functions read from LLM_SETTINGS dict at call time so that runtime
updates (env var overrides, frontend settings panel) are always reflected.
"""

from typing import Dict, List

from backend.config import LLM_SETTINGS


def get_search_timeout() -> int:
    return int(LLM_SETTINGS.get("search_timeout", 180))


def build_search_llm_config() -> Dict[str, str]:
    return {
        "base_url": LLM_SETTINGS["primary_base_url"],
        "api_key": LLM_SETTINGS["api_key"],
        "model": LLM_SETTINGS["model"],
    }


def build_llm_configs() -> List[Dict[str, str]]:
    return [
        {
            "name": "direct",
            "base_url": LLM_SETTINGS["primary_base_url"],
            "api_key": LLM_SETTINGS["api_key"],
            "model": LLM_SETTINGS["model"],
        },
        {
            "name": "gcp",
            "base_url": LLM_SETTINGS["secondary_base_url"],
            "api_key": LLM_SETTINGS["api_key"],
            "model": LLM_SETTINGS["model"],
        },
    ]
