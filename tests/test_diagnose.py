from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from open_mechanic.ai import diagnose
from open_mechanic.ai.diagnose import (
    DISCLAIMER,
    DiagnosisAIOutput,
    DiagnosticEngine,
    EstimatedCostUsd,
)
from open_mechanic.db.models import VehicleProfile
from open_mechanic.dtc import DTCCode


@dataclass
class _ParsedResponse:
    parsed_output: DiagnosisAIOutput | None


class _FakeMessages:
    def __init__(self, responses: list[DiagnosisAIOutput | None | Exception]) -> None:
        self._responses = responses
        self.calls: list[dict[str, Any]] = []

    def parse(self, **kwargs: Any) -> _ParsedResponse:
        self.calls.append(kwargs)
        index = min(len(self.calls) - 1, len(self._responses) - 1)
        payload = self._responses[index]
        if isinstance(payload, Exception):
            raise payload
        return _ParsedResponse(parsed_output=payload)


class _FakeClient:
    def __init__(self, responses: list[DiagnosisAIOutput | None | Exception]) -> None:
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


def _diagnosis_output(summary: str) -> DiagnosisAIOutput:
    return DiagnosisAIOutput(
        severity="warning",
        summary=summary,
        likely_causes=["Cause A", "Cause B"],
        repair_steps=["Step A", "Step B"],
        estimated_cost_usd=EstimatedCostUsd(low=100, high=500),
        diy_feasible=False,
        diy_difficulty="moderate",
        urgency="soon",
    )


def _engine_with_responses(
    responses: list[DiagnosisAIOutput | None | Exception],
) -> tuple[DiagnosticEngine, _FakeClient]:
    engine = DiagnosticEngine(api_key="test-key")
    fake_client = _FakeClient(responses)
    engine._client = fake_client  # type: ignore[assignment]
    return engine, fake_client


def test_diagnose_cache_key_changes_when_sensor_snapshot_changes() -> None:
    engine, fake_client = _engine_with_responses(
        [_diagnosis_output("first"), _diagnosis_output("second")]
    )

    first = engine.diagnose(_vehicle(), _dtcs(), {"RPM": {"value": "750", "supported": True}})
    second = engine.diagnose(_vehicle(), _dtcs(), {"RPM": {"value": "2500", "supported": True}})

    assert first.summary == "first"
    assert second.summary == "second"
    assert second.cached is False
    assert len(fake_client.messages.calls) == 2


def test_diagnose_reuses_cache_for_same_complete_input() -> None:
    engine, fake_client = _engine_with_responses([_diagnosis_output("first")])

    first = engine.diagnose(_vehicle(), _dtcs(), {"RPM": {"value": "750", "supported": True}})
    second = engine.diagnose(_vehicle(), _dtcs(), {"RPM": {"value": "750", "supported": True}})

    assert first.cached is False
    assert second.cached is True
    assert second.summary == "first"
    assert len(fake_client.messages.calls) == 1


def test_diagnose_can_bypass_cache_for_same_complete_input() -> None:
    engine, fake_client = _engine_with_responses(
        [_diagnosis_output("first"), _diagnosis_output("second")]
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


def test_diagnose_uses_structured_output_format() -> None:
    engine, fake_client = _engine_with_responses([_diagnosis_output("structured")])

    result = engine.diagnose(_vehicle(), _dtcs(), {})

    assert result.summary == "structured"
    assert result.disclaimer == DISCLAIMER
    assert fake_client.messages.calls[0]["output_format"] is DiagnosisAIOutput


def test_diagnose_returns_disclaimer_fallback_when_parsed_output_missing() -> None:
    engine, _ = _engine_with_responses([None])

    result = engine.diagnose(_vehicle(), _dtcs(), {})

    assert result.summary == "Diagnosis unavailable - could not parse AI response"
    assert result.disclaimer == DISCLAIMER


def test_diagnose_returns_disclaimer_fallback_on_validation_error() -> None:
    engine, _ = _engine_with_responses(
        [ValidationError.from_exception_data("DiagnosisAIOutput", [])]
    )

    result = engine.diagnose(_vehicle(), _dtcs(), {})

    assert result.summary == "Diagnosis unavailable - could not parse AI response"
    assert result.disclaimer == DISCLAIMER


def test_diagnosis_ai_output_rejects_invalid_severity() -> None:
    with pytest.raises(ValidationError):
        DiagnosisAIOutput(
            severity="mild",  # type: ignore[arg-type]
            summary="bad",
            likely_causes=["A", "B"],
            repair_steps=["A", "B"],
            estimated_cost_usd=EstimatedCostUsd(low=1, high=2),
            diy_feasible=False,
            diy_difficulty="moderate",
            urgency="soon",
        )


def test_diagnostic_engine_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        DiagnosticEngine()


def test_normalize_for_cache_handles_lists_and_sensor_values() -> None:
    sensor = SimpleSensor(value=750, unit="rpm", supported=True)

    assert diagnose._normalize_for_cache({"items": [sensor]}) == {
        "items": [{"supported": True, "value": "750", "unit": "rpm"}]
    }


def test_diagnose_wraps_anthropic_api_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeAPIError(Exception):
        pass

    class FailingMessages:
        def parse(self, **kwargs: Any) -> object:
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
