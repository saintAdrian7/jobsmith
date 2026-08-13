import httpx
import pytest

from pipeline.config import Config
from pipeline.llm import LLMError, get_provider

ANTHROPIC_BODY = {"content": [{"type": "text", "text": '{"score": 0.8}'}]}
OPENAI_BODY = {"choices": [{"message": {"content": "hello"}}]}


def make_config(tmp_path, provider, api_key_env="ANTHROPIC_API_KEY"):
    (tmp_path / "config.yaml").write_text("x: 1", encoding="utf-8")
    config = Config.load(tmp_path)
    config.data = {
        "llm": {
            "provider": provider,
            "model": "m",
            "api_key_env": api_key_env,
            "base_url": "https://api.example.com/v1",
            "max_tokens": 100,
        }
    }
    return config


def client_returning(status, body):
    def handler(request):
        return httpx.Response(status, json=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_anthropic_extracts_text_and_system_field(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    captured = {}

    def handler(request):
        import json

        captured.update(json.loads(request.content))
        assert request.headers["x-api-key"] == "k"
        return httpx.Response(200, json=ANTHROPIC_BODY)

    provider = get_provider(
        make_config(tmp_path, "anthropic"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    messages = [{"role": "system", "content": "be brief"}, {"role": "user", "content": "hi"}]
    assert provider.complete(messages) == '{"score": 0.8}'
    assert captured["system"] == "be brief"
    assert captured["messages"] == [{"role": "user", "content": "hi"}]


def test_json_mode_parses_and_strips_fences(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    body = {"content": [{"type": "text", "text": '```json\n{"a": 1}\n```'}]}
    provider = get_provider(make_config(tmp_path, "anthropic"), client=client_returning(200, body))
    assert provider.complete([{"role": "user", "content": "x"}], json_mode=True) == {"a": 1}


def test_openai_compat_extracts_choice(tmp_path, monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    provider = get_provider(
        make_config(tmp_path, "openai_compat", api_key_env="MISTRAL_API_KEY"),
        client=client_returning(200, OPENAI_BODY),
    )
    assert provider.complete([{"role": "user", "content": "hi"}]) == "hello"


def test_server_error_retries_then_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr("time.sleep", lambda s: None)
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(500, json={})

    provider = get_provider(
        make_config(tmp_path, "anthropic"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(LLMError):
        provider.complete([{"role": "user", "content": "hi"}])
    assert len(calls) == 2


def test_unknown_provider_raises(tmp_path):
    with pytest.raises(LLMError, match="unknown"):
        get_provider(make_config(tmp_path, "unknown"))
