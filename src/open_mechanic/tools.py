from __future__ import annotations

# pyright: reportMissingTypeStubs=false, reportAttributeAccessIssue=false
import argparse
import sys
import time
from dataclasses import asdict
from datetime import datetime
from typing import Any, Protocol

import obd
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.prompt import IntPrompt, Prompt
from rich.table import Table
from rich.text import Text

from open_mechanic.connection import OBDConnection, scan_ports
from open_mechanic.dtc import DTCReader
from open_mechanic.local_store import (
    PROFILE_PATH,
    SESSIONS_DIR,
    SessionLog,
    VehicleProfile,
    ensure_local_dirs,
    load_vehicle_profile,
    save_vehicle_profile,
)
from open_mechanic.reader import SENSOR_COMMANDS, SensorPoller, SensorValue

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
    "CONTROL_MODULE_VOLTAGE": "Control Module Voltage",
    "ENGINE_LOAD": "Engine Load",
    "TIMING_ADVANCE": "Timing Advance",
}

HEALTH_COMMANDS: list[str] = [
    "RPM",
    "SPEED",
    "COOLANT_TEMP",
    "INTAKE_TEMP",
    "CONTROL_MODULE_VOLTAGE",
    "ENGINE_LOAD",
    "THROTTLE_POS",
    "SHORT_FUEL_TRIM_1",
    "LONG_FUEL_TRIM_1",
    "MAF",
]

FREEZE_FRAME_COMMANDS: list[str] = [
    "DTC_FREEZE_DTC",
    "DTC_RPM",
    "DTC_SPEED",
    "DTC_COOLANT_TEMP",
    "DTC_INTAKE_TEMP",
    "DTC_ENGINE_LOAD",
    "DTC_CONTROL_MODULE_VOLTAGE",
    "DTC_THROTTLE_POS",
    "DTC_SHORT_FUEL_TRIM_1",
    "DTC_LONG_FUEL_TRIM_1",
    "DTC_FUEL_STATUS",
    "DTC_INTAKE_PRESSURE",
    "DTC_TIMING_ADVANCE",
    "DTC_MAF",
]

READINESS_COMMANDS: list[str] = ["STATUS", "DTC_STATUS_DRIVE_CYCLE"]

GRAPH_SENSOR_NAMES: list[str] = [
    "RPM",
    "COOLANT_TEMP",
    "CONTROL_MODULE_VOLTAGE",
    "ENGINE_LOAD",
    "THROTTLE_POS",
    "SHORT_FUEL_TRIM_1",
    "LONG_FUEL_TRIM_1",
]

GRAPH_RANGES: dict[str, tuple[float, float]] = {
    "RPM": (0.0, 7000.0),
    "COOLANT_TEMP": (40.0, 120.0),
    "CONTROL_MODULE_VOLTAGE": (11.0, 15.0),
    "ENGINE_LOAD": (0.0, 100.0),
    "THROTTLE_POS": (0.0, 100.0),
    "SHORT_FUEL_TRIM_1": (-25.0, 25.0),
    "LONG_FUEL_TRIM_1": (-25.0, 25.0),
}

MAJOR_MAKES: list[str] = [
    "Acura",
    "Alfa Romeo",
    "Audi",
    "BMW",
    "Buick",
    "Cadillac",
    "Chevrolet",
    "Chrysler",
    "Dodge",
    "Fiat",
    "Ford",
    "Genesis",
    "GMC",
    "Honda",
    "Hyundai",
    "Infiniti",
    "Jaguar",
    "Jeep",
    "Kia",
    "Land Rover",
    "Lexus",
    "Lincoln",
    "Lucid",
    "Mazda",
    "Mercedes-Benz",
    "Mercury",
    "Mini",
    "Mitsubishi",
    "Nissan",
    "Porsche",
    "Ram",
    "Rivian",
    "Scion",
    "Subaru",
    "Tesla",
    "Toyota",
    "Volkswagen",
    "Volvo",
    "Other",
]

