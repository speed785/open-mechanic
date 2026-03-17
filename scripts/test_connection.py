"""Standalone OBD-II adapter test script.

Run this first to verify your adapter is detected and working.
Does NOT import from the open_mechanic package — fully self-contained.

Usage:
    python scripts/test_connection.py
    python scripts/test_connection.py --port /dev/ttyUSB0
    python scripts/test_connection.py --port COM3 --timeout 5
"""

from __future__ import annotations

# pyright: reportMissingTypeStubs=false
# pyright: reportAttributeAccessIssue=false
import argparse
import glob
import json
import logging
import platform
import sys
import time
from datetime import datetime
from pathlib import Path

import obd
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

logging.getLogger("obd").setLevel(logging.CRITICAL)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VERSION = "0.1.0"

SENSOR_COMMANDS = [
    "RPM",
    "SPEED",
    "COOLANT_TEMP",
    "INTAKE_TEMP",
    "MAF",
    "THROTTLE_POS",
    "ENGINE_LOAD",
    "CONTROL_MODULE_VOLTAGE",
]

SENSOR_LABELS: dict[str, str] = {
    "RPM": "Engine RPM",
    "SPEED": "Vehicle Speed",
    "COOLANT_TEMP": "Coolant Temp",
    "INTAKE_TEMP": "Intake Air Temp",
    "MAF": "Mass Air Flow",
    "THROTTLE_POS": "Throttle Position",
    "ENGINE_LOAD": "Engine Load",
    "CONTROL_MODULE_VOLTAGE": "Control Module Voltage",
}

# ---------------------------------------------------------------------------
# Port detection (mirrors connection.py — no package import)
# ---------------------------------------------------------------------------


def detect_ports() -> tuple[list[str], str]:
    """Return (available_ports, default_port) for the current OS."""
    system = platform.system()

    if system == "Linux":
        ports = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
        default = "/dev/ttyUSB0"
    elif system == "Darwin":
        ports = glob.glob("/dev/cu.usbserial-*") + glob.glob("/dev/tty.usbserial-*")
        default = ports[0] if ports else "/dev/cu.usbserial-0"
    elif system == "Windows":
        try:
            from serial.tools import list_ports  # type: ignore[import-untyped]

            ports = [p.device for p in list_ports.comports()]
        except ImportError:
            ports = []
        default = "COM3"
    else:
        ports = []
        default = "/dev/ttyUSB0"

    return sorted(ports), default


def port_pattern_for_os() -> str:
    system = platform.system()
    if system == "Linux":
        return "/dev/ttyUSB*, /dev/ttyACM*"
    if system == "Darwin":
        return "/dev/cu.usbserial-*, /dev/tty.usbserial-*"
    if system == "Windows":
        return "COM*"
    return "/dev/ttyUSB*"


# ---------------------------------------------------------------------------
# DTC lookup (inline — no package import)
# ---------------------------------------------------------------------------


