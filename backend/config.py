"""
Centralized backend configuration.

API keys are left empty by default.
Configure them via the frontend settings panel or edit this file directly.
"""

APP_SETTINGS = {
    "port": 5000,
    "concurrency_limit": 10,
}

PROXY_SETTINGS = {
    "fallback_proxy": "",
}

LLM_SETTINGS = {
    "model": "gpt-4o",
    "api_key": "",
    "primary_base_url": "https://api.openai.com/v1",
    "secondary_base_url": "",
    "search_timeout": 180,
}

SERPAPI_SETTINGS = {
    "api_key": "",
    "base_url": "https://serpapi.com/search",
}

ADSABS_SETTINGS = {
    "api_key": "",
    "base_url": "https://api.adsabs.harvard.edu/v1",
}

SEMANTIC_SCHOLAR_SETTINGS = {
    "api_key": "",
    "base_url": "https://api.semanticscholar.org/graph/v1",
}

MINERU_SETTINGS = {
    "api_token": "",
    "base_url": "https://mineru.net/api/v4",
}

IMAGE_TEST_SETTINGS = {
    "model": "gpt-image-1",
}
