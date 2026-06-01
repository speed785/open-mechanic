from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from rich.table import Table
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Static

from open_mechanic.ai.providers import ProviderConfigurationError, select_provider
from open_mechanic.connection import OBDConnection
from open_mechanic.dtc import DTCCode, DTCReader
from open_mechanic.local_store import VehicleProfile, load_vehicle_profile
from open_mechanic.reader import SensorPoller, SensorValue


class DashboardView(StrEnum):
    OVERVIEW = "Overview"
    SENSORS = "Live Sensors"
    DTCS = "Fault Codes"
    READINESS = "Readiness"
    DIAGNOSIS = "AI Diagnosis"
    LOGS = "Logs"


_VIEW_ORDER: tuple[DashboardView, ...] = (
    DashboardView.OVERVIEW,
    DashboardView.SENSORS,
    DashboardView.DTCS,
    DashboardView.READINESS,
    DashboardView.DIAGNOSIS,
    DashboardView.LOGS,
)


@dataclass
class DashboardState:
    active_view: DashboardView = DashboardView.OVERVIEW
    connected: bool = False
    port: str | None = None
    protocol: str | None = None
    profile: VehicleProfile | None = None
    provider_name: str = "unknown"
    sensors: dict[str, SensorValue] = field(default_factory=dict)
    dtcs: list[DTCCode] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)

    @property
    def adapter_label(self) -> str:
        if not self.connected:
            return "Disconnected"
        details = " ".join(part for part in (self.protocol, self.port) if part)
        return f"Connected {details}".strip()

    @property
    def status_line(self) -> str:
        if not self.connected:
            return "Offline - connect an OBD adapter to stream live vehicle data"
        return "Connected - live vehicle data is updating"

    def select_next_view(self) -> None:
        index = _VIEW_ORDER.index(self.active_view)
        self.active_view = _VIEW_ORDER[(index + 1) % len(_VIEW_ORDER)]

    def select_previous_view(self) -> None:
        index = _VIEW_ORDER.index(self.active_view)
        self.active_view = _VIEW_ORDER[(index - 1) % len(_VIEW_ORDER)]