def load_dtc_db() -> dict[str, dict[str, str]]:
    """Load data/dtc_codes.json relative to this script's parent directory."""
    dtc_path = Path(__file__).parent.parent / "data" / "dtc_codes.json"
    if not dtc_path.exists():
        return {}
    try:
        with dtc_path.open() as fh:
            entries: list[dict[str, str]] = json.load(fh)
        return {d["code"].upper(): d for d in entries}
    except (json.JSONDecodeError, KeyError):
        return {}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="test_connection.py",
        description=(
            "open-mechanic — OBD-II Adapter Test\n\n"
            "Verifies that your OBD-II USB adapter is detected and communicating.\n"
            "Run this before using open-mechanic to confirm your setup is working."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--port",
        metavar="PORT",
        default=None,
        help="Serial port to use (e.g. /dev/ttyUSB0, COM3). Auto-detected if omitted.",
    )
    parser.add_argument(
        "--timeout",
        metavar="SECONDS",
        type=float,
        default=10.0,
        help="Connection timeout in seconds (default: 10).",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    args = parse_args()
    console = Console()
    start_time = time.monotonic()

    # ── Header ──────────────────────────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header_text = Text()
    header_text.append("open-mechanic", style="bold cyan")
    header_text.append(" — OBD-II Adapter Test\n", style="bold white")
    header_text.append(f"Version {VERSION}  •  {timestamp}", style="dim")
    console.print(Panel(header_text, border_style="cyan", padding=(0, 2)))
    console.print()

    # ── System info ─────────────────────────────────────────────────────────
    available_ports, default_port = detect_ports()
    port_to_use: str = args.port or (available_ports[0] if available_ports else default_port)

    sys_table = Table(show_header=False, box=None, padding=(0, 2))
    sys_table.add_column("Key", style="bold dim", no_wrap=True)
    sys_table.add_column("Value")

    sys_table.add_row("OS", f"{platform.system()} {platform.release()}")
    sys_table.add_row("Python", sys.version.split()[0])
    sys_table.add_row("Port pattern", port_pattern_for_os())
    sys_table.add_row(
        "Detected ports",
        ", ".join(available_ports) if available_ports else "[dim]none found[/dim]",
    )
    sys_table.add_row(
        "Using port",
        f"[bold]{port_to_use}[/bold]" + (" [dim](--port override)[/dim]" if args.port else ""),
    )
    sys_table.add_row("Timeout", f"{args.timeout:.0f}s")

    console.print(Panel(sys_table, title="[bold]System Info[/bold]", border_style="blue"))
    console.print()

    # ── Connection attempt ───────────────────────────────────────────────────
    connection: obd.OBD | None = None

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task(f"Connecting to [bold]{port_to_use}[/bold]...", total=None)
        try:
            connection = obd.OBD(
                portstr=port_to_use,
                timeout=args.timeout,
                check_voltage=False,
            )
            if not connection.is_connected():
                connection = None
        except Exception:
            connection = None
        finally:
            progress.remove_task(task)

    if connection is not None and connection.is_connected():
        protocol = connection.protocol_name() or "Unknown protocol"
        console.print(
            f"[bold green]✓ Connected[/bold green]  [dim]{protocol}[/dim]  "
            f"[dim]on {port_to_use}[/dim]"
        )
        console.print()
        _show_connected(console, connection)
    else:
        console.print(
            f"[bold yellow]⚠ No adapter found[/bold yellow]  "
            f"[dim]Could not connect on {port_to_use}[/dim]"
        )
        console.print()
        _show_troubleshooting(console)

    # ── Footer ───────────────────────────────────────────────────────────────
    elapsed = time.monotonic() - start_time
    console.print()
    console.print(f"[dim]Completed in {elapsed:.2f}s[/dim]")

    return 0


# ---------------------------------------------------------------------------
# Connected view
# ---------------------------------------------------------------------------


def _show_connected(console: Console, connection: obd.OBD) -> None:
    supported_count = len(connection.supportedCommands)
    console.print(f"[bold]Adapter supports[/bold] [cyan]{supported_count}[/cyan] commands")
    console.print()

    # ── Live sensor table ────────────────────────────────────────────────────
    sensor_table = Table(
        title="Live Sensor Readings",
        show_header=True,
        header_style="bold magenta",
        border_style="dim",
    )
    sensor_table.add_column("Sensor", style="bold", no_wrap=True)
    sensor_table.add_column("Value", justify="right")
    sensor_table.add_column("Unit", style="dim")
    sensor_table.add_column("Supported", justify="center")

    for cmd_name in SENSOR_COMMANDS:
        label = SENSOR_LABELS.get(cmd_name, cmd_name)

        # Check if command exists in obd.commands namespace
        if not hasattr(obd.commands, cmd_name):
            sensor_table.add_row(label, "[dim]N/A[/dim]", "", "[dim]—[/dim]")
            continue

        cmd = getattr(obd.commands, cmd_name)

        # Check if adapter supports this command
        if cmd not in connection.supportedCommands:
            sensor_table.add_row(label, "[dim]N/A[/dim]", "", "[yellow]✗[/yellow]")
            continue

        # Query the command
        try:
            response = connection.query(cmd)
        except Exception:
            sensor_table.add_row(label, "[dim]N/A[/dim]", "", "[yellow]✗[/yellow]")
            continue

        if response is None or response.is_null():
            sensor_table.add_row(label, "[dim]N/A[/dim]", "", "[yellow]✗[/yellow]")
            continue

        value = response.value
        if value is not None and hasattr(value, "magnitude"):
            # pint Quantity
            unit_str = str(value.units) if hasattr(value, "units") else ""
            val_str = f"{value.magnitude:.2f}"
        else:
            val_str = str(value) if value is not None else "N/A"
            unit_str = ""

        sensor_table.add_row(
            label,
            f"[green]{val_str}[/green]",
            unit_str,
            "[green]✓[/green]",
        )

    console.print(sensor_table)
    console.print()

    # ── DTC codes ────────────────────────────────────────────────────────────
    dtc_db = load_dtc_db()
    dtcs: list[tuple[str, str]] = []

    if hasattr(obd.commands, "GET_DTC") and obd.commands.GET_DTC in connection.supportedCommands:
        try:
            response = connection.query(obd.commands.GET_DTC)
            if response is not None and not response.is_null() and response.value:
                for entry in response.value:
                    # entry is typically (code_str, description_str) or just code_str
                    if isinstance(entry, (list, tuple)) and len(entry) >= 1:
                        code = str(entry[0]).upper()
                        obd_desc = str(entry[1]) if len(entry) > 1 else ""
                    else:
                        code = str(entry).upper()
                        obd_desc = ""

                    db_entry = dtc_db.get(code)
                    description = (
                        db_entry["description"] if db_entry else obd_desc or "Unknown fault code"
                    )
                    dtcs.append((code, description))
        except Exception:
            pass

    if dtcs:
        dtc_table = Table(
            title="Fault Codes (DTCs)",
            show_header=True,
            header_style="bold red",
            border_style="dim",
        )
        dtc_table.add_column("Code", style="bold red", no_wrap=True)
        dtc_table.add_column("Description")

        for code, description in sorted(dtcs):
            dtc_table.add_row(code, description)

        console.print(dtc_table)
    else:
        console.print("[bold green]✓ No fault codes[/bold green]")


# ---------------------------------------------------------------------------
# Not-connected view
# ---------------------------------------------------------------------------


def _show_troubleshooting(console: Console) -> None:
    system = platform.system()

    lines: list[str] = [
        "[bold yellow]No OBD adapter detected.[/bold yellow]",
        "",
        "[bold]Troubleshooting:[/bold]",
    ]

    if system == "Linux":
        lines += [
            "• [bold]Linux:[/bold] Check [cyan]dmesg | grep ttyUSB[/cyan] — adapter should appear as ttyUSB0",
            "• [bold]Linux:[/bold] Run: [cyan]sudo usermod -a -G dialout $USER[/cyan] (then re-login)",
        ]
    elif system == "Darwin":
        lines += [
            "• [bold]macOS:[/bold] Check [cyan]ls /dev/cu.usbserial-*[/cyan] — may need FTDI VCP driver",
            "• [bold]macOS:[/bold] Download FTDI VCP driver from [cyan]https://ftdichip.com/drivers/vcp-drivers/[/cyan]",
        ]
    elif system == "Windows":
        lines += [
            "• [bold]Windows:[/bold] Check Device Manager → Ports (COM & LPT)",
            "• [bold]Windows:[/bold] Set [cyan]OBD_PORT=COMx[/cyan] in your [cyan].env[/cyan] file",
        ]
    else:
        lines += [
            "• [bold]Linux:[/bold] Check [cyan]dmesg | grep ttyUSB[/cyan] — adapter should appear as ttyUSB0",
            "• [bold]Linux:[/bold] Run: [cyan]sudo usermod -a -G dialout $USER[/cyan] (then re-login)",
            "• [bold]macOS:[/bold] Check [cyan]ls /dev/cu.usbserial-*[/cyan] — may need FTDI VCP driver",
            "• [bold]Windows:[/bold] Check Device Manager → Ports (COM & LPT), set [cyan]OBD_PORT=COMx[/cyan] in .env",
        ]

    lines += [
        "• [bold]All platforms:[/bold] Make sure the adapter is plugged into the car's OBD-II port AND the USB port",
        "",
        "Pass [cyan]--port PORT[/cyan] to override auto-detection (e.g. [cyan]--port /dev/ttyUSB1[/cyan])",
    ]

    console.print(
        Panel(
            "\n".join(lines),
            title="[bold yellow]Connection Failed[/bold yellow]",
            border_style="yellow",
            padding=(1, 2),
        )
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.exit(main())
