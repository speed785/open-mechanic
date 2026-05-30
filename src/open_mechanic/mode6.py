from __future__ import annotations

# pyright: reportMissingTypeStubs=false,reportUnknownMemberType=false,reportUnknownVariableType=false
import logging
import re
from dataclasses import dataclass
from typing import Any

import obd

from open_mechanic.connection import OBDConnection
from open_mechanic.dtc import DTCCode

logger = logging.getLogger(__name__)

_CYLINDER_MONITOR_RE = re.compile(r"CYLINDER_(\d+)")


@dataclass(frozen=True)
class Mode6TestResult:
    monitor: str
    monitor_description: str
    category: str
    test_id: int | None
    test_name: str
    description: str
    value: str
    minimum: str
    maximum: str
    unit: str | None
    passed: bool | None
    status: str


@dataclass(frozen=True)
class MisfireFinding:
    source: str
    severity: str
    detail: str
    cylinder: int | None = None
    value: str | None = None
    threshold: str | None = None


@dataclass(frozen=True)
class MisfireSummary:
    supported: bool
    status: str
    summary: str
    findings: list[MisfireFinding]


class Mode6Reader:
    """Read Mode 6 onboard monitor test results from an active OBD connection."""

    def __init__(self, connection: OBDConnection) -> None:
        self._connection = connection

    def get_results(self, *, only_misfire: bool = False) -> list[Mode6TestResult]:
        """Return supported Mode 6 monitor test results."""
        conn = self._connection.get_connection()
        if conn is None or not self._connection.is_connected():
            return []

        supported_commands: set[object] = getattr(conn, "supported_commands", set())
        results: list[Mode6TestResult] = []
        for command in _mode6_monitor_commands(only_misfire=only_misfire):
            if command not in supported_commands:
                continue
            results.extend(_query_mode6_monitor(conn, command))
        return results


def diagnose_misfires(
    mode6_results: list[Mode6TestResult],
    dtcs: list[DTCCode] | None = None,
    sensor_snapshot: dict[str, Any] | None = None,
) -> MisfireSummary:
    """Build a best-effort misfire summary from monitor tests, DTCs, and sensors."""
    findings: list[MisfireFinding] = []
    misfire_results = [result for result in mode6_results if result.category == "misfire"]

    for result in misfire_results:
        if result.passed is False:
            threshold = f"{result.minimum}..{result.maximum}"
            findings.append(
                MisfireFinding(
                    source="mode6",
                    severity="warning",
                    cylinder=_cylinder_from_monitor(result.monitor),
                    detail=f"{result.monitor_description} failed {result.test_name}",
                    value=result.value,
                    threshold=threshold,
                )
            )

    for dtc in dtcs or []:
        cylinder = _cylinder_from_dtc(dtc.code)
        if dtc.code == "P0300" or cylinder is not None:
            cylinder_text = (
                "random/multiple cylinders" if cylinder is None else f"cylinder {cylinder}"
            )
            findings.append(
                MisfireFinding(
                    source="dtc",
                    severity="critical" if dtc.status == "confirmed" else "warning",
                    cylinder=cylinder,
                    detail=f"{dtc.code} reports misfire on {cylinder_text}: {dtc.description}",
                )
            )

    findings.extend(_sensor_misfire_clues(sensor_snapshot or {}))
    return _summarize_misfires(misfire_results, findings)


def _query_mode6_monitor(conn: Any, command: object) -> list[Mode6TestResult]:
    try:
        response = conn.query(command)
    except Exception as exc:
        logger.warning("Failed querying Mode 6 command %s: %s", _command_name(command), exc)
        return [_empty_result(command, f"error: {exc}")]

    if response is None or response.is_null() or response.value is None:
        return [_empty_result(command, "no data")]

    tests = _monitor_tests(response.value)
    if not tests:
        return [_empty_result(command, "no tests")]

    return [_mode6_result_from_test(command, test) for test in tests]


def _mode6_monitor_commands(*, only_misfire: bool) -> list[object]:
    commands = getattr(obd, "commands", None)
    if commands is None:
        return []

    candidates: list[tuple[int, str, object]] = []
    for name in dir(commands):
        if not name.startswith("MONITOR_"):
            continue
        if only_misfire and "MISFIRE" not in name:
            continue
        command = getattr(commands, name)
        if getattr(command, "mode", None) != 6:
            continue
        pid = getattr(command, "pid", 999)
        sort_pid = pid if isinstance(pid, int) else 999
        candidates.append((sort_pid, name, command))

    return [command for _, _, command in sorted(candidates, key=lambda item: (item[0], item[1]))]


def _monitor_tests(value: object) -> list[object]:
    tests = getattr(value, "tests", None)
    if isinstance(tests, list):
        return tests
    if isinstance(value, list):
        return value
    return []


def _mode6_result_from_test(command: object, test: object) -> Mode6TestResult:
    value = getattr(test, "value", None)
    minimum = getattr(test, "min", None)
    maximum = getattr(test, "max", None)
    value_text, unit = _format_measurement(value)
    min_text, _ = _format_measurement(minimum)
    max_text, _ = _format_measurement(maximum)
    passed = getattr(test, "passed", None)
    if not isinstance(passed, bool):
        passed = _infer_passed(value, minimum, maximum)

    test_id = getattr(test, "tid", None)
    test_name = getattr(test, "name", None)
    description = getattr(test, "desc", None)
    resolved_test_name = (
        str(test_name)
        if test_name
        else f"TID ${test_id:02X}"
        if isinstance(test_id, int)
        else "Unknown test"
    )
    return Mode6TestResult(
        monitor=_command_name(command),
        monitor_description=_command_description(command),
        category=_category_from_monitor(_command_name(command)),
        test_id=test_id if isinstance(test_id, int) else None,
        test_name=resolved_test_name,
        description=str(description or resolved_test_name),
        value=value_text,
        minimum=min_text,
        maximum=max_text,
        unit=unit,
        passed=passed,
        status=_status_from_passed(passed),
    )


