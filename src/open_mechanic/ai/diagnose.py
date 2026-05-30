from __future__ import annotations

# pyright: reportMissingTypeStubs=false
import dataclasses
import json
import logging
import os
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

import anthropic
from dotenv import load_dotenv

from open_mechanic.ai.prompts import DIAGNOSTIC_SYSTEM_PROMPT, format_diagnostic_prompt
from open_mechanic.db.models import VehicleProfile
from open_mechanic.dtc import DTCCode
from open_mechanic.mode6 import MisfireSummary, Mode6TestResult

_ = load_dotenv()

logger = logging.getLogger(__name__)

DISCLAIMER = (
    "This diagnosis is informational only and does not constitute professional "
    "mechanical advice. Consult a qualified mechanic before making safety-critical repairs."
)


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


def _coerce_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _coerce_cost_range(value: Any) -> dict[str, int]:
    def _to_int(raw: Any) -> int:
        if isinstance(raw, bool):
            return 0
        if isinstance(raw, int):
            return raw
        if isinstance(raw, float):
            return int(raw)
        if isinstance(raw, str):
            try:
                return int(float(raw.strip()))
            except ValueError:
                return 0
        return 0

    if not isinstance(value, dict):
        return {"low": 0, "high": 0}

    low = _to_int(value.get("low", 0))
    high = _to_int(value.get("high", 0))
    return {"low": low, "high": high}


def _strip_markdown_code_fences(raw_text: str) -> str:
    cleaned_text = raw_text.strip()
    if cleaned_text.startswith("```json"):
        cleaned_text = cleaned_text[7:].lstrip()
    elif cleaned_text.startswith("```"):
        cleaned_text = cleaned_text[3:].lstrip()
    if cleaned_text.endswith("```"):
        cleaned_text = cleaned_text[:-3].rstrip()
    return cleaned_text


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
        diagnostic_context: dict[str, Any],
    ) -> str:
        snapshot_json = json.dumps(
            _normalize_for_cache(diagnostic_context), sort_keys=True, default=str
        )
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
        mode6_results: list[Mode6TestResult] | None = None,
        misfire_summary: MisfireSummary | None = None,
        bypass_cache: bool = False,
    ) -> DiagnosisResult:
        vehicle_str = f"{vehicle.year} {vehicle.make} {vehicle.model} ({vehicle.mileage:,} miles)"
        dtc_codes = [dtc.code for dtc in dtcs]
        diagnostic_context = {
            "snapshot": snapshot,
            "mode6_results": mode6_results or [],
            "misfire_summary": misfire_summary,
        }

        key = self._diagnostic_cache_key(dtc_codes, vehicle_str, diagnostic_context)
        if not bypass_cache and self._is_cache_valid(key):
            cached_result, _ = self._cache[key]
            return replace(cached_result, cached=True)

        user_message = format_diagnostic_prompt(
            vehicle,
            dtcs,
            snapshot,
            mode6_results=mode6_results,
            misfire_summary=misfire_summary,
        )

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                system=DIAGNOSTIC_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )

            raw_text_parts: list[str] = []
            for block in response.content:
                text = getattr(block, "text", None)
                if isinstance(text, str):
                    raw_text_parts.append(text)
            raw_text = "\n".join(raw_text_parts)
            cleaned_text = _strip_markdown_code_fences(raw_text)
            data = json.loads(cleaned_text)
            if not isinstance(data, dict):
                raise ValueError("AI response JSON must be an object")

            estimated_cost = _coerce_cost_range(data.get("estimated_cost_usd"))
            result = DiagnosisResult(
                severity=str(data.get("severity", "warning")),
                summary=str(data.get("summary", "Diagnosis unavailable")),
                likely_causes=_coerce_string_list(data.get("likely_causes")),
                repair_steps=_coerce_string_list(data.get("repair_steps")),
                estimated_cost_usd=estimated_cost,
                diy_feasible=bool(data.get("diy_feasible", False)),
                diy_difficulty=str(data.get("diy_difficulty", "moderate")),
                urgency=str(data.get("urgency", "soon")),
                disclaimer=DISCLAIMER,
                dtc_codes=dtc_codes,
                vehicle_str=vehicle_str,
                timestamp=datetime.now(),
            )
            result.disclaimer = DISCLAIMER
            self._cache[key] = (result, datetime.now())
            return result
        except (json.JSONDecodeError, ValueError) as exc:
            logger.error("Failed to parse Claude diagnostic JSON: %s", exc)
            fallback_result = DiagnosisResult(
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
            fallback_result.disclaimer = DISCLAIMER
            self._cache[key] = (fallback_result, datetime.now())
            return fallback_result
        except anthropic.APIError as exc:
            logger.error("Claude API error during diagnostic call: %s", exc)
            raise DiagnosticError(str(exc)) from exc


def _normalize_for_cache(value: Any) -> Any:
    if hasattr(value, "supported") and hasattr(value, "value"):
        return {
            "supported": bool(value.supported),
            "value": str(value.value),
            "unit": getattr(value, "unit", None),
        }
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _normalize_for_cache(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {str(key): _normalize_for_cache(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_normalize_for_cache(item) for item in value]
    return value