MENU_ITEMS: list[tuple[str, str]] = [
    ("profile", "Vehicle Profile"),
    ("sensors", "Live Sensors"),
    ("dtcs", "Fault Codes"),
    ("readiness", "Readiness Monitors"),
    ("freeze-frame", "Freeze Frame"),
    ("snapshot", "Health Snapshot"),
    ("quit", "Exit"),
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="open-mechanic",
        description="Read-only OBD-II tools for open-mechanic.",
    )
    subparsers = parser.add_subparsers(dest="command")

    tools_parser = subparsers.add_parser("tools", help="Open the read-only tools menu")
    _add_connection_args(tools_parser)

    for name in ("sensors", "dtcs", "readiness", "freeze-frame", "snapshot", "profile"):
        cmd = subparsers.add_parser(name, help=f"Run {name} tool")
        _add_connection_args(cmd)
        if name == "sensors":
            cmd.add_argument("--samples", type=int, default=0, help="Samples to capture; 0 runs until Ctrl-C")
            cmd.add_argument("--interval", type=float, default=1.0, help="Refresh interval in seconds")
            cmd.add_argument("--no-graphs", action="store_true", help="Hide live sensor graphs")

    args = parser.parse_args(argv)
    console = Console()
    ensure_local_dirs()

    if args.command is None:
        return run_tools_menu(args, console)
    if args.command == "tools":
        return run_tools_menu(args, console)
    if args.command == "profile":
        profile = prompt_vehicle_profile(console)
        show_profile(console, profile)
        return 0

    return run_direct_tool(args.command, args, console)


def _add_connection_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--port", default=None, help="Serial port override, for example /dev/ttyUSB0")
    parser.add_argument("--protocol", default=None, help="OBD protocol override, for example 6 for CAN 11/500")
    parser.add_argument("--timeout", type=float, default=10.0, help="Connection timeout in seconds")
    parser.add_argument("--baudrate", type=int, default=115200, help="Serial baudrate")


def run_tools_menu(args: argparse.Namespace, console: Console) -> int:
    profile = load_vehicle_profile()
    selected = 1
    while True:
        selected = _select_menu_item(console, profile, selected)
        tool_name = MENU_ITEMS[selected][0]

        if tool_name == "quit":
            return 0
        if tool_name == "profile":
            console.clear()
            profile = prompt_vehicle_profile(console)
            show_profile(console, profile)
            Prompt.ask("Press Enter to return to tools", default="")
            continue

        if profile is None:
            console.clear()
            console.print("[yellow]Vehicle profile not set yet.[/yellow]")
            profile = prompt_vehicle_profile(console)

        console.clear()
        status = run_direct_tool(tool_name, args, console, profile=profile)
        if status != 0:
            return status
        Prompt.ask("Press Enter to return to tools", default="")



def _select_menu_item(console: Console, profile: VehicleProfile | None, selected: int) -> int:
    if not sys.stdin.isatty() or sys.platform == "win32":
        return _prompt_menu_item(console, profile)

    while True:
        console.clear()
        console.print(_header(profile))
        console.print(_menu_table(selected))
        console.print("[dim]Use Up/Down and Enter. Number keys still work. Press q to exit.[/dim]")
        key = _read_key()
        if key in {"up", "k"}:
            selected = (selected - 1) % len(MENU_ITEMS)
        elif key in {"down", "j"}:
            selected = (selected + 1) % len(MENU_ITEMS)
        elif key in {"enter", "\n", "\r"}:
            return selected
        elif key == "q":
            return len(MENU_ITEMS) - 1
        elif key.isdigit():
            index = int(key) - 1
            if 0 <= index < len(MENU_ITEMS) - 1:
                return index


def _prompt_menu_item(console: Console, profile: VehicleProfile | None) -> int:
    console.print(_header(profile))
    console.print(_menu_table(1))
    choices = [str(i) for i in range(1, len(MENU_ITEMS))] + ["q"]
    choice = Prompt.ask("Select", choices=choices, default="2")
    if choice == "q":
        return len(MENU_ITEMS) - 1
    return int(choice) - 1


def _menu_table(selected: int) -> Table:
    table = Table(title="Tools", show_header=False, border_style="blue")
    table.add_column("", width=2, no_wrap=True)
    table.add_column("Key", style="bold cyan", no_wrap=True)
    table.add_column("Tool")
    for index, (_, label) in enumerate(MENU_ITEMS):
        key = "q" if label == "Exit" else str(index + 1)
        cursor = ">" if index == selected else ""
        style = "reverse" if index == selected else None
        table.add_row(cursor, key, label, style=style)
    return table


