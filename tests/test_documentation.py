from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_readme_documents_supported_stellantis_path_and_privacy() -> None:
    readme = _read("README.md")

    assert "OBDLink EX" in readme
    assert "only required diagnostic hardware" in readme
    assert "2024 Jeep Wrangler JL 4xe" in readme
    assert "read-only" in readme
    assert "No diagnostic history is saved by default" in readme
    assert "passenger or qualified technician" in readme
    assert "explicit per-request authorization" in readme


def test_linux_setup_documents_fixed_and_bounded_stellantis_commands() -> None:
    setup = _read("docs/SETUP_LINUX.md")

    assert 'pip install -e ".[dev,api]"' in setup
    assert "OBDLink EX" in setup
    assert "2024 Jeep Wrangler JL 4xe" in setup
    assert "--protocol 6" in setup
    assert "--baudrate 115200" in setup
    assert "stellantis-scan" in setup
    assert "stellantis-live" in setup
    assert "--samples 3" in setup
    assert "--interval 1" in setup
    assert "passenger or qualified technician" in setup


def test_api_and_ai_docs_require_explicit_external_sharing() -> None:
    readme = _read("README.md")
    api = _read("docs/API.md")
    providers = _read("docs/AI_PROVIDERS.md")

    assert "external_sharing_authorized" in api
    assert "403" in api
    assert "not persisted" in api
    assert "explicit per-request authorization" in providers
    assert "--share-with-ai" in providers
    assert "not cached" in providers
    assert "Every CLI AI invocation requires `--share-with-ai`" in providers
    assert "exits before adapter or AI access" in providers
    assert "Every CLI AI invocation requires `--share-with-ai`" in readme
    assert "Interactive use confirms" not in readme
    assert "asks for confirmation" not in providers


def test_contributor_docs_preserve_safety_and_data_boundaries() -> None:
    agents = _read("AGENTS.md")
    future = _read("docs/FUTURE_DEVELOPMENT_PLAN.md")

    assert "OBDLink EX" in agents
    assert "No diagnostic history is saved by default" in agents
    assert "0x19" in agents
    assert "0x22" in agents
    assert "0x3E" in agents
    assert "AutoAuth" in agents
    assert "SGW bypass" in agents
    assert "synthetic" in agents
    assert "ephemeral" in future
    assert "provenance" in future
    assert "community_unverified" in future
