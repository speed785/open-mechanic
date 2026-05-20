from __future__ import annotations

from datetime import datetime

from open_mechanic.ai.diagnose import DISCLAIMER, DiagnosticEngine
from open_mechanic.ai.providers import DiagnosticProvider
from open_mechanic.db.models import VehicleProfile


class FakeProvider(DiagnosticProvider):
    name = "fake"

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        return """
        {
          "severity": "critical",
          "summary": "Fuel trim is outside normal range.",
          "likely_causes": ["Vacuum leak", "Weak fuel pump"],
          "repair_steps": ["Smoke test intake", "Check fuel pressure"],
          "estimated_cost_usd": {"low": "120", "high": 700.8},
          "diy_feasible": true,
          "diy_difficulty": "moderate",
          "urgency": "soon",
          "disclaimer": "provider supplied text must not win"
        }
        """


def test_diagnostic_engine_uses_provider_and_injects_disclaimer() -> None:
    vehicle = VehicleProfile(
        year=2018,
        make="Ford",
        model="F-150",
        mileage=85000,
        vin=None,
        created_at=datetime.now(),
    )
    engine = DiagnosticEngine(provider=FakeProvider())

    result = engine.diagnose(vehicle, [], {})

    assert result.provider == "fake"
    assert result.summary == "Fuel trim is outside normal range."
    assert result.estimated_cost_usd == {"low": 120, "high": 700}
    assert result.disclaimer == DISCLAIMER


def test_diagnostic_engine_cache_preserves_provider_name() -> None:
    vehicle = VehicleProfile(
        year=2018,
        make="Ford",
        model="F-150",
        mileage=85000,
        vin=None,
        created_at=datetime.now(),
    )
    engine = DiagnosticEngine(provider=FakeProvider())

    _ = engine.diagnose(vehicle, [], {})
    cached = engine.diagnose(vehicle, [], {})

    assert cached.cached is True
    assert cached.provider == "fake"
