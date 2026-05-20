from __future__ import annotations

import pytest

from open_mechanic.ai.providers import (
    AnthropicProvider,
    LocalOpenAIProvider,
    OllamaProvider,
    OpenAIProvider,
    ProviderConfigurationError,
    select_provider,
)


def test_auto_provider_prefers_openai_then_anthropic_then_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.1")
    monkeypatch.setenv("LOCAL_OPENAI_BASE_URL", "http://localhost:1234/v1")
    monkeypatch.setenv("LOCAL_OPENAI_MODEL", "local-model")

    provider = select_provider("auto")

    assert isinstance(provider, OpenAIProvider)


def test_auto_provider_falls_back_to_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")

    provider = select_provider("auto")

    assert isinstance(provider, AnthropicProvider)


def test_auto_provider_falls_back_to_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.1")

    provider = select_provider("auto")

    assert isinstance(provider, OllamaProvider)


def test_explicit_local_openai_requires_base_url_and_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LOCAL_OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("LOCAL_OPENAI_MODEL", raising=False)

    with pytest.raises(ProviderConfigurationError):
        _ = select_provider("openai_compatible")


def test_explicit_local_openai_uses_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_OPENAI_BASE_URL", "http://localhost:1234/v1")
    monkeypatch.setenv("LOCAL_OPENAI_MODEL", "local-model")

    provider = select_provider("openai_compatible")

    assert isinstance(provider, LocalOpenAIProvider)
    assert provider.name == "openai_compatible"