def _read_key() -> str:
    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        first = sys.stdin.read(1)
        if first == "\x1b":
            second = sys.stdin.read(1)
            third = sys.stdin.read(1) if second == "[" else ""
            if third == "A":
                return "up"
            if third == "B":
                return "down"
            return "escape"
        if first in {"\r", "\n"}:
            return "enter"
        return first.lower()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def run_direct_tool(
    tool_name: str,
    args: argparse.Namespace,
    console: Console,
    profile: VehicleProfile | None = None,
) -> int:
    active_profile = profile or load_vehicle_profile()
    if active_profile is None and tool_name != "profile":
        console.print("[yellow]Vehicle profile not set yet.[/yellow]")
        active_profile = prompt_vehicle_profile(console)

    connection = OBDConnection(
        port=getattr(args, "port", None),
        protocol=getattr(args, "protocol", None),
        baudrate=getattr(args, "baudrate", 115200),
        timeout=getattr(args, "timeout", 10.0),
        max_retries=1,
    )
    console.print(_header(active_profile))
    console.print("[dim]Read-only mode: this CLI does not clear codes or write to the car.[/dim]")
    connected = connection.connect()
    if not connected:
        console.print("[bold yellow]No OBD adapter connection.[/bold yellow]")
        return 1

    raw_conn = connection.get_connection()
    protocol = raw_conn.protocol_name() if raw_conn is not None else "unknown"
    console.print(f"[green]Connected[/green] [dim]{protocol} on {connection.get_port()}[/dim]")

    log = SessionLog(tool_name, active_profile)
    log.write(
        "connection",
        {"port": connection.get_port(), "protocol": protocol, "supported_commands": _supported_count(raw_conn)},
    )

    try:
        if tool_name == "sensors":
            samples = int(getattr(args, "samples", 0) or 0)
            interval = float(getattr(args, "interval", 1.0) or 1.0)
            show_graphs = not bool(getattr(args, "no_graphs", False))
            show_live_sensors(
                console,
                connection,
                log,
                samples=samples,
                interval=interval,
                show_graphs=show_graphs,
            )
        elif tool_name == "dtcs":
            show_dtcs(console, connection, log)
        elif tool_name == "readiness":
            show_readiness(console, connection, log)
        elif tool_name == "freeze-frame":
            show_freeze_frame(console, connection, log)
        elif tool_name == "snapshot":
            show_health_snapshot(console, connection, log)
        else:
            console.print(f"[red]Unknown tool:[/red] {tool_name}")
            return 2
    finally:
        connection.disconnect()

    console.print(f"[dim]Session log: {log.path}[/dim]")
    return 0


def prompt_vehicle_profile(console: Console) -> VehicleProfile:
    console.print(Panel("Vehicle Profile", border_style="cyan"))
    year = IntPrompt.ask("Year")
    make = select_vehicle_make(console)
    model = Prompt.ask("Model").strip()
    mileage_text = Prompt.ask("Mileage (optional)", default="").strip()
    mileage = int(mileage_text) if mileage_text.isdigit() else None
    profile = VehicleProfile(year=year, make=make, model=model, mileage=mileage)
    save_vehicle_profile(profile)
    console.print(f"[green]Saved profile locally:[/green] {PROFILE_PATH}")
    return profile



def select_vehicle_make(console: Console) -> str:
    selected = _select_from_list(console, "Select Make", MAJOR_MAKES)
    if selected == "Other":
        return Prompt.ask("Make").strip()
    return selected


def _select_from_list(
    console: Console,
    title: str,
    options: list[str],
    default_index: int = 0,
) -> str:
    if not sys.stdin.isatty() or sys.platform == "win32":
        choices = [str(index + 1) for index in range(len(options))]
        table = _option_table(title, options, default_index)
        console.print(table)
        choice = Prompt.ask("Select", choices=choices, default=str(default_index + 1))
        return options[int(choice) - 1]

    selected = max(0, min(default_index, len(options) - 1))
    while True:
        console.clear()
        console.print(_option_table(title, options, selected))
        console.print("[dim]Use Up/Down and Enter. Type a number for quick select.[/dim]")
        key = _read_key()
        if key in {"up", "k"}:
            selected = (selected - 1) % len(options)
        elif key in {"down", "j"}:
            selected = (selected + 1) % len(options)
        elif key in {"enter", "\n", "\r"}:
            console.clear()
            return options[selected]
        elif key.isdigit():
            next_selected = _read_number_selection(key, len(options), selected)
            if next_selected is not None:
                console.clear()
                return options[next_selected]
            selected = 0


