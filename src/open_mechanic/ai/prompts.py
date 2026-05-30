"""Prompt templates for the Claude AI diagnostic engine.

This module is pure string formatting — no API calls, no imports of anthropic.
"""

from __future__ import annotations

from typing import Any

from open_mechanic.db.models import VehicleProfile
from open_mechanic.dtc import DTCCode
from open_mechanic.mode6 import MisfireSummary, Mode6TestResult

DIAGNOSTIC_SYSTEM_PROMPT: str = """\
You are an expert automotive technician with deep knowledge of OBD-II diagnostics, \
vehicle fault codes, and mechanical repair across all major makes and models.

You will be given vehicle information, active fault codes (DTCs), and live sensor data \
from an OBD-II scan. Your task is to analyze this data and return a diagnosis.

RESPONSE FORMAT:
You MUST respond with ONLY valid JSON — no markdown, no prose, no code fences. \
The JSON must conform exactly to this schema:

{
  "severity": "<info|warning|critical|do_not_drive>",
  "summary": "<one sentence plain-English summary of the diagnosis>",
  "likely_causes": ["<cause 1>", "<cause 2>"],
  "repair_steps": ["<step 1>", "<step 2>"],
  "estimated_cost_usd": {"low": <integer>, "high": <integer>},
  "diy_feasible": <true|false>,
  "diy_difficulty": "<easy|moderate|hard|professional_only>",
  "urgency": "<immediate|soon|next_service|monitor>",
  "disclaimer": "This diagnosis is informational only and does not constitute \
professional mechanical advice. Consult a qualified mechanic before making \
safety-critical repairs."
}

SEVERITY DEFINITIONS:
- info: No fault codes, all sensors nominal — routine check.
- warning: Issue present but vehicle is drivable; address within days to weeks.
- critical: Significant fault; continued driving risks further damage. Address soon.
- do_not_drive: Safety-critical fault; vehicle should not be driven until repaired.

URGENCY DEFINITIONS:
- immediate: Stop driving now; safety risk.
- soon: Address within 1–3 days.
- next_service: Address at next scheduled service.
- monitor: Keep an eye on it; no immediate action required.

RULES:
1. Always populate "disclaimer" with exactly: \
"This diagnosis is informational only and does not constitute professional mechanical \
advice. Consult a qualified mechanic before making safety-critical repairs."
2. Be conservative: when in doubt, escalate severity rather than downplay it.
3. Some sensors may show "N/A (unsupported)" — this means the vehicle does not \
expose that PID. Do not treat missing sensor data as a fault; simply work with \
what is available.
4. If multiple DTCs are present, consider their combined effect on severity.
5. Mode 6 monitor failures are pre-DTC evidence. Use them as supporting evidence,
especially for misfires, catalyst efficiency, oxygen sensors, fuel system, EVAP,
and EGR monitors. Do not treat absent Mode 6 data as a fault.
6. Provide at least two likely causes and at least two repair steps.
7. Cost estimates should reflect realistic US market labour + parts ranges.
"""


def format_sensor_snapshot(snapshot: dict[str, Any]) -> str:
    """Format a sensor snapshot dict into a human-readable multi-line string.

    Handles both :class:`~open_mechanic.reader.SensorValue` dataclass instances
    and plain dicts gracefully.

    Args:
        snapshot: Mapping of sensor name to :class:`SensorValue` or dict.

    Returns:
        A formatted string with one sensor per line, e.g.::

            RPM: 750 rpm
            SPEED: 0 km/h
            COOLANT_TEMP: 92 °C
            INTAKE_TEMP: N/A (unsupported)
    """
    if not snapshot:
        return "  (no sensor data available)"

    lines: list[str] = []
    for name, sensor in snapshot.items():
        if hasattr(sensor, "supported"):
            supported: bool = bool(sensor.supported)
            value: str = str(sensor.value)
            unit: str | None = sensor.unit
        elif isinstance(sensor, dict):
            supported = bool(sensor.get("supported", True))
            value = str(sensor.get("value", "N/A"))
            unit = sensor.get("unit")
        else:
            lines.append(f"  {name}: {sensor}")
            continue

        if not supported or value == "N/A":
            lines.append(f"  {name}: N/A (unsupported)")
        else:
            if unit:
                lines.append(f"  {name}: {value} {unit}")
            else:
                lines.append(f"  {name}: {value}")

    return "\n".join(lines)


