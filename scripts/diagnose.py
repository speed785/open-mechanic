#!/usr/bin/env python3
"""AI-powered OBD-II diagnostic runner.

Connects to the OBD-II adapter, reads live sensor data and fault codes,
runs the full AI diagnostic engine, and displays a rich formatted result.

Usage:
    python scripts/diagnose.py --vehicle "2018 Ford F-150" --mileage 85000
    python scripts/diagnose.py --vehicle "2018 Ford F-150" --mileage 85000 --protocol 6
    python scripts/diagnose.py --vehicle "2018 Ford F-150" --mileage 85000 --share-with-ai
"""

from __future__ import annotations

# pyright: reportMissingTypeStubs=false
import argparse
import logging
import sys
import time
from dataclasses import dataclass
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

from open_mechanic.ai.diagnose import DiagnosisResult, DiagnosticEngine, DiagnosticError
from open_mechanic.connection import OBDConnection
from open_mechanic.db.models import VehicleProfile
from open_mechanic.dtc import DTCCode, DTCReader
from open_mechanic.reader import SensorPoller, SensorValue


@dataclass
class _Args:
    vehicle: str
    mileage: int
    vin: str | None
    port: str | None
    protocol: str | None
    model: str | None
    share_with_ai: bool


logging.getLogger("obd").setLevel(logging.CRITICAL)
logging.getLogger("open_mechanic").setLevel(logging.CRITICAL)

VERSION = "0.1.0"

SENSOR_LABELS: dict[str, str] = {
    "RPM": "Engine RPM",
    "SPEED": "Vehicle Speed",
    "COOLANT_TEMP": "Coolant Temp",
    "INTAKE_TEMP": "Intake Air Temp",
    "MAF": "Mass Air Flow",
    "THROTTLE_POS": "Throttle Position",
    "O2_B1S1": "O2 Sensor B1S1",
    "O2_B1S2": "O2 Sensor B1S2",
    "SHORT_FUEL_TRIM_1": "Short Term Fuel Trim",
    "LONG_FUEL_TRIM_1": "Long Term Fuel Trim",
    "CONTROL_MODULE_VOLTAGE": "Module Voltage",
    "ENGINE_LOAD": "Engine Load",
    "TIMING_ADVANCE": "Timing Advance",
}

_SEVERITY_STYLES: dict[str, tuple[str, str]] = {
    "info": ("dim white", "ℹ INFO"),
    "warning": ("yellow", "⚠ WARNING"),
    "critical": ("red", "✗ CRITICAL"),
    "do_not_drive": ("bold red", "✗ DO NOT DRIVE"),
}


def _require_str(value: object, name: str) -> str:
    if isinstance(value, str):
        return value
    msg = f"Invalid argument type for {name}: expected str"
    raise TypeError(msg)


def _require_optional_str(value: object, name: str) -> str | None:
    if value is None or isinstance(value, str):
        return value
    msg = f"Invalid argument type for {name}: expected str | None"
    raise TypeError(msg)


def _require_int(value: object, name: str) -> int:
    if isinstance(value, bool):
        msg = f"Invalid argument type for {name}: expected int"
        raise TypeError(msg)
    if isinstance(value, int):
        return value
    msg = f"Invalid argument type for {name}: expected int"
    raise TypeError(msg)


def _require_bool(value: object, name: str) -> bool:
    if isinstance(value, bool):
        return value
    msg = f"Invalid argument type for {name}: expected bool"
    raise TypeError(msg)


