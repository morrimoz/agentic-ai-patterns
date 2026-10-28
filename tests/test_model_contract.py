import httpx
import pytest
from patterns.providers import HttpModel, HttpEmbeddings


def test_http_model_keeps_auth_out_of_prompt_and_returns_json_object(monkeypatch):
    monkeypatch.setenv("AI_BASE_URL", "http://127.0.0.1:9999/v1")
    monkeypatch.setenv("AI_MODEL", "local-model")
    monkeypatch.setenv("AI_API_KEY", "synthetic-test-credential")
    calls = []

    def post(url, **kwargs):
        calls.append(kwargs)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"steps":[]}'}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", post)
    assert HttpModel().complete("route", {"request": "Inspect invoice"}) == {"steps": []}
    assert "synthetic-test-credential" not in str(calls[0]["json"])
    assert calls[0]["timeout"] == 30


def test_invalid_http_output_and_embedding_fail_before_execution(monkeypatch):
    monkeypatch.setenv("AI_BASE_URL", "http://127.0.0.1:9999/v1")
    monkeypatch.setenv("AI_MODEL", "local-model")
    monkeypatch.setenv("AI_EMBEDDING_MODEL", "local-embedding")
    monkeypatch.setattr(
        httpx,
        "post",
        lambda url, **kwargs: httpx.Response(
            200, json={"choices": [{"message": {"content": "[]"}}]}, request=httpx.Request("POST", url)
        ),
    )
    with pytest.raises(ValueError):
        HttpModel().complete("route", {})
    monkeypatch.setattr(
        httpx,
        "post",
        lambda url, **kwargs: httpx.Response(
            200, json={"data": [{"embedding": [0, 0]}]}, request=httpx.Request("POST", url)
        ),
    )
    with pytest.raises(ValueError):
        HttpEmbeddings().embed("invoice")