class OpenMechanicDashboard(App[None]):
    CSS = """
    Screen {
        background: #0f1117;
        color: #e5e7eb;
    }

    #shell {
        height: 1fr;
    }

    #nav {
        width: 25;
        min-width: 25;
        border: solid #334155;
        padding: 1;
        background: #111827;
    }

    #content {
        width: 1fr;
        border: solid #334155;
        padding: 1 2;
    }

    #status {
        dock: bottom;
        height: 3;
        border: solid #334155;
        padding: 0 1;
        background: #111827;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("up", "previous_view", "Previous"),
        Binding("down", "next_view", "Next"),
        Binding("enter", "select_view", "Select"),
        Binding("r", "reconnect", "Reconnect"),
        Binding("d", "diagnose", "Diagnose"),
    ]

    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__()
        self.args = args
        self.state = DashboardState(profile=load_vehicle_profile())
        self._connection: OBDConnection | None = None
        self._poller: SensorPoller | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="shell"):
            yield Static(id="nav")
            with Vertical(id="content"):
                yield Static(id="main")
        yield Static(id="status")
        yield Footer()

    def on_mount(self) -> None:
        self._resolve_provider()
        if not bool(getattr(self.args, "offline", False)):
            self._connect()
        self.set_interval(float(getattr(self.args, "interval", 1.0)), self._poll)
        self._render()

    def action_next_view(self) -> None:
        self.state.select_next_view()
        self._render()

    def action_previous_view(self) -> None:
        self.state.select_previous_view()
        self._render()

    def action_select_view(self) -> None:
        self._render()

    def action_reconnect(self) -> None:
        self._disconnect()
        self._connect()
        self._render()

    def action_diagnose(self) -> None:
        self.state.active_view = DashboardView.DIAGNOSIS
        self.state.logs.append(
            "AI Diagnosis selected. Use open-mechanic diagnose for full report output."
        )
        self._render()

    def on_unmount(self) -> None:
        self._disconnect()

    def _resolve_provider(self) -> None:
        try:
            provider = select_provider(getattr(self.args, "provider", None))
            self.state.provider_name = provider.name
        except ProviderConfigurationError as exc:
            self.state.provider_name = "not configured"
            self.state.logs.append(f"AI provider: {exc}")

    def _connect(self) -> None:
        self.state.logs.append("Connecting to OBD adapter...")
        connection = OBDConnection(
            port=getattr(self.args, "port", None),
            protocol=getattr(self.args, "protocol", None),
            baudrate=getattr(self.args, "baudrate", 115200),
            timeout=getattr(self.args, "timeout", 10.0),
            max_retries=1,
        )
        if not connection.connect():
            self.state.connected = False
            self.state.logs.append("No OBD adapter connection.")
            return
        raw_conn = connection.get_connection()
        self._connection = connection
        self._poller = SensorPoller(connection, interval=float(getattr(self.args, "interval", 1.0)))
        self.state.connected = True
        self.state.port = connection.get_port()
        self.state.protocol = raw_conn.protocol_name() if raw_conn is not None else "unknown"
        self.state.logs.append(f"Connected on {self.state.port}.")

    def _disconnect(self) -> None:
        if self._connection is not None:
            self._connection.disconnect()
        self._connection = None
        self._poller = None
        self.state.connected = False
        self.state.port = None
        self.state.protocol = None

    def _poll(self) -> None:
        if self._poller is None or self._connection is None:
            return
        self.state.sensors = self._poller.get_snapshot()
        self.state.dtcs = DTCReader(self._connection).get_dtcs()
        self._render()

    def _render(self) -> None:
        self.query_one("#nav", Static).update(self._nav_text())
        self.query_one("#main", Static).update(self._main_view())
        self.query_one("#status", Static).update(self._status_text())

    def _nav_text(self) -> str:
        lines = ["open-mechanic", ""]
        for view in _VIEW_ORDER:
            marker = ">" if view == self.state.active_view else " "
            lines.append(f"{marker} {view.value}")
        lines.extend(
            ["", "Up/Down: move", "Enter: select", "r: reconnect", "d: diagnose", "q: quit"]
        )
        return "\n".join(lines)

    def _status_text(self) -> str:
        profile = self.state.profile.label if self.state.profile else "No vehicle profile"
        return (
            f"{profile}\n"
            f"{self.state.adapter_label} | AI provider: {self.state.provider_name}\n"
            f"{self.state.status_line}"
        )

    def _main_view(self) -> Any:
        if self.state.active_view == DashboardView.OVERVIEW:
            return self._overview()
        if self.state.active_view == DashboardView.SENSORS:
            return self._sensor_table()
        if self.state.active_view == DashboardView.DTCS:
            return self._dtc_table()
        if self.state.active_view == DashboardView.READINESS:
            return self._placeholder("Readiness monitors will use the connected OBD adapter.")
        if self.state.active_view == DashboardView.DIAGNOSIS:
            return self._placeholder(
                "Press d to focus diagnosis. Full report output uses open-mechanic diagnose."
            )
        return "\n".join(self.state.logs[-12:]) or "No dashboard events yet."

    def _overview(self) -> Table:
        table = Table(title="Overview")
        table.add_column("Field", style="bold cyan")
        table.add_column("Value")
        profile = self.state.profile.label if self.state.profile else "not set"
        table.add_row("Vehicle", profile)
        table.add_row("Adapter", self.state.adapter_label)
        table.add_row("AI provider", self.state.provider_name)
        table.add_row("Active DTCs", str(len(self.state.dtcs)))
        table.add_row(
            "Supported live sensors",
            str(sum(1 for sensor in self.state.sensors.values() if sensor.supported)),
        )
        table.add_row("Enhanced modules", "future: ABS, SRS, transmission, body modules, TPMS")
        return table

    def _sensor_table(self) -> Table:
        table = Table(title="Live Sensors")
        table.add_column("Sensor", style="bold")
        table.add_column("Value", justify="right")
        table.add_column("Unit")
        supported = {name: value for name, value in self.state.sensors.items() if value.supported}
        if not supported:
            table.add_row("Sensors", "N/A", "connect adapter to stream data")
        else:
            for name, sensor in supported.items():
                table.add_row(name, str(sensor.value), sensor.unit or "")
        return table

    def _dtc_table(self) -> Table:
        table = Table(title="Fault Codes")
        table.add_column("Code", style="bold red")
        table.add_column("Severity")
        table.add_column("Description")
        if not self.state.dtcs:
            table.add_row("OK", "info", "No active codes available")
        else:
            for dtc in self.state.dtcs:
                table.add_row(dtc.code, dtc.severity, dtc.description)
        return table

    def _placeholder(self, message: str) -> str:
        return f"{self.state.active_view.value}\n\n{message}"


def run_dashboard(args: argparse.Namespace) -> int:
    OpenMechanicDashboard(args).run()
    return 0
