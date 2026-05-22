from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from open_mechanic.ai import diagnose
from open_mechanic.ai.diagnose import DISCLAIMER, DiagnosticEngine
from open_mechanic.db.models import VehicleProfile
from open_mechanic.dtc import DTCCode


@dataclass
class _TextBlock:
    text: str


@dataclass
class _Response:
    content: list[_TextBlock]


class _FakeMessages:
    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> _Response:
        self.calls.append(kwargs)
        index = min(len(self.calls) - 1, len(self._responses) - 1)
        return _Response([_TextBlock(self._responses[index])])


class _FakeClient:
    def __init__(self, responses: list[str]) -> None:
        self.messages = _FakeMessages(responses)


def _vehicle() -> VehicleProfile:
    return VehicleProfile(
        year=2018,
        make="Ford",
        model="F-150",
        mileage=85000,
        vin=None,
    )


def _dtcs() -> list[DTCCode]:
    return [
        DTCCode(
            code="P0420",
            description="Catalyst system efficiency below threshold",
            status="confirmed",
            severity="warning",
            category="emissions",
        )
    ]


def _diagnosis_json(summary: str) -> str:
    return (
        "{"
        '"severity": "warning",'
        f'"summary": "{summary}",'
        '"likely_causes": ["Cause A", "Cause B"],'
        '"repair_steps": ["Step A", "Step B"],'
        '"estimated_cost_usd": {"low": 100, "high": 500},'
        '"diy_feasible": false,'
        '"diy_difficulty": "moderate",'
        '"urgency": "soon"'
        "}"
    )


def _engine_with_responses(responses: list[str]) -> tuple[DiagnosticEngine, _FakeClient]:
    engine = DiagnosticEngine(api_key="test-key")
    fake_client = _FakeClient(responses)
    engine._client = fake_client  # type: ignore[assignment]
    return engine, fake_client


def test_diagnose_cache_key_changes_when_sensor_snapshot_changes() -> None:
    engine, fake_client = _engine_with_responses(
        [_diagnosis_json("first"), _diagnosis_json("second")]
    )

    first = engine.diagnose(_vehicle(), _dtcs(), {"RPM": {"value": "750", "supported": True}})
    second = engine.diagnose(_vehicle(), _dtcs(), {"RPM": {"value": "2500", "supported": True}})

    assert first.summary == "first"
    assert second.summary == "second"
    assert second.cached is False
    assert len(fake_client.messages.calls) == 2


def test_diagnose_reuses_cache_for_same_complete_input() -> None:
    engine, fake_client = _engine_with_responses([_diagnosis_json("first")])

    first = engine.diagnose(_vehicle(), _dtcs(), {"RPM": {"value": "750", "supported": True}})
    second = engine.diagnose(_vehicle(), _dtcs(), {"RPM": {"value": "750", "supported": True}})

    assert first.cached is False
    assert second.cached is True
    assert second.summary == "first"
    assert len(fake_client.messages.calls) == 1


def test_diagnose_can_bypass_cache_for_same_complete_input() -> None:
    engine, fake_client = _engine_with_responses(
        [_diagnosis_json("first"), _diagnosis_json("second")]
    )

    first = engine.diagnose(_vehicle(), _dtcs(), {"RPM": {"value": "750", "supported": True}})
    second = engine.diagnose(
        _vehicle(),
        _dtcs(),
        {"RPM": {"value": "750", "supported": True}},
        bypass_cache=True,
    )

    assert first.summary == "first"
    assert second.summary == "second"
    assert second.cached is False
    assert len(fake_client.messages.calls) == 2


def test_diagnose_returns_disclaimer_fallback_for_non_object_json() -> None:
    engine, _ = _engine_with_responses(["[]"])

    result = engine.diagnose(_vehicle(), _dtcs(), {})

    assert result.summary == "Diagnosis unavailable - could not parse AI response"
    assert result.disclaimer == DISCLAIMER


@pytest.mark.parametrize(
    ("raw_json", "expected"),
    [
        (_diagnosis_json("plain"), "plain"),
        (f"```json\n{_diagnosis_json('fenced')}\n```", "fenced"),
    ],
)
def test_diagnose_parses_plain_and_fenced_json(raw_json: str, expected: str) -> None:
    engine, _ = _engine_with_responses([raw_json])

    result = engine.diagnose(_vehicle(), _dtcs(), {})

    assert result.summary == expected
    assert result.disclaimer == DISCLAIMER


def test_diagnose_coerces_bad_field_types_to_safe_defaults() -> None:
    engine, _ = _engine_with_responses(
        [
            "{"
            '"severity": "warning",'
            '"summary": "bad fields",'
            '"likely_causes": "not a list",'
            '"repair_steps": [1, "Step B"],'
            '"estimated_cost_usd": {"low": "99.9", "high": true},'
            '"diy_feasible": "",'
            '"diy_difficulty": null,'
            '"urgency": null'
            "}"
        ]
    )

    result = engine.diagnose(_vehicle(), _dtcs(), {})

    assert result.likely_causes == []
    assert result.repair_steps == ["Step B"]
    assert result.estimated_cost_usd == {"low": 99, "high": 0}
    assert result.diy_feasible is False
    assert result.disclaimer == DISCLAIMER


def test_diagnostic_engine_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        DiagnosticEngine()


def test_cost_range_defaults_for_non_dict_and_bad_strings() -> None:
    assert diagnose._coerce_cost_range(None) == {"low": 0, "high": 0}
    assert diagnose._coerce_cost_range({"low": 1.9, "high": object()}) == {
        "low": 1,
        "high": 0,
    }
    assert diagnose._coerce_cost_range({"low": "bad", "high": 2}) == {"low": 0, "high": 2}


def test_strip_markdown_code_fences_handles_generic_fence() -> None:
    assert diagnose._strip_markdown_code_fences("```\n{}\n```") == "{}"


def test_normalize_for_cache_handles_lists_and_sensor_values() -> None:
    sensor = SimpleSensor(value=750, unit="rpm", supported=True)

    assert diagnose._normalize_for_cache({"items": [sensor]}) == {
        "items": [{"supported": True, "value": "750", "unit": "rpm"}]
    }


def test_diagnose_wraps_anthropic_api_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeAPIError(Exception):
        pass

    class FailingMessages:
        def create(self, **kwargs: Any) -> object:
            raise FakeAPIError("api down")

    engine = DiagnosticEngine(api_key="test-key")
    engine._client = SimpleNamespace(messages=FailingMessages())  # type: ignore[assignment]
    monkeypatch.setattr(diagnose.anthropic, "APIError", FakeAPIError)

    with pytest.raises(diagnose.DiagnosticError, match="api down"):
        engine.diagnose(_vehicle(), _dtcs(), {})


@dataclass
class SimpleSensor:
    value: object
    unit: str | None
    supported: bool
