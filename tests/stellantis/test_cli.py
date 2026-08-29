from __future__ import annotations

from datetime import UTC, datetime

import pytest
from rich.console import Console

from open_mechanic.manufacturers.stellantis.cli import (
    MAX_LIVE_SAMPLES,
    render_live_to_text,
    render_scan_to_text,
    run_live,
    run_scan,
)
from open_mechanic.manufacturers.stellantis.models import (
    LiveValue,
    ModuleDTC,
    ModuleScanResult,
    ModuleState,
    StellantisScanResult,
)
from open_mechanic.protocols.elm327 import ELM327ConnectionError


def _scan_result() -> StellantisScanResult:
    return StellantisScanResult(
        (
            ModuleScanResult(
                "electric_power_steering",
                "Electric Power Steering Module",
                ModuleState.RESPONDED,
                (ModuleDTC(0x123456, 0x2F),),
                "community_unverified",
            ),
            ModuleScanResult(
                "adaptive_cruise",
                "Adaptive Cruise Control Module",
                ModuleState.GATEWAY_BLOCKED,
                (),
                "community_unverified",
                "securityAccessDenied (NRC 0x33)",
            ),
        )
    )


def test_scan_render_preserves_unknown_three_byte_dtc_status_and_partial_error() -> None:
    output = render_scan_to_text(_scan_result())

    assert "Electric Power Steering" in output
    assert "0x123456" in output
    assert "0x2F" in output
    assert "testFailed" in output
    assert "unknown" in output
    assert "community_unverified" in output
    assert "gateway_blocked" in output
    assert "securityAccessDenied" in output
    assert "No diagnostic data was saved" in output


def test_live_render_includes_source_units_freshness_event_and_safety_warning() -> None:
    output = render_live_to_text(
        (
            LiveValue(
                "abs_esc",
                "wheel_speed",
                "Wheel speed",
                48.5,
                485,
                "km/h",
                datetime(2026, 8, 29, 12, 0, tzinfo=UTC),
                True,
                ModuleState.RESPONDED,
                "exact_model_year",
                event_marker="engaged_to_cancelled",
            ),
        ),
        sample=2,
    )

    assert "abs_esc" in output
    assert "48.5" in output
    assert "km/h" in output
    assert "fresh" in output
    assert "engaged_to_cancelled" in output
    assert "No diagnostic data was saved" in output


@pytest.mark.parametrize("samples", [0, -1, MAX_LIVE_SAMPLES + 1])
def test_live_rejects_unbounded_or_excessive_sample_counts(samples: int) -> None:
    with pytest.raises(ValueError, match="samples"):
        run_live(Console(file=None), object(), samples=samples, interval=0.1)  # type: ignore[arg-type]


@pytest.mark.parametrize("interval", [0.0, -0.1, 10.1])
def test_live_rejects_nonpositive_or_excessive_intervals(interval: float) -> None:
    with pytest.raises(ValueError, match="interval"):
        run_live(Console(file=None), object(), samples=1, interval=interval)  # type: ignore[arg-type]


def test_interrupted_live_view_reports_cleanup_without_retaining_history() -> None:
    class InterruptedScanner:
        def read_group(self, group: str) -> tuple[LiveValue, ...]:
            assert group == "cruise"
            raise KeyboardInterrupt

    console = Console(record=True, width=180)

    assert run_live(console, InterruptedScanner(), samples=1, interval=0.1) == 130  # type: ignore[arg-type]
    output = console.export_text()
    assert "adapter was closed" in output
    assert "No diagnostic data was saved" in output


def test_scan_connection_error_gives_non_root_linux_permission_guidance() -> None:
    class FailedScanner:
        def scan_dtcs(self) -> StellantisScanResult:
            raise ELM327ConnectionError("could not open OBD adapter at /dev/ttyUSB0")

    console = Console(record=True, width=180)

    assert run_scan(console, FailedScanner()) == 1  # type: ignore[arg-type]
    output = console.export_text()
    assert "/dev/ttyUSB0" in output
    assert "dialout" in output
    assert "Do not run open-mechanic as root" in output
    assert "No diagnostic data was saved" in output


def test_scan_success_renders_result() -> None:
    class Scanner:
        def scan_dtcs(self) -> StellantisScanResult:
            return _scan_result()

    console = Console(record=True, width=180)

    assert run_scan(console, Scanner()) == 0  # type: ignore[arg-type]
    assert "Electric Power Steering" in console.export_text()


def test_live_collects_exact_finite_samples_and_waits_only_between_them() -> None:
    calls: list[str] = []
    value = LiveValue(
        "adaptive_cruise",
        "cruise_state",
        "Cruise state",
        None,
        None,
        None,
        datetime(2026, 8, 29, 12, 0, tzinfo=UTC),
        False,
        ModuleState.GATEWAY_BLOCKED,
        "community_unverified",
        "securityAccessDenied",
    )

    class Scanner:
        def read_group(self, group: str) -> tuple[LiveValue, ...]:
            calls.append(group)
            return (value,)

    console = Console(record=True, width=180)
    sleeps: list[float] = []

    assert (
        run_live(
            console,
            Scanner(),
            samples=2,
            interval=0.2,
            sleep=sleeps.append,  # type: ignore[arg-type]
        )
        == 0
    )
    assert calls == ["cruise", "cruise"]
    assert sleeps == [0.2]
    assert "securityAccessDenied" in console.export_text()


def test_driver_warning_is_printed_before_first_live_acquisition() -> None:
    events: list[str] = []

    class RecordingConsole(Console):
        def print(self, *objects: object, **kwargs: object) -> None:
            events.append(str(objects[0]))
            super().print(*objects, **kwargs)

    class Scanner:
        def read_group(self, group: str) -> tuple[LiveValue, ...]:
            events.append("read_group")
            return ()

    assert run_live(
        RecordingConsole(file=None), Scanner(), samples=1, interval=0.1  # type: ignore[arg-type]
    ) == 0
    assert "passenger or qualified technician" in events[0]
    assert events.index("read_group") > 0