def _parse_args() -> _Args:
    parser = argparse.ArgumentParser(
        prog="diagnose.py",
        description=(
            "open-mechanic — AI Diagnosis\n\n"
            "Connects to your OBD-II adapter, reads live sensor data and fault codes,\n"
            "then runs the full AI diagnostic engine and displays a formatted result."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _ = parser.add_argument(
        "--vehicle",
        metavar="DESCRIPTION",
        required=True,
        help='Vehicle description e.g. "2018 Ford F-150" (format: YEAR MAKE MODEL)',
    )
    _ = parser.add_argument(
        "--mileage",
        metavar="MILES",
        type=int,
        required=True,
        help="Current odometer reading in miles",
    )
    _ = parser.add_argument(
        "--vin",
        metavar="VIN",
        default=None,
        help="VIN number (optional)",
    )
    _ = parser.add_argument(
        "--port",
        metavar="PORT",
        default=None,
        help="OBD port override (default: from OBD_PORT env or auto-detect)",
    )
    _ = parser.add_argument(
        "--protocol",
        metavar="PROTOCOL",
        default=None,
        help=(
            "OBD protocol number (default: from OBD_PROTOCOL env). "
            "Use 6 for ISO 15765-4 CAN 11/500 (most 2008+ cars)."
        ),
    )
    _ = parser.add_argument(
        "--model",
        metavar="MODEL",
        default=None,
        help="AI model override (default: from ANTHROPIC_MODEL env)",
    )
    _ = parser.add_argument(
        "--share-with-ai",
        action="store_true",
        help="Authorize sharing vehicle details, DTCs, and sensor readings for this request",
    )
    parsed = vars(parser.parse_args())
    return _Args(
        vehicle=_require_str(parsed.get("vehicle"), "vehicle"),
        mileage=_require_int(parsed.get("mileage"), "mileage"),
        vin=_require_optional_str(parsed.get("vin"), "vin"),
        port=_require_optional_str(parsed.get("port"), "port"),
        protocol=_require_optional_str(parsed.get("protocol"), "protocol"),
        model=_require_optional_str(parsed.get("model"), "model"),
        share_with_ai=_require_bool(parsed.get("share_with_ai"), "share_with_ai"),
    )


def _parse_vehicle(vehicle_str: str, console: Console) -> tuple[int, str, str] | None:
    """Split 'YEAR MAKE MODEL' into (year, make, model).

    Returns None and prints an error message if parsing fails.
    """
    parts = vehicle_str.strip().split(maxsplit=2)
    if len(parts) < 3:
        message = (
            "[bold red]✗ Error:[/bold red] --vehicle must be 'YEAR MAKE MODEL', got: "
            + f"[yellow]{vehicle_str!r}[/yellow]\n"
            + '[dim]Example: --vehicle "2018 Ford F-150"[/dim]'
        )
        console.print(message)
        return None

    try:
        year = int(parts[0])
    except ValueError:
        message = (
            "[bold red]✗ Error:[/bold red] First part of --vehicle must be a year "
            + f"(number), got: [yellow]{parts[0]!r}[/yellow]\n"
            + '[dim]Example: --vehicle "2018 Ford F-150"[/dim]'
        )
        console.print(message)
        return None

    return year, parts[1], parts[2]


def _build_vehicle(
    year: int,
    make: str,
    model_name: str,
    mileage: int,
    vin: str | None,
) -> VehicleProfile:
    return VehicleProfile(year=year, make=make, model=model_name, mileage=mileage, vin=vin)


def _show_sensors(console: Console, snapshot: dict[str, SensorValue]) -> None:
    supported = {k: v for k, v in snapshot.items() if v.supported}
    if not supported:
        console.print("[dim]No supported sensors found[/dim]")
        return

    table = Table(
        title="Live Sensor Readings",
        show_header=True,
        header_style="bold magenta",
        border_style="dim",
    )
    table.add_column("Sensor", style="bold", no_wrap=True)
    table.add_column("Value", justify="right")
    table.add_column("Unit", style="dim")

    for name, sv in supported.items():
        label = SENSOR_LABELS.get(name, name)
        table.add_row(label, f"[green]{sv.value}[/green]", sv.unit or "")

    console.print(table)


def _show_dtcs(console: Console, dtcs: list[DTCCode]) -> None:
    if not dtcs:
        console.print("[bold green]✓ No fault codes[/bold green]")
        return

    table = Table(
        title="Fault Codes (DTCs)",
        show_header=True,
        header_style="bold red",
        border_style="dim",
    )
    table.add_column("Code", style="bold red", no_wrap=True)
    table.add_column("Status", style="dim")
    table.add_column("Severity", style="dim")
    table.add_column("Description")

    for dtc in dtcs:
        table.add_row(dtc.code, dtc.status, dtc.severity, dtc.description)

    console.print(table)


def _show_diagnosis(
    console: Console,
    result: DiagnosisResult,
    vehicle_str: str,
    mileage: int,
) -> None:
    severity = result.severity.lower()
    border_style, severity_label = _SEVERITY_STYLES.get(
        severity, ("yellow", f"⚠ {severity.upper()}")
    )

    # Derive a valid rich Panel border colour from the full style string
    if "red" in border_style:
        panel_border = "red"
    elif "yellow" in border_style:
        panel_border = "yellow"
    else:
        panel_border = "dim"

    header = Text()
    _ = header.append(f"Diagnosis: {vehicle_str} ({mileage:,} miles)\n", style="bold white")
    _ = header.append("Severity: ", style="bold")
    _ = header.append(severity_label, style=border_style)
    console.print(Panel(header, border_style=panel_border, padding=(0, 2)))
    console.print()

    console.print("[bold]Summary[/bold]")
    console.print(f"  {result.summary}")
    console.print()

    if result.likely_causes:
        console.print("[bold]Likely Causes[/bold]")
        for i, cause in enumerate(result.likely_causes, 1):
            console.print(f"  {i}. {cause}")
        console.print()

    if result.repair_steps:
        console.print("[bold]Repair Steps[/bold]")
        for i, step in enumerate(result.repair_steps, 1):
            console.print(f"  {i}. {step}")
        console.print()

    details = Table(show_header=False, box=None, padding=(0, 2))
    details.add_column("Key", style="bold dim", no_wrap=True, width=18)
    details.add_column("Value")

    low = result.estimated_cost_usd.get("low", 0)
    high = result.estimated_cost_usd.get("high", 0)
    diy_label = "Yes" if result.diy_feasible else "No"

    details.add_row("Estimated Cost", f"${low:,} – ${high:,}")
    details.add_row("DIY Feasible", f"{diy_label}  [dim]({result.diy_difficulty})[/dim]")
    details.add_row("Urgency", result.urgency.capitalize())

    console.print(details)
    console.print()
    console.print(f"[yellow dim]⚠ {result.disclaimer}[/yellow dim]")


def main() -> int:  # noqa: PLR0911
    args = _parse_args()
    console = Console()
    start_time = time.monotonic()

    # ── Header ──────────────────────────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header_text = Text()
    _ = header_text.append("open-mechanic", style="bold cyan")
    _ = header_text.append(" — AI Diagnosis\n", style="bold white")
    _ = header_text.append(f"Version {VERSION}  •  {timestamp}", style="dim")
    console.print(Panel(header_text, border_style="cyan", padding=(0, 2)))
    console.print()

    # ── Parse vehicle ────────────────────────────────────────────────────────
    parsed = _parse_vehicle(args.vehicle, console)
    if parsed is None:
        return 1
    year, make, model_name = parsed
    vehicle = _build_vehicle(year, make, model_name, args.mileage, args.vin)
    vehicle_str = f"{year} {make} {model_name}"

    if not args.share_with_ai:
        console.print(
            "[bold yellow]AI sharing not authorized.[/bold yellow] "
            "This command would share vehicle details, DTCs, and sensor readings. "
            "Re-run with [bold]--share-with-ai[/bold] to authorize this request."
        )
        return 1

    console.print(f"[bold]Vehicle[/bold]  {vehicle_str}  •  {args.mileage:,} miles")
    if args.vin:
        console.print(f"[bold]VIN[/bold]      [dim]{args.vin}[/dim]")
    console.print()

    # ── OBD connection ───────────────────────────────────────────────────────
    obd_connection = OBDConnection(port=args.port, protocol=args.protocol)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        _ = progress.add_task("Connecting to OBD adapter...", total=None)
        connected = obd_connection.connect()

    if connected:
        raw_conn = obd_connection.get_connection()
        protocol_name = raw_conn.protocol_name() if raw_conn is not None else "Unknown"
        console.print(
            f"[bold green]✓ Connected[/bold green]  [dim]{protocol_name}[/dim]  "
            + f"[dim]on {obd_connection.get_port()}[/dim]"
        )
    else:
        console.print(
            "[bold yellow]⚠ No OBD adapter found[/bold yellow]  "
            + "[dim]Running in offline mode — diagnosis based on vehicle info only[/dim]"
        )
    console.print()

    # ── Sensors and DTCs ─────────────────────────────────────────────────────
    snapshot: dict[str, object] = {}
    dtcs: list[DTCCode] = []

    if connected:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            _ = progress.add_task("Reading sensor data...", total=None)
            raw_snapshot = SensorPoller(obd_connection).get_snapshot()

        snapshot = {name: sensor for name, sensor in raw_snapshot.items()}
        _show_sensors(console, raw_snapshot)
        console.print()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            _ = progress.add_task("Reading fault codes...", total=None)
            dtcs = DTCReader(obd_connection).get_dtcs()

        _show_dtcs(console, dtcs)
        console.print()
    else:
        console.print("[dim]Skipping sensor reads and fault codes — no OBD connection[/dim]")
        console.print()

    # ── AI diagnosis ─────────────────────────────────────────────────────────
    try:
        engine = DiagnosticEngine(model=args.model or None)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            _ = progress.add_task("Analyzing with AI...", total=None)
            result = engine.diagnose(
                vehicle,
                dtcs,
                snapshot,
                external_sharing_authorized=args.share_with_ai,
            )

    except ValueError as exc:
        console.print(
            f"[bold red]✗ Configuration error:[/bold red] {exc}\n"
            + "[dim]Hint: Set ANTHROPIC_API_KEY in your .env file[/dim]"
        )
        return 1
    except DiagnosticError as exc:
        console.print(f"[bold red]✗ AI diagnosis failed:[/bold red] {exc}")
        return 1

    # ── Display result ────────────────────────────────────────────────────────
    _show_diagnosis(console, result, vehicle_str, args.mileage)

    # ── Footer ────────────────────────────────────────────────────────────────
    elapsed = time.monotonic() - start_time
    cached_note = "  [dim](cached)[/dim]" if result.cached else ""
    console.print(f"[dim]Completed in {elapsed:.2f}s{cached_note}[/dim]")

    if connected:
        obd_connection.disconnect()

    return 0


if __name__ == "__main__":
    sys.exit(main())
