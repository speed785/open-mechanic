from __future__ import annotations

import json
from collections.abc import Mapping
from urllib.error import URLError

from open_mechanic.enrichment import VehicleEnrichment, decode_vin


class FakeResponse:
    def __init__(self, payload: Mapping[str, object]) -> None:
        self._payload = payload

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def test_decode_vin_returns_vehicle_context(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    payload = {
        "Results": [
            {"Variable": "Model Year", "Value": "2018"},
            {"Variable": "Make", "Value": "FORD"},
            {"Variable": "Model", "Value": "F-150"},
            {"Variable": "Engine Model", "Value": "3.5L GTDI"},
        ]
    }

    def fake_urlopen(request: object, timeout: float) -> FakeResponse:
        return FakeResponse(payload)

    monkeypatch.setattr("open_mechanic.enrichment.urlopen", fake_urlopen)

    enrichment = decode_vin("1FTFW1E58JFC12345")

    assert enrichment == VehicleEnrichment(
        vin="1FTFW1E58JFC12345",
        source="nhtsa_vpic",
        year=2018,
        make="FORD",
        model="F-150",
        engine="3.5L GTDI",
        error=None,
    )


def test_decode_vin_failure_is_non_fatal(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def fake_urlopen(request: object, timeout: float) -> FakeResponse:
        raise URLError("offline")

    monkeypatch.setattr("open_mechanic.enrichment.urlopen", fake_urlopen)

    enrichment = decode_vin("1FTFW1E58JFC12345")

    assert enrichment.vin == "1FTFW1E58JFC12345"
    assert enrichment.source == "nhtsa_vpic"
    assert enrichment.error is not None
