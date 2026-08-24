from __future__ import annotations

# pyright: reportMissingTypeStubs=false
import json
import logging
import os
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Literal

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError

from open_mechanic.ai.prompts import DIAGNOSTIC_SYSTEM_PROMPT, format_diagnostic_prompt
from open_mechanic.db.models import VehicleProfile
from open_mechanic.dtc import DTCCode

_ = load_dotenv()

logger = logging.getLogger(__name__)

DISCLAIMER = (
    "This diagnosis is informational only and does not constitute professional "
    "mechanical advice. Consult a qualified mechanic before making safety-critical repairs."
)

DiagnosisSeverity = Literal["info", "warning", "critical", "do_not_drive"]
DiyDifficulty = Literal["easy", "moderate", "hard", "professional_only"]
Urgency = Literal["immediate", "soon", "next_service", "monitor"]


class EstimatedCostUsd(BaseModel):
    """US-dollar cost band returned by the diagnostic model."""

    low: int = Field(ge=0)
    high: int = Field(ge=0)


class DiagnosisAIOutput(BaseModel):
    """Structured Claude diagnosis payload (disclaimer is injected by the engine)."""

    severity: DiagnosisSeverity
    summary: str
    likely_causes: list[str]
    repair_steps: list[str]
    estimated_cost_usd: EstimatedCostUsd
    diy_feasible: bool
    diy_difficulty: DiyDifficulty
    urgency: Urgency


class DiagnosticError(Exception):
    pass


@dataclass
class DiagnosisResult:
    severity: str
    summary: str
    likely_causes: list[str]
    repair_steps: list[str]
    estimated_cost_usd: dict[str, int]
    diy_feasible: bool
    diy_difficulty: str
    urgency: str
    disclaimer: str
    dtc_codes: list[str]
    vehicle_str: str
    timestamp: datetime
    cached: bool = False


def _fallback_result(*, dtc_codes: list[str], vehicle_str: str) -> DiagnosisResult:
    result = DiagnosisResult(
        severity="warning",
        summary="Diagnosis unavailable - could not parse AI response",
        likely_causes=[],
        repair_steps=[],
        estimated_cost_usd={"low": 0, "high": 0},
        diy_feasible=False,
        diy_difficulty="moderate",
        urgency="soon",
        disclaimer=DISCLAIMER,
        dtc_codes=dtc_codes,
        vehicle_str=vehicle_str,
        timestamp=datetime.now(),
    )
    result.disclaimer = DISCLAIMER
    return result


def _result_from_ai_output(
    output: DiagnosisAIOutput,
    *,
    dtc_codes: list[str],
    vehicle_str: str,
) -> DiagnosisResult:
    result = DiagnosisResult(
        severity=output.severity,
        summary=output.summary,
        likely_causes=list(output.likely_causes),
        repair_steps=list(output.repair_steps),
        estimated_cost_usd={
            "low": output.estimated_cost_usd.low,
            "high": output.estimated_cost_usd.high,
        },
        diy_feasible=output.diy_feasible,
        diy_difficulty=output.diy_difficulty,
        urgency=output.urgency,
        disclaimer=DISCLAIMER,
        dtc_codes=dtc_codes,
        vehicle_str=vehicle_str,
        timestamp=datetime.now(),
    )
    result.disclaimer = DISCLAIMER
    return result


class DiagnosticEngine:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        resolved_api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if resolved_api_key is None:
            msg = "ANTHROPIC_API_KEY is required to initialize DiagnosticEngine"
            raise ValueError(msg)

        self._model: str = model or os.getenv("ANTHROPIC_MODEL") or "claude-sonnet-4-5"
        self._client: anthropic.Anthropic = anthropic.Anthropic(api_key=resolved_api_key)
        self._cache: dict[str, tuple[DiagnosisResult, datetime]] = {}
        self._cache_ttl: float = 86400.0

    def _cache_key(self, dtc_codes: list[str], vehicle_str: str) -> str:
        return f"{vehicle_str}|{','.join(sorted(dtc_codes))}"

    def _diagnostic_cache_key(
        self,
        dtc_codes: list[str],
        vehicle_str: str,
        snapshot: dict[str, Any],
    ) -> str:
        snapshot_json = json.dumps(_normalize_for_cache(snapshot), sort_keys=True, default=str)
        return f"{self._cache_key(dtc_codes, vehicle_str)}|{snapshot_json}"

    def _is_cache_valid(self, key: str) -> bool:
        if key not in self._cache:
            return False
        _, cached_at = self._cache[key]
        return (datetime.now() - cached_at).total_seconds() < self._cache_ttl

    def diagnose(
        self,
        vehicle: VehicleProfile,
        dtcs: list[DTCCode],
        snapshot: dict[str, Any],
        *,
        bypass_cache: bool = False,
    ) -> DiagnosisResult:
        vehicle_str = f"{vehicle.year} {vehicle.make} {vehicle.model} ({vehicle.mileage:,} miles)"
        dtc_codes = [dtc.code for dtc in dtcs]

        key = self._diagnostic_cache_key(dtc_codes, vehicle_str, snapshot)
        if not bypass_cache and self._is_cache_valid(key):
            cached_result, _ = self._cache[key]
            return replace(cached_result, cached=True)

        user_message = format_diagnostic_prompt(vehicle, dtcs, snapshot)

        try:
            response = self._client.messages.parse(
                model=self._model,
                max_tokens=1024,
                system=DIAGNOSTIC_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
                output_format=DiagnosisAIOutput,
            )
            parsed = response.parsed_output
            if parsed is None:
                raise ValueError("Claude structured output was empty")

            result = _result_from_ai_output(
                parsed,
                dtc_codes=dtc_codes,
                vehicle_str=vehicle_str,
            )
            self._cache[key] = (result, datetime.now())
            return result
        except (ValidationError, TypeError, ValueError) as exc:
            logger.error("Failed to parse Claude structured diagnosis: %s", exc)
            fallback_result = _fallback_result(dtc_codes=dtc_codes, vehicle_str=vehicle_str)
            self._cache[key] = (fallback_result, datetime.now())
            return fallback_result
        except anthropic.APIError as exc:
            logger.error("Claude API error during diagnostic call: %s", exc)
            raise DiagnosticError(str(exc)) from exc


def _normalize_for_cache(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _normalize_for_cache(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_normalize_for_cache(item) for item in value]
    if hasattr(value, "supported") and hasattr(value, "value"):
        return {
            "supported": bool(value.supported),
            "value": str(value.value),
            "unit": getattr(value, "unit", None),
        }
    return value
