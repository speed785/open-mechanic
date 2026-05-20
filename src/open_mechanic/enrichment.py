from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import quote
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class VehicleEnrichment:
    vin: str
    source: str
    year: int | None = None
    make: str | None = None
    model: str | None = None
    engine: str | None = None
    error: str | None = None


def decode_vin(vin: str, timeout: float = 5.0) -> VehicleEnrichment:
    normalized_vin = vin.strip().upper()
    if not normalized_vin:
        return VehicleEnrichment(vin=normalized_vin, source="nhtsa_vpic", error="VIN is empty")

    url = (
        "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/"
        f"{quote(normalized_vin)}?format=json"
    )
    try:
        request = Request(url, headers={"User-Agent": "open-mechanic/0.1"})
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return _parse_vpic_payload(normalized_vin, payload)
    except Exception as exc:
        return VehicleEnrichment(vin=normalized_vin, source="nhtsa_vpic", error=str(exc))


def _parse_vpic_payload(vin: str, payload: object) -> VehicleEnrichment:
    if not isinstance(payload, dict):
        return VehicleEnrichment(
            vin=vin, source="nhtsa_vpic", error="Unexpected VIN decode response"
        )
    results = payload.get("Results")
    if not isinstance(results, list) or not results:
        return VehicleEnrichment(vin=vin, source="nhtsa_vpic", error="No VIN decode results")

    first = results[0]
    if not isinstance(first, dict):
        return VehicleEnrichment(vin=vin, source="nhtsa_vpic", error="Unexpected VIN decode row")

    if "Variable" in first:
        values = {
            str(row.get("Variable")): str(row.get("Value") or "")
            for row in results
            if isinstance(row, dict)
        }
        year_text = values.get("Model Year") or values.get("ModelYear") or ""
        return VehicleEnrichment(
            vin=vin,
            source="nhtsa_vpic",
            year=_parse_int(year_text),
            make=_clean(values.get("Make")),
            model=_clean(values.get("Model")),
            engine=_clean(values.get("Engine Model") or values.get("Displacement (L)")),
        )

    return VehicleEnrichment(
        vin=vin,
        source="nhtsa_vpic",
        year=_parse_int(first.get("ModelYear")),
        make=_clean(first.get("Make")),
        model=_clean(first.get("Model")),
        engine=_clean(first.get("EngineModel") or first.get("DisplacementL")),
    )


def _clean(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _parse_int(value: object) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None
