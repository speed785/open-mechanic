from __future__ import annotations

# pyright: reportMissingTypeStubs=false
from datetime import datetime

from open_mechanic.ai.prompts import (
    format_diagnostic_prompt,
    format_misfire_summary,
    format_mode6_results,
    format_sensor_snapshot,
)
from open_mechanic.db.models import VehicleProfile
from open_mechanic.dtc import DTCCode
from open_mechanic.mode6 import MisfireFinding, MisfireSummary, Mode6TestResult
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


def test_format_sensor_snapshot_handles_plain_values() -> None:
    formatted = format_sensor_snapshot({"RAW": 42})

    assert formatted == "  RAW: 42"


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
    mode6_results = [
        Mode6TestResult(
            monitor="MONITOR_MISFIRE_CYLINDER_1",
            monitor_description="Misfire Cylinder 1 Data",
            category="misfire",
            test_id=1,
            test_name="Misfire counts",
            description="Misfire counts",
            value="12",
            minimum="0",
            maximum="5",
            unit="count",
            passed=False,
            status="failed",
        )
    ]
    misfire_summary = MisfireSummary(
        supported=True,
        status="possible_misfire",
        summary="Mode 6 misfire monitor failures were reported before a confirmed DTC.",
        findings=[
            MisfireFinding(
                source="mode6",
                severity="warning",
                detail="Cylinder 1 misfire counts failed",
                cylinder=1,
                value="12",
                threshold="0..5",
            )
        ],
    )

    prompt = format_diagnostic_prompt(vehicle, dtcs, snapshot, mode6_results, misfire_summary)

    assert "Vehicle: 2018 Ford F-150 (85,000 miles) | VIN: 1FTFW1E58JFC12345" in prompt
    assert "Fault Codes (1):" in prompt
    assert "  - P0420: Catalyst system efficiency below threshold [warning, emissions]" in prompt
    assert "Live Sensor Data:\n  RPM: 750 rpm" in prompt
    assert "Mode 6 Monitor Data:\n  - MONITOR_MISFIRE_CYLINDER_1" in prompt
    assert "Misfire Indicators:\n  Status: possible_misfire" in prompt
    assert prompt.endswith("Please analyze this data and provide your diagnosis as JSON.")


def test_format_diagnostic_prompt_handles_no_dtcs_and_no_vin() -> None:
    vehicle = VehicleProfile(
        year=2018,
        make="Ford",
        model="F-150",
        mileage=85000,
        vin=None,
    )

    prompt = format_diagnostic_prompt(vehicle, [], {})

    assert "VIN" not in prompt
    assert "Fault Codes: None" in prompt
    assert "  (no sensor data available)" in prompt


def test_format_mode6_results_limits_passed_results_and_prefers_failures() -> None:
    passed = [
        Mode6TestResult(
            monitor=f"MONITOR_O2_{index}",
            monitor_description="O2",
            category="oxygen_sensor",
            test_id=index,
            test_name="O2 test",
            description="O2 test",
            value="1",
            minimum="0",
            maximum="2",
            unit=None,
            passed=True,
            status="passed",
        )
        for index in range(21)
    ]
    failed = Mode6TestResult(
        monitor="MONITOR_CATALYST_B1",
        monitor_description="Catalyst",
        category="catalyst",
        test_id=1,
        test_name="Catalyst test",
        description="Catalyst test",
        value="3",
        minimum="0",
        maximum="2",
        unit=None,
        passed=False,
        status="failed",
    )

    assert format_mode6_results([]) == "  (no Mode 6 monitor data available)"
    assert "1 additional" in format_mode6_results(passed)
    formatted = format_mode6_results([*passed, failed])
    assert "MONITOR_CATALYST_B1" in formatted
    assert "MONITOR_O2_0" not in formatted


def test_format_misfire_summary_handles_missing_and_empty_findings() -> None:
    assert format_misfire_summary(None) == "  (no misfire analysis available)"

    summary = MisfireSummary(
        supported=True,
        status="no_misfire_detected",
        summary="Mode 6 misfire monitors did not report failed tests.",
        findings=[],
    )

    formatted = format_misfire_summary(summary)

    assert "Status: no_misfire_detected" in formatted
    assert "Findings" not in formatted