def _read_number_selection(first_digit: str, option_count: int, current: int) -> int | None:
    digits = first_digit
    if option_count >= 10 and sys.stdin.isatty():
        try:
            next_char = _read_key_timeout()
        except OSError:
            next_char = ""
        if next_char.isdigit():
            digits += next_char
    index = int(digits) - 1
    if 0 <= index < option_count:
        return index
    return current if 0 <= current < option_count else None


def _read_key_timeout(timeout_seconds: float = 0.25) -> str:
    import select
    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        readable, _, _ = select.select([sys.stdin], [], [], timeout_seconds)
        if not readable:
            return ""
        return sys.stdin.read(1).lower()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def _option_table(title: str, options: list[str], selected: int) -> Table:
    table = Table(title=title, show_header=False, border_style="blue")
    table.add_column("", width=2, no_wrap=True)
    table.add_column("Key", style="bold cyan", no_wrap=True)
    table.add_column("Option")
    for index, option in enumerate(options):
        cursor = ">" if index == selected else ""
        style = "reverse" if index == selected else None
        table.add_row(cursor, str(index + 1), option, style=style)
    return table


def show_profile(console: Console, profile: VehicleProfile | None = None) -> None:
    active_profile = profile or load_vehicle_profile()
    table = Table(title="Vehicle Profile", show_header=False, border_style="dim")
    table.add_column("Field", style="bold dim")
    table.add_column("Value")
    if active_profile is None:
        table.add_row("Status", "[yellow]not set[/yellow]")
    else:
        table.add_row("Vehicle", active_profile.label)
        table.add_row("Mileage", str(active_profile.mileage) if active_profile.mileage else "[dim]not set[/dim]")
        table.add_row("Storage", str(PROFILE_PATH))
    console.print(table)


def show_live_sensors(
    console: Console,
    connection: OBDConnection,
    log: SessionLog,
    samples: int = 0,
    interval: float = 1.0,
    show_graphs: bool = True,
) -> None:
    poller = SensorPoller(connection, interval=interval)
    captured = 0
    history: dict[str, list[float]] = {name: [] for name in GRAPH_SENSOR_NAMES}
    try:
        with Live(console=console, refresh_per_second=4) as live:
            while samples == 0 or captured < samples:
                snapshot = poller.get_snapshot()
                captured += 1
                _update_sensor_history(history, snapshot)
                log.write("sensor_snapshot", _sensor_payload(snapshot))
                table = _sensor_table(snapshot, title=f"Live Sensors - sample {captured}")
                if show_graphs:
                    live.update(Group(table, _sensor_graph_table(history)))
                else:
                    live.update(table)
                time.sleep(interval)
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped live sensors.[/yellow]")


def show_dtcs(console: Console, connection: OBDConnection, log: SessionLog) -> None:
    dtcs = DTCReader(connection).get_dtcs()
    log.write("dtcs", {"codes": [asdict(dtc) for dtc in dtcs]})
    table = Table(title="Fault Codes", border_style="dim")
    table.add_column("Code", style="bold red", no_wrap=True)
    table.add_column("Status")
    table.add_column("Severity")
    table.add_column("Description")
    if not dtcs:
        table.add_row("OK", "none", "info", "No current or confirmed fault codes reported")
    else:
        for dtc in dtcs:
            table.add_row(dtc.code, dtc.status, dtc.severity, dtc.description)
    console.print(table)


def show_readiness(console: Console, connection: OBDConnection, log: SessionLog) -> None:
    conn = _require_raw_connection(connection)
    rows: list[dict[str, Any]] = []
    for name in READINESS_COMMANDS:
        command = getattr(obd.commands, name, None)
        if command is None:
            continue
        rows.extend(_readiness_rows(conn, name, command))

    log.write("readiness", {"rows": rows})
    table = Table(title="Readiness Monitors", border_style="dim")
    table.add_column("Source", style="bold")
    table.add_column("Monitor")
    table.add_column("Available")
    table.add_column("Complete")
    if not rows:
        table.add_row("STATUS", "No readiness data reported", "unknown", "unknown")
    else:
        for row in rows:
            table.add_row(
                str(row["source"]),
                str(row["monitor"]),
                _yes_no(row.get("available")),
                _yes_no(row.get("complete")),
            )
    console.print(table)


