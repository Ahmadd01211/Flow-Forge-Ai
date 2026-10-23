import httpx
import pytest
from fastapi import HTTPException

from app.providers import registry


@pytest.mark.parametrize(
    ("provider", "payload", "expected"),
    [
        ("openai", {"data": [{"id": "gpt-5-mini"}]}, "gpt-5-mini"),
        ("anthropic", {"data": [{"id": "claude-test"}]}, "claude-test"),
        (
            "gemini",
            {
                "models": [
                    {
                        "name": "models/gemini-test",
                        "supportedGenerationMethods": ["generateContent"],
                    }
                ]
            },
            "gemini-test",
        ),
        ("deepseek", {"data": [{"id": "deepseek-chat"}]}, "deepseek-chat"),
    ],
)
def test_provider_profiles_use_fixed_hosts_and_auth(monkeypatch, provider, payload, expected):
    seen = []

    def respond(request):
        seen.append(request)
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(respond)
    original = httpx.Client
    monkeypatch.setattr(registry.httpx, "Client", lambda **_kwargs: original(transport=transport))
    assert registry.verify_key(provider, "test-secret") == [expected]
    assert seen[0].url.host == httpx.URL(registry.PROVIDERS[provider][1]).host
    assert seen[0].headers.get(
        "x-api-key"
        if provider == "anthropic"
        else "x-goog-api-key"
        if provider == "gemini"
        else "authorization"
    )


def test_openrouter_verifies_key_before_listing_models(monkeypatch):
    seen = []

    def respond(request):
        seen.append(request.url.path)
        if request.url.path.endswith("/key"):
            return httpx.Response(401)
        return httpx.Response(200, json={"data": [{"id": "vendor/model"}]})

    original = httpx.Client
    monkeypatch.setattr(
        registry.httpx, "Client", lambda **_kwargs: original(transport=httpx.MockTransport(respond))
    )
    with pytest.raises(HTTPException) as error:
        registry.verify_key("openrouter", "invalid-secret")
    assert error.value.status_code == 422
    assert seen == ["/api/v1/key"]