def format_mode6_results(results: list[Mode6TestResult]) -> str:
    """Format Mode 6 monitor test results for AI diagnostic context."""
    if not results:
        return "  (no Mode 6 monitor data available)"

    failed = [result for result in results if result.passed is False]
    visible = failed if failed else results[:20]
    lines: list[str] = []
    for result in visible:
        unit = f" {result.unit}" if result.unit else ""
        lines.append(
            "  - "
            f"{result.monitor}: {result.test_name} [{result.status}] "
            f"value={result.value}{unit}, range={result.minimum}..{result.maximum}"
        )

    hidden_count = len(results) - len(visible)
    if hidden_count > 0:
        lines.append(f"  ({hidden_count} additional passed/unchanged Mode 6 tests omitted)")
    return "\n".join(lines)


def format_misfire_summary(summary: MisfireSummary | None) -> str:
    """Format distilled misfire evidence for AI diagnostic context."""
    if summary is None:
        return "  (no misfire analysis available)"

    lines = [f"  Status: {summary.status}", f"  Summary: {summary.summary}"]
    if not summary.findings:
        return "\n".join(lines)

    lines.append("  Findings:")
    for finding in summary.findings:
        cylinder = f" cylinder={finding.cylinder}" if finding.cylinder is not None else ""
        value = f" value={finding.value}" if finding.value is not None else ""
        threshold = f" threshold={finding.threshold}" if finding.threshold is not None else ""
        lines.append(
            f"  - {finding.source}/{finding.severity}:{cylinder}{value}{threshold} {finding.detail}"
        )
    return "\n".join(lines)


def format_diagnostic_prompt(
    vehicle: VehicleProfile,
    dtcs: list[DTCCode],
    snapshot: dict[str, Any],
    mode6_results: list[Mode6TestResult] | None = None,
    misfire_summary: MisfireSummary | None = None,
) -> str:
    """Build the user message to send to Claude for a diagnostic session.

    The system prompt is kept separate (:data:`DIAGNOSTIC_SYSTEM_PROMPT`).

    Args:
        vehicle: The :class:`~open_mechanic.db.models.VehicleProfile` for context.
        dtcs: List of active :class:`~open_mechanic.dtc.DTCCode` objects.
        snapshot: Sensor snapshot dict from
            :meth:`~open_mechanic.reader.SensorPoller.get_snapshot`.

    Returns:
        A formatted prompt string ready to send as the user message.
    """
    vin_line: str = f" | VIN: {vehicle.vin}" if vehicle.vin is not None else ""
    vehicle_line = (
        f"Vehicle: {vehicle.year} {vehicle.make} {vehicle.model}"
        f" ({vehicle.mileage:,} miles){vin_line}"
    )

    if dtcs:
        dtc_header = f"Fault Codes ({len(dtcs)}):"
        dtc_lines = "\n".join(
            f"  - {dtc.code}: {dtc.description} [{dtc.severity}, {dtc.category}]" for dtc in dtcs
        )
        fault_section = f"{dtc_header}\n{dtc_lines}"
    else:
        fault_section = "Fault Codes: None"

    sensor_section = f"Live Sensor Data:\n{format_sensor_snapshot(snapshot)}"
    mode6_section = f"Mode 6 Monitor Data:\n{format_mode6_results(mode6_results or [])}"
    misfire_section = f"Misfire Indicators:\n{format_misfire_summary(misfire_summary)}"

    return (
        f"{vehicle_line}\n\n"
        f"{fault_section}\n\n"
        f"{sensor_section}\n\n"
        f"{mode6_section}\n\n"
        f"{misfire_section}\n\n"
        "Please analyze this data and provide your diagnosis as JSON."
    )
