"""Fixed upstream destinations keep credential checks away from user-controlled URLs."""

import json
import re
import time
from typing import Literal
from urllib.parse import urlencode

import httpx

from app.core.errors import fail

Provider = Literal["openai", "openrouter", "anthropic", "gemini", "deepseek"]

PROVIDERS: dict[str, tuple[str, str]] = {
    "openai": ("OpenAI", "https://api.openai.com/v1/models"),
    "openrouter": ("OpenRouter", "https://openrouter.ai/api/v1/models"),
    "anthropic": ("Claude (Anthropic)", "https://api.anthropic.com/v1/models"),
    "gemini": (
        "Gemini (Google)",
        "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000",
    ),
    "deepseek": ("DeepSeek", "https://api.deepseek.com/models"),
}
MAX_RESPONSE_BYTES = 4_000_000
MAX_MODELS = 1000


def verify_key(provider: Provider, key: str) -> list[str]:
    """List provider models with a bounded, non-billable request."""
    headers = {"Accept": "application/json"}
    if provider == "anthropic":
        headers.update({"x-api-key": key, "anthropic-version": "2023-06-01"})
    elif provider == "gemini":
        headers["x-goog-api-key"] = key
    else:
        headers["Authorization"] = f"Bearer {key}"

    deadline = time.monotonic() + 15
    total_bytes = 0

    def fetch(client: httpx.Client, url: str) -> dict:
        nonlocal total_bytes
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            fail(503, "PROVIDER_UNAVAILABLE", "Provider verification timed out.")
        with client.stream("GET", url, headers=headers, timeout=min(10, remaining)) as response:
            if response.status_code in (401, 403):
                fail(422, "PROVIDER_CREDENTIAL_REJECTED", "The provider rejected this credential.")
            if response.status_code == 429:
                fail(503, "PROVIDER_RATE_LIMITED", "Provider verification is rate limited.")
            if response.status_code != 200:
                fail(503, "PROVIDER_UNAVAILABLE", "Provider verification is unavailable.")
            chunks = bytearray()
            for chunk in response.iter_bytes():
                chunks.extend(chunk)
                total_bytes += len(chunk)
                if total_bytes > MAX_RESPONSE_BYTES:
                    fail(503, "PROVIDER_RESPONSE_INVALID", "The provider response is too large.")
                if time.monotonic() > deadline:
                    fail(503, "PROVIDER_UNAVAILABLE", "Provider verification timed out.")
        payload = json.loads(chunks)
        if not isinstance(payload, dict):
            raise ValueError("Invalid provider response")
        return payload

    try:
        with httpx.Client(
            timeout=httpx.Timeout(10.0, connect=3.0), follow_redirects=False, trust_env=False
        ) as client:
            if provider == "openrouter":
                key_info = fetch(client, "https://openrouter.ai/api/v1/key")
                if not isinstance(key_info.get("data"), dict):
                    raise ValueError("Missing key information")
            models = []
            url = PROVIDERS[provider][1]
            cursors = set()
            for _ in range(10):
                payload = fetch(client, url)
                rows = payload.get("models" if provider == "gemini" else "data")
                if not isinstance(rows, list):
                    raise ValueError("Missing model list")
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    if provider == "gemini" and "generateContent" not in row.get(
                        "supportedGenerationMethods", []
                    ):
                        continue
                    model = row.get("name" if provider == "gemini" else "id")
                    if provider == "gemini" and isinstance(model, str):
                        model = model.removeprefix("models/")
                    if (
                        isinstance(model, str)
                        and re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._:/@+\-]{0,199}", model)
                        and model not in models
                    ):
                        models.append(model)
                    if len(models) > MAX_MODELS:
                        raise ValueError("Catalog exceeds model limit")
                cursor = (
                    payload.get("nextPageToken")
                    if provider == "gemini"
                    else payload.get("last_id")
                    if provider == "anthropic" and payload.get("has_more")
                    else None
                )
                if provider == "anthropic" and payload.get("has_more") and not cursor:
                    raise ValueError("Missing pagination cursor")
                if not cursor:
                    break
                if not isinstance(cursor, str) or len(cursor) > 512 or cursor in cursors:
                    raise ValueError("Invalid pagination cursor")
                cursors.add(cursor)
                # Build the next URL ourselves: never follow an upstream-supplied URL.
                url = (
                    PROVIDERS[provider][1].split("?")[0]
                    + "?"
                    + urlencode(
                        {"pageSize": 1000, "pageToken": cursor}
                        if provider == "gemini"
                        else {"limit": 100, "after_id": cursor}
                    )
                )
            else:
                raise ValueError("Catalog exceeds page limit")
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        fail(503, "PROVIDER_UNAVAILABLE", "Provider verification is unavailable.")
    if not models:
        fail(422, "MODEL_UNAVAILABLE", "The provider did not list a usable generation model.")
    return models
