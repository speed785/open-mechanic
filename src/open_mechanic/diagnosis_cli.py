from __future__ import annotations

import json
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

from open_mechanic.ai.diagnose import DiagnosisResult, DiagnosticEngine, DiagnosticError
from open_mechanic.ai.providers import DiagnosticProvider, ProviderConfigurationError
from open_mechanic.connection import OBDConnection
from open_mechanic.db.models import VehicleProfile
from open_mechanic.dtc import DTCCode, DTCReader
from open_mechanic.enrichment import VehicleEnrichment, decode_vin
from open_mechanic.reader import SensorPoller, SensorValue

_SEVERITY_STYLES: dict[str, tuple[str, str]] = {
    "info": ("dim white", "INFO"),
    "warning": ("yellow", "WARNING"),
    "critical": ("red", "CRITICAL"),
    "do_not_drive": ("bold red", "DO NOT DRIVE"),
}

SENSOR_LABELS: dict[str, str] = {
    "RPM": "Engine RPM",
    "SPEED": "Vehicle Speed",
    "COOLANT_TEMP": "Coolant Temp",
    "INTAKE_TEMP": "Intake Air Temp",
    "MAF": "Mass Air Flow",
    "THROTTLE_POS": "Throttle Position",
    "SHORT_FUEL_TRIM_1": "Short Term Fuel Trim",
    "LONG_FUEL_TRIM_1": "Long Term Fuel Trim",
    "CONTROL_MODULE_VOLTAGE": "Module Voltage",
    "ENGINE_LOAD": "Engine Load",
}


def run_ai_diagnosis(
    args: Any,
    console: Console,
    provider: DiagnosticProvider | None = None,
) -> int:
    start_time = time.monotonic()
    parsed = parse_vehicle(str(args.vehicle), int(args.mileage), getattr(args, "vin", None))
    if parsed is None:
        console.print("[bold red]Invalid vehicle.[/bold red] Use --vehicle 'YEAR MAKE MODEL'.")
        return 1

    vehicle = parsed
    enrichment: VehicleEnrichment | None = None
    if vehicle.vin and not bool(getattr(args, "no_vin_decode", False)):
        enrichment = decode_vin(vehicle.vin)
        if enrichment.error is None:
            vehicle = apply_enrichment(vehicle, enrichment)

    console.print(_diagnosis_header(vehicle, enrichment))

    snapshot: dict[str, SensorValue] = {}
    dtcs: list[DTCCode] = []
    connected = False
    if bool(getattr(args, "offline", False)):
        console.print("[yellow]Offline mode[/yellow] [dim]Skipping adapter reads.[/dim]")
    else:
        connection = OBDConnection(
            port=getattr(args, "port", None),
            protocol=getattr(args, "protocol", None),
            baudrate=getattr(args, "baudrate", 115200),
            timeout=getattr(args, "timeout", 10.0),
            max_retries=1,
        )
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            _ = progress.add_task("Connecting to OBD adapter...", total=None)
            connected = connection.connect()
        if connected:
            raw_conn = connection.get_connection()
            protocol = raw_conn.protocol_name() if raw_conn is not None else "unknown"
            console.print(
                f"[green]Connected[/green] [dim]{protocol} on {connection.get_port()}[/dim]"
            )
            snapshot = SensorPoller(connection).get_snapshot()
            dtcs = DTCReader(connection).get_dtcs()
            connection.disconnect()
        else:
            console.print(
                "[yellow]No OBD adapter connection.[/yellow] [dim]Using profile/VIN context only.[/dim]"
            )

    _show_sensor_snapshot(console, snapshot)
    _show_dtcs(console, dtcs)

    prompt_snapshot: dict[str, Any] = dict(snapshot)
    if enrichment and enrichment.error is None:
        prompt_snapshot["VIN_DECODE"] = asdict(enrichment)

    try:
        engine = DiagnosticEngine(provider=provider, provider_name=getattr(args, "provider", None))
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            _ = progress.add_task("Running AI diagnosis...", total=None)
            result = engine.diagnose(vehicle, dtcs, prompt_snapshot)
    except (ProviderConfigurationError, ValueError) as exc:
        console.print(f"[bold red]AI provider is not configured:[/bold red] {exc}")
        return 1
    except DiagnosticError as exc:
        console.print(f"[bold red]AI diagnosis failed:[/bold red] {exc}")
        return 1

    _show_diagnosis(console, result)
    report_path = write_diagnosis_report(result, args, enrichment)
    console.print(f"[dim]Report: {report_path}[/dim]")
    console.print(f"[dim]Completed in {time.monotonic() - start_time:.2f}s[/dim]")
    return 0


def parse_vehicle(vehicle_text: str, mileage: int, vin: str | None) -> VehicleProfile | None:
    parts = vehicle_text.strip().split(maxsplit=2)
    if len(parts) < 3:
        return None
    try:
        year = int(parts[0])
    except ValueError:
        return None
    return VehicleProfile(year=year, make=parts[1], model=parts[2], mileage=mileage, vin=vin)


