from __future__ import annotations

# pyright: reportMissingTypeStubs=false
from datetime import datetime

from open_mechanic.ai.prompts import format_diagnostic_prompt, format_sensor_snapshot
from open_mechanic.db.models import VehicleProfile
from open_mechanic.dtc import DTCCode
from open_mechanic.reader import SensorValue


def test_format_sensor_snapshot_handles_empty_snapshot() -> None:
    assert format_sensor_snapshot({}) == "  (no sensor data available)"


def test_format_sensor_snapshot_formats_supported_and_unsupported_values() -> None:
    snapshot = {
        "RPM": SensorValue(
            name="RPM",
            value="750",
            unit="rpm",
            timestamp=datetime.now(),
            supported=True,
        ),
        "INTAKE_TEMP": {
            "value": "N/A",
            "unit": "°C",
            "supported": False,
        },
    }

    formatted = format_sensor_snapshot(snapshot)

    assert "  RPM: 750 rpm" in formatted
    assert "  INTAKE_TEMP: N/A (unsupported)" in formatted


def test_format_diagnostic_prompt_includes_vehicle_dtcs_and_sensors() -> None:
    vehicle = VehicleProfile(
        year=2018,
        make="Ford",
        model="F-150",
        mileage=85000,
        vin="1FTFW1E58JFC12345",
    )
    dtcs = [
        DTCCode(
            code="P0420",
            description="Catalyst system efficiency below threshold",
            status="confirmed",
            severity="warning",
            category="emissions",
        )
    ]
    snapshot = {
        "RPM": SensorValue(
            name="RPM",
            value="750",
            unit="rpm",
            timestamp=datetime.now(),
            supported=True,
        )
    }

    prompt = format_diagnostic_prompt(vehicle, dtcs, snapshot)

    assert "Vehicle: 2018 Ford F-150 (85,000 miles) | VIN: 1FTFW1E58JFC12345" in prompt
    assert "Fault Codes (1):" in prompt
    assert "  - P0420: Catalyst system efficiency below threshold [warning, emissions]" in prompt
    assert "Live Sensor Data:\n  RPM: 750 rpm" in prompt
    assert prompt.endswith("Please analyze this data and provide your diagnosis as JSON.")


def test_format_diagnostic_prompt_includes_vin_enrichment_context() -> None:
    vehicle = VehicleProfile(
        year=2018,
        make="Ford",
        model="F-150",
        mileage=85000,
        vin="1FTFW1E58JFC12345",
    )
    snapshot = {
        "VIN_DECODE": {
            "source": "nhtsa_vpic",
            "year": 2018,
            "make": "FORD",
            "model": "F-150",
            "engine": "3.5L GTDI",
            "error": None,
        }
    }

    prompt = format_diagnostic_prompt(vehicle, [], snapshot)

    assert "VIN Enrichment: NHTSA vPIC" in prompt
    assert "Engine: 3.5L GTDI" in prompt
    assert "VIN_DECODE: N/A (unsupported)" not in prompt