def _empty_result(command: object, status: str) -> Mode6TestResult:
    return Mode6TestResult(
        monitor=_command_name(command),
        monitor_description=_command_description(command),
        category=_category_from_monitor(_command_name(command)),
        test_id=None,
        test_name="No test result",
        description=status,
        value="N/A",
        minimum="N/A",
        maximum="N/A",
        unit=None,
        passed=None,
        status=status,
    )


def _format_measurement(value: object) -> tuple[str, str | None]:
    if value is None:
        return "N/A", None
    magnitude = getattr(value, "magnitude", value)
    unit_value = getattr(value, "units", None)
    value_text = f"{magnitude:.2f}" if isinstance(magnitude, float) else str(magnitude)
    unit = str(unit_value) if unit_value is not None else None
    return value_text, unit


def _infer_passed(value: object, minimum: object, maximum: object) -> bool | None:
    measured = _coerce_float(value)
    low = _coerce_float(minimum)
    high = _coerce_float(maximum)
    if measured is None or low is None or high is None:
        return None
    return low <= measured <= high


def _coerce_float(value: object) -> float | None:
    magnitude = getattr(value, "magnitude", value)
    if isinstance(magnitude, bool):
        return None
    if isinstance(magnitude, int | float):
        return float(magnitude)
    if isinstance(magnitude, str):
        try:
            return float(magnitude.strip())
        except ValueError:
            return None
    return None


def _status_from_passed(passed: bool | None) -> str:
    if passed is True:
        return "passed"
    if passed is False:
        return "failed"
    return "unknown"


def _command_name(command: object) -> str:
    name = getattr(command, "name", None)
    return str(name) if name else str(command)


def _command_description(command: object) -> str:
    description = getattr(command, "desc", None)
    return str(description) if description else _command_name(command)


def _category_from_monitor(name: str) -> str:
    if "MISFIRE" in name:
        return "misfire"
    if "O2" in name:
        return "oxygen_sensor"
    if "CATALYST" in name or "NOX" in name:
        return "catalyst"
    if "EVAP" in name or "PURGE" in name:
        return "evap"
    if "EGR" in name:
        return "egr"
    if "FUEL_SYSTEM" in name:
        return "fuel"
    if "BOOST" in name:
        return "boost"
    return "other"


def _cylinder_from_monitor(name: str) -> int | None:
    match = _CYLINDER_MONITOR_RE.search(name)
    if match is None:
        return None
    return int(match.group(1))


def _cylinder_from_dtc(code: str) -> int | None:
    normalized = code.strip().upper()
    if normalized in {"P0310", "P0311", "P0312"}:
        return int(normalized[-2:])
    if normalized.startswith("P030") and len(normalized) == 5 and normalized[-1].isdigit():
        cylinder = int(normalized[-1])
        return cylinder or None
    return None


def _sensor_misfire_clues(snapshot: dict[str, Any]) -> list[MisfireFinding]:
    findings: list[MisfireFinding] = []
    short_trim = _sensor_float(snapshot, "SHORT_FUEL_TRIM_1")
    long_trim = _sensor_float(snapshot, "LONG_FUEL_TRIM_1")
    if short_trim is not None and abs(short_trim) >= 15.0:
        findings.append(
            MisfireFinding(
                source="sensor",
                severity="warning",
                detail="Short-term fuel trim is high enough to support a misfire or air/fuel issue",
                value=f"{short_trim:.2f}",
                threshold="+/-15%",
            )
        )
    if long_trim is not None and abs(long_trim) >= 15.0:
        findings.append(
            MisfireFinding(
                source="sensor",
                severity="warning",
                detail="Long-term fuel trim is high enough to support a misfire or air/fuel issue",
                value=f"{long_trim:.2f}",
                threshold="+/-15%",
            )
        )
    return findings


def _sensor_float(snapshot: dict[str, Any], name: str) -> float | None:
    sensor = snapshot.get(name)
    if sensor is None:
        return None
    if hasattr(sensor, "supported") and not bool(sensor.supported):
        return None
    if hasattr(sensor, "value"):
        return _coerce_float(sensor.value)
    if isinstance(sensor, dict):
        if sensor.get("supported") is False:
            return None
        return _coerce_float(sensor.get("value"))
    return _coerce_float(sensor)


def _summarize_misfires(
    misfire_results: list[Mode6TestResult],
    findings: list[MisfireFinding],
) -> MisfireSummary:
    has_dtc = any(finding.source == "dtc" for finding in findings)
    has_mode6_failure = any(finding.source == "mode6" for finding in findings)
    if has_dtc:
        status = "confirmed_misfire"
        summary = "Misfire DTCs are present; prioritize ignition, fuel, and compression checks."
    elif has_mode6_failure:
        status = "possible_misfire"
        summary = "Mode 6 misfire monitor failures were reported before a confirmed DTC."
    elif findings:
        status = "watch"
        summary = "No misfire-specific failures were reported, but supporting sensor data warrants monitoring."
    elif misfire_results:
        status = "no_misfire_detected"
        summary = "Mode 6 misfire monitors did not report failed tests."
    else:
        status = "no_mode6_misfire_data"
        summary = "No Mode 6 misfire monitor data was reported by this vehicle."

    return MisfireSummary(
        supported=bool(misfire_results),
        status=status,
        summary=summary,
        findings=findings,
    )