def apply_enrichment(vehicle: VehicleProfile, enrichment: VehicleEnrichment) -> VehicleProfile:
    return VehicleProfile(
        year=enrichment.year or vehicle.year,
        make=enrichment.make or vehicle.make,
        model=enrichment.model or vehicle.model,
        mileage=vehicle.mileage,
        vin=vehicle.vin,
    )


def write_diagnosis_report(
    result: DiagnosisResult,
    args: Any,
    enrichment: VehicleEnrichment | None,
) -> Path:
    report_dir = Path(getattr(args, "report_dir", None) or "local_data/sessions")
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = report_dir / f"{timestamp}-diagnosis.json"
    payload = {
        "severity": result.severity,
        "summary": result.summary,
        "likely_causes": result.likely_causes,
        "repair_steps": result.repair_steps,
        "estimated_cost_usd": result.estimated_cost_usd,
        "diy_feasible": result.diy_feasible,
        "diy_difficulty": result.diy_difficulty,
        "urgency": result.urgency,
        "disclaimer": result.disclaimer,
        "dtc_codes": result.dtc_codes,
        "vehicle": result.vehicle_str,
        "provider": result.provider,
        "cached": result.cached,
        "vin_enrichment": asdict(enrichment) if enrichment is not None else None,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _diagnosis_header(vehicle: VehicleProfile, enrichment: VehicleEnrichment | None) -> Panel:
    text = Text()
    text.append("open-mechanic / AI Diagnosis\n", style="bold cyan")
    text.append(f"{vehicle.year} {vehicle.make} {vehicle.model}  ")
    text.append(f"{vehicle.mileage:,} miles", style="dim")
    if vehicle.vin:
        text.append(f"\nVIN {vehicle.vin}", style="dim")
    if enrichment and enrichment.error is None:
        text.append("\nVIN enrichment: NHTSA vPIC", style="green")
    elif enrichment and enrichment.error:
        text.append("\nVIN enrichment unavailable", style="yellow")
    return Panel(text, border_style="cyan")


def _show_sensor_snapshot(console: Console, snapshot: dict[str, SensorValue]) -> None:
    table = Table(title="Sensor Snapshot", border_style="dim")
    table.add_column("Sensor", style="bold")
    table.add_column("Value", justify="right")
    table.add_column("Unit", style="dim")
    supported = {name: value for name, value in snapshot.items() if value.supported}
    if not supported:
        table.add_row("Sensors", "N/A", "offline or unsupported")
    else:
        for name, sensor in supported.items():
            table.add_row(SENSOR_LABELS.get(name, name), str(sensor.value), sensor.unit or "")
    console.print(table)


def _show_dtcs(console: Console, dtcs: list[DTCCode]) -> None:
    table = Table(title="Fault Codes", border_style="dim")
    table.add_column("Code", style="bold red")
    table.add_column("Severity")
    table.add_column("Description")
    if not dtcs:
        table.add_row("OK", "info", "No active fault codes available")
    else:
        for dtc in dtcs:
            table.add_row(dtc.code, dtc.severity, dtc.description)
    console.print(table)


def _show_diagnosis(console: Console, result: DiagnosisResult) -> None:
    style, label = _SEVERITY_STYLES.get(
        result.severity.lower(), ("yellow", result.severity.upper())
    )
    summary = Text()
    summary.append("Provider: ", style="bold")
    summary.append(result.provider)
    summary.append("\nSeverity: ", style="bold")
    summary.append(label, style=style)
    summary.append(f"\n{result.summary}")
    console.print(
        Panel(
            summary,
            title="AI Diagnosis",
            border_style="yellow" if "yellow" in style else "red" if "red" in style else "dim",
        )
    )

    if result.likely_causes:
        causes = Table(title="Likely Causes", show_header=False, border_style="dim")
        causes.add_column("Cause")
        for cause in result.likely_causes:
            causes.add_row(cause)
        console.print(causes)

    if result.repair_steps:
        steps = Table(title="Repair Steps", show_header=False, border_style="dim")
        steps.add_column("Step")
        for index, step in enumerate(result.repair_steps, 1):
            steps.add_row(f"{index}. {step}")
        console.print(steps)

    low = result.estimated_cost_usd.get("low", 0)
    high = result.estimated_cost_usd.get("high", 0)
    details = Table(title="Repair Context", show_header=False, border_style="blue")
    details.add_column("Field", style="bold dim")
    details.add_column("Value")
    details.add_row("Estimated cost", f"${low:,} - ${high:,}")
    details.add_row(
        "DIY feasible", f"{'yes' if result.diy_feasible else 'no'} ({result.diy_difficulty})"
    )
    details.add_row("Urgency", result.urgency)
    console.print(details)
    console.print(f"[yellow dim]{result.disclaimer}[/yellow dim]")
