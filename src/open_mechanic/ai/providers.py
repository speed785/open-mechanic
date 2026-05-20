from __future__ import annotations

# pyright: reportMissingTypeStubs=false
import json
import os
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import anthropic
from dotenv import load_dotenv

_ = load_dotenv()


class ProviderConfigurationError(ValueError):
    pass


class ProviderError(Exception):
    pass


class DiagnosticProvider(Protocol):
    name: str

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        """Return raw model text for a diagnostic prompt."""


def _require_env(name: str, provider: str) -> str:
    value = os.getenv(name)
    if not value:
        msg = f"{name} is required for AI provider '{provider}'"
        raise ProviderConfigurationError(msg)
    return value


@dataclass
class OpenAIProvider:
    api_key: str
    model: str
    base_url: str = "https://api.openai.com/v1"
    name: str = "openai"

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self.model,
            "instructions": system_prompt,
            "input": user_prompt,
            "text": {"format": {"type": "json_object"}},
            "max_output_tokens": 1024,
        }
        data = _post_json(
            f"{self.base_url.rstrip('/')}/responses",
            payload,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        text = data.get("output_text")
        if isinstance(text, str):
            return text
        parts: list[str] = []
        output = data.get("output")
        if not isinstance(output, list):
            return ""
        for item in output:
            if not isinstance(item, dict):
                continue
            content_blocks = item.get("content")
            if not isinstance(content_blocks, list):
                continue
            for content in content_blocks:
                if isinstance(content, dict):
                    content_text = content.get("text")
                    if isinstance(content_text, str):
                        parts.append(content_text)
        return "\n".join(parts)


@dataclass
class LocalOpenAIProvider(OpenAIProvider):
    name: str = "openai_compatible"


@dataclass
class OllamaProvider:
    base_url: str
    model: str
    name: str = "ollama"

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        data = _post_json(
            f"{self.base_url.rstrip('/')}/api/chat",
            {
                "model": self.model,
                "stream": False,
                "format": "json",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            },
        )
        message = data.get("message")
        if isinstance(message, dict):
            message_content = message.get("content")
            if isinstance(message_content, str):
                return message_content
        response = data.get("response")
        return response if isinstance(response, str) else ""


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, model: str) -> None:
        self._model = model
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw_text_parts: list[str] = []
        for block in response.content:
            text = getattr(block, "text", None)
            if isinstance(text, str):
                raw_text_parts.append(text)
        return "\n".join(raw_text_parts)


def select_provider(provider_name: str | None = None) -> DiagnosticProvider:
    requested = (provider_name or os.getenv("AI_PROVIDER") or "auto").strip().lower()
    if requested == "auto":
        return _select_auto_provider()
    if requested == "openai":
        return OpenAIProvider(
            api_key=_require_env("OPENAI_API_KEY", "openai"),
            model=os.getenv("OPENAI_MODEL") or "gpt-4o",
        )
    if requested == "anthropic":
        return AnthropicProvider(
            api_key=_require_env("ANTHROPIC_API_KEY", "anthropic"),
            model=os.getenv("ANTHROPIC_MODEL") or "claude-sonnet-4-5",
        )
    if requested == "ollama":
        return OllamaProvider(
            base_url=os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434",
            model=_require_env("OLLAMA_MODEL", "ollama"),
        )
    if requested == "openai_compatible":
        return LocalOpenAIProvider(
            api_key=os.getenv("LOCAL_OPENAI_API_KEY") or "local",
            model=_require_env("LOCAL_OPENAI_MODEL", "openai_compatible"),
            base_url=_require_env("LOCAL_OPENAI_BASE_URL", "openai_compatible"),
        )
    msg = f"Unsupported AI provider: {provider_name}"
    raise ProviderConfigurationError(msg)


def _select_auto_provider() -> DiagnosticProvider:
    if os.getenv("OPENAI_API_KEY"):
        return select_provider("openai")
    if os.getenv("ANTHROPIC_API_KEY"):
        return select_provider("anthropic")
    if os.getenv("OLLAMA_MODEL"):
        return select_provider("ollama")
    if os.getenv("LOCAL_OPENAI_BASE_URL") and os.getenv("LOCAL_OPENAI_MODEL"):
        return select_provider("openai_compatible")
    msg = (
        "No AI provider configured. Set OPENAI_API_KEY, ANTHROPIC_API_KEY, "
        "OLLAMA_MODEL, or LOCAL_OPENAI_BASE_URL + LOCAL_OPENAI_MODEL."
    )
    raise ProviderConfigurationError(msg)


def _post_json(
    url: str, payload: dict[str, object], headers: dict[str, str] | None = None
) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8")
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    request = Request(url, data=body, headers=request_headers, method="POST")
    try:
        with urlopen(request, timeout=60.0) as response:
            raw = response.read().decode("utf-8")
    except (HTTPError, URLError, TimeoutError) as exc:
        raise ProviderError(str(exc)) from exc
    data = json.loads(raw)
    return data if isinstance(data, dict) else {}
