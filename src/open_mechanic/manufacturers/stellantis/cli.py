"""Ephemeral Rich views for catalog-bounded Stellantis diagnostics."""

from __future__ import annotations

import time
from collections.abc import Callable

from rich.console import Console
from rich.table import Table

from open_mechanic.manufacturers.stellantis.models import (
    LiveValue,
    StellantisScanResult,
)
from open_mechanic.manufacturers.stellantis.scanner import StellantisScanner
from open_mechanic.protocols.elm327 import ELM327ConnectionError

MAX_LIVE_SAMPLES = 60
MAX_LIVE_INTERVAL_SECONDS = 10.0

_DTC_STATUS_FLAGS = (
    "testFailed",
    "testFailedThisOperationCycle",
    "pendingDTC",
    "confirmedDTC",
    "testNotCompletedSinceLastClear",
    "testFailedSinceLastClear",
    "testNotCompletedThisOperationCycle",
    "warningIndicatorRequested",
)


def dtc_status_flags(mask: int) -> tuple[str, ...]:
    """Return standard UDS status flag names while retaining the raw mask."""
    return tuple(name for bit, name in enumerate(_DTC_STATUS_FLAGS) if mask & (1 << bit))


def render_scan(console: Console, result: StellantisScanResult) -> None:
    """Render module-grouped DTC results without storing them."""
    table = Table(title="2024 Wrangler JL 4xe — read-only module DTC scan")
    table.add_column("Module")
    table.add_column("Status")
    table.add_column("DTC")
    table.add_column("Mask / flags")
    table.add_column("Definition")
    table.add_column("Evidence")
    for module in result.modules:
        if module.dtcs:
            for dtc in module.dtcs:
                flags = ", ".join(dtc_status_flags(dtc.status_mask)) or "none"
                table.add_row(
                    module.module_name,
                    module.state.value,
                    f"0x{dtc.identifier:06X}",
                    f"0x{dtc.status_mask:02X} ({flags})",
                    "unknown",
                    module.applicability,
                )
        else:
            table.add_row(
                module.module_name,
                module.state.value,
                "—",
                "—",
                module.error or "No DTCs reported",
                module.applicability,
            )
    console.print(table)
    console.print("[dim]No diagnostic data was saved, cached, or sent anywhere.[/dim]")


def render_scan_to_text(result: StellantisScanResult) -> str:
    """Render a scan to plain text for alternate frontends and tests."""
    console = Console(record=True, width=160)
    render_scan(console, result)
    return console.export_text()


def run_scan(console: Console, scanner: StellantisScanner) -> int:
    """Run and render one ephemeral module scan with actionable permissions help."""
    try:
        result = scanner.scan_dtcs()
    except ELM327ConnectionError as error:
        console.print(f"[red]{error}[/red]")
        console.print(
            "[yellow]Linux access:[/yellow] verify the device permissions and your dialout "
            "group or an equivalent udev ACL. Do not run open-mechanic as root."
        )
        console.print("[dim]No diagnostic data was saved, cached, or sent anywhere.[/dim]")
        return 1
    render_scan(console, result)
    return 0


def render_live(console: Console, values: tuple[LiveValue, ...], *, sample: int) -> None:
    """Render one finite live-data sample."""
    table = Table(title=f"Cruise live data — sample {sample}")
    table.add_column("Source")
    table.add_column("Value")
    table.add_column("Freshness")
    table.add_column("Status / event")
    table.add_column("Evidence")
    for value in values:
        display = "unavailable" if value.value is None else str(value.value)
        if value.unit:
            display = f"{display} {value.unit}"
        status = value.state.value
        if value.error:
            status = f"{status}: {value.error}"
        if value.event_marker:
            status = f"{status}; {value.event_marker}"
        table.add_row(
            f"{value.module_key} / {value.label}",
            display,
            "fresh" if value.fresh else "stale/unavailable",
            status,
            value.applicability,
        )
    console.print(table)
    console.print("[dim]No diagnostic data was saved, cached, or sent anywhere.[/dim]")


def render_live_to_text(values: tuple[LiveValue, ...], *, sample: int) -> str:
    """Render live values to plain text."""
    console = Console(record=True, width=180)
    render_live(console, values, sample=sample)
    return console.export_text()


def validate_live_bounds(samples: int, interval: float) -> None:
    if not 1 <= samples <= MAX_LIVE_SAMPLES:
        raise ValueError(f"samples must be from 1 to {MAX_LIVE_SAMPLES}")
    if not 0 < interval <= MAX_LIVE_INTERVAL_SECONDS:
        raise ValueError(f"interval must be greater than 0 and at most {MAX_LIVE_INTERVAL_SECONDS}")


def run_live(
    console: Console,
    scanner: StellantisScanner,
    *,
    samples: int,
    interval: float,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Collect a finite number of ephemeral cruise samples."""
    validate_live_bounds(samples, interval)
    console.print(
        "[bold yellow]Driver-distraction warning:[/bold yellow] moving tests must be operated "
        "by a passenger or qualified technician; the driver must not operate this computer."
    )
    try:
        for sample in range(1, samples + 1):
            render_live(console, scanner.read_group("cruise"), sample=sample)
            if sample < samples:
                sleep(interval)
    except KeyboardInterrupt:
        console.print("[yellow]Stopped. The adapter was closed; no history was retained.[/yellow]")
        console.print("[dim]No diagnostic data was saved, cached, or sent anywhere.[/dim]")
        return 130
    return 0