def show_freeze_frame(console: Console, connection: OBDConnection, log: SessionLog) -> None:
    conn = _require_raw_connection(connection)
    rows = _query_named_commands(conn, FREEZE_FRAME_COMMANDS)
    log.write("freeze_frame", {"rows": rows})
    table = Table(title="Freeze Frame", border_style="dim")
    table.add_column("PID", style="bold")
    table.add_column("Value")
    table.add_column("Unit")
    table.add_column("Status")
    if not rows:
        table.add_row("Freeze frame", "N/A", "", "No supported freeze-frame PIDs reported")
    else:
        for row in rows:
            table.add_row(row["label"], row["value"], row["unit"] or "", row["status"])
    console.print(table)


def show_health_snapshot(console: Console, connection: OBDConnection, log: SessionLog) -> None:
    conn = _require_raw_connection(connection)
    rows = _query_named_commands(conn, HEALTH_COMMANDS)
    dtcs = DTCReader(connection).get_dtcs()
    readiness = []
    status_cmd = getattr(obd.commands, "STATUS", None)
    if status_cmd is not None:
        readiness = _readiness_rows(conn, "STATUS", status_cmd)

    log.write(
        "health_snapshot",
        {"sensors": rows, "dtcs": [asdict(dtc) for dtc in dtcs], "readiness": readiness},
    )

    sensor_table = Table(title="Health Snapshot", border_style="dim")
    sensor_table.add_column("Metric", style="bold")
    sensor_table.add_column("Value", justify="right")
    sensor_table.add_column("Unit")
    sensor_table.add_column("Status")
    for row in rows:
        sensor_table.add_row(row["label"], row["value"], row["unit"] or "", row["status"])
    console.print(sensor_table)

    summary = Table(title="Summary", show_header=False, border_style="blue")
    summary.add_column("Key", style="bold dim")
    summary.add_column("Value")
    summary.add_row("Fault codes", str(len(dtcs)))
    incomplete = [row for row in readiness if row.get("available") and not row.get("complete")]
    summary.add_row("Incomplete readiness monitors", str(len(incomplete)))
    summary.add_row("Local session directory", str(SESSIONS_DIR))
    console.print(summary)


def _query_named_commands(conn: obd.OBD, command_names: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for name in command_names:
        command = getattr(obd.commands, name, None)
        if command is None:
            continue
        label = SENSOR_LABELS.get(name, name.replace("DTC_", "").replace("_", " ").title())
        if command not in conn.supported_commands:
            rows.append({"name": name, "label": label, "value": "N/A", "unit": "", "status": "unsupported"})
            continue
        try:
            response = conn.query(command)
        except Exception as exc:
            rows.append({"name": name, "label": label, "value": "N/A", "unit": "", "status": f"error: {exc}"})
            continue
        value, unit = _format_response(response)
        status = "ok" if value != "N/A" else "no data"
        rows.append({"name": name, "label": label, "value": value, "unit": unit, "status": status})
    return rows


def _readiness_rows(conn: obd.OBD, source: str, command: object) -> list[dict[str, Any]]:
    if command not in conn.supported_commands:
        return [{"source": source, "monitor": "command", "available": False, "complete": False}]
    try:
        response = conn.query(command)
    except Exception:
        return []
    if response is None or response.is_null() or response.value is None:
        return []

    value = response.value
    rows: list[dict[str, Any]] = []
    if hasattr(value, "MIL"):
        rows.append({"source": source, "monitor": "MIL", "available": True, "complete": not bool(value.MIL)})
    if hasattr(value, "DTC_count"):
        rows.append({"source": source, "monitor": "DTC count", "available": True, "complete": int(value.DTC_count) == 0})

    items = sorted(getattr(value, "__dict__", {}).items(), key=lambda item: str(item[0]))
    for name, test in items:
        if name in {"MIL", "DTC_count", "ignition_type"} or name is None:
            continue
        if hasattr(test, "available") and hasattr(test, "complete"):
            rows.append(
                {
                    "source": source,
                    "monitor": getattr(test, "name", name) or name,
                    "available": bool(test.available),
                    "complete": bool(test.complete),
                }
            )
    return rows


def _sensor_table(snapshot: dict[str, SensorValue], title: str) -> Table:
    table = Table(title=title, border_style="dim")
    table.add_column("Sensor", style="bold", no_wrap=True)
    table.add_column("Value", justify="right")
    table.add_column("Unit")
    table.add_column("Status")
    for name in SENSOR_COMMANDS:
        sensor = snapshot.get(name)
        label = SENSOR_LABELS.get(name, name)
        if sensor is None:
            table.add_row(label, "N/A", "", "not queried")
        else:
            status = "supported" if sensor.supported else "unsupported/no data"
            value = sensor.value if sensor.supported else "N/A"
            table.add_row(label, value, sensor.unit or "", status)
    return table


def _sensor_payload(snapshot: dict[str, SensorValue]) -> dict[str, Any]:
    return {
        name: {
            "value": sensor.value,
            "unit": sensor.unit,
            "supported": sensor.supported,
            "timestamp": sensor.timestamp.isoformat(timespec="seconds"),
        }
        for name, sensor in snapshot.items()
    }



def _update_sensor_history(
    history: dict[str, list[float]], snapshot: dict[str, SensorValue], max_points: int = 48
) -> None:
    for name in GRAPH_SENSOR_NAMES:
        sensor = snapshot.get(name)
        if sensor is None or not sensor.supported:
            continue
        value = _parse_float(sensor.value)
        if value is None:
            continue
        points = history.setdefault(name, [])
        points.append(value)
        if len(points) > max_points:
            del points[:-max_points]


def _sensor_graph_table(history: dict[str, list[float]]) -> Table:
    table = Table(title="Live Sensor Graphs", border_style="green")
    table.add_column("Sensor", style="bold", no_wrap=True)
    table.add_column("Current", justify="right")
    table.add_column("Gauge")
    table.add_column("Recent History")
    for name in GRAPH_SENSOR_NAMES:
        points = history.get(name, [])
        if not points:
            continue
        label = SENSOR_LABELS.get(name, name)
        latest = points[-1]
        low, high = _graph_range(name, points)
        table.add_row(
            label,
            f"{latest:.2f}",
            _bar_gauge(latest, low, high),
            _history_line(points, low, high),
        )
    if not table.rows:
        table.add_row("No graphable values yet", "", "", "")
    return table


def _graph_range(name: str, points: list[float]) -> tuple[float, float]:
    configured = GRAPH_RANGES.get(name)
    if configured is not None:
        return configured
    low = min(points)
    high = max(points)
    if high == low:
        padding = max(abs(high) * 0.1, 1.0)
        return low - padding, high + padding
    return low, high


def _bar_gauge(value: float, low: float, high: float, width: int = 12) -> str:
    if high <= low:
        return "-" * width
    ratio = max(0.0, min(1.0, (value - low) / (high - low)))
    filled = round(ratio * width)
    bar = "#" * filled + "-" * (width - filled)
    return f"{bar} {low:g}..{high:g}"


def _history_line(points: list[float], low: float, high: float, width: int = 34) -> str:
    if not points:
        return ""
    visible = points[-width:]
    if high <= low:
        return "_" * len(visible)
    levels = "▁▂▃▄▅▆▇█"
    chars = []
    for value in visible:
        ratio = max(0.0, min(1.0, (value - low) / (high - low)))
        index = round(ratio * (len(levels) - 1))
        chars.append(levels[index])
    return "".join(chars)


def _parse_float(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


class _OBDResponse(Protocol):
    value: object

    def is_null(self) -> bool: ...


def _format_response(response: _OBDResponse | None) -> tuple[str, str]:
    if response is None or response.is_null():
        return "N/A", ""
    raw_value = response.value
    if raw_value is None:
        return "N/A", ""
    magnitude = getattr(raw_value, "magnitude", raw_value)
    unit_value = getattr(raw_value, "units", None)
    value = f"{magnitude:.2f}" if isinstance(magnitude, float) else str(magnitude)
    unit = str(unit_value) if unit_value is not None else ""
    return value, unit


def _yes_no(value: object) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "unknown"


def _supported_count(conn: obd.OBD | None) -> int:
    return len(conn.supported_commands) if conn is not None else 0


def _require_raw_connection(connection: OBDConnection) -> obd.OBD:
    conn = connection.get_connection()
    if conn is None:
        raise RuntimeError("OBD connection is not active")
    return conn


def _header(profile: VehicleProfile | None) -> Panel:
    text = Text()
    text.append("open-mechanic", style="bold cyan")
    text.append(f" tools v{VERSION}\n", style="bold white")
    if profile is None:
        text.append("Vehicle profile: not set", style="yellow")
    else:
        mileage = f" - {profile.mileage:,} mi" if profile.mileage else ""
        text.append(f"Vehicle profile: {profile.label}{mileage}", style="white")
    ports = scan_ports()
    port_text = ", ".join(ports) if ports else "none detected"
    text.append(f"\nDetected ports: {port_text}", style="dim")
    text.append(f"\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", style="dim")
    return Panel(text, border_style="cyan")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
