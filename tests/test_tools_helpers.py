from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from io import StringIO
from types import SimpleNamespace

import pytest
from rich.console import Console

from open_mechanic import tools
from open_mechanic.dtc import DTCCode
from open_mechanic.local_store import VehicleProfile
from open_mechanic.protocols.elm327 import ELM327ConnectionError
from open_mechanic.reader import SensorValue


@dataclass
class _Response:
    value: object
    null: bool = False

    def is_null(self) -> bool:
        return self.null


def test_format_response_handles_null_none_and_units() -> None:
    assert tools._format_response(None) == ("N/A", "")
    assert tools._format_response(_Response(None)) == ("N/A", "")
    assert tools._format_response(_Response(SimpleNamespace(magnitude=12.345, units="V"))) == (
        "12.35",
        "V",
    )


def test_parse_float_returns_none_for_invalid_value() -> None:
    assert tools._parse_float("12.5") == 12.5
    assert tools._parse_float("N/A") is None


def test_sensor_payload_and_history_helpers() -> None:
    snapshot = {
        "RPM": SensorValue("RPM", "750", "rpm", datetime(2026, 5, 22, 1, 2, 3), True),
        "SPEED": SensorValue("SPEED", "N/A", None, datetime(2026, 5, 22, 1, 2, 3), False),
    }
    history = {"RPM": []}

    assert tools._sensor_payload(snapshot)["RPM"]["timestamp"] == "2026-05-22T01:02:03"
    tools._update_sensor_history(history, snapshot, max_points=1)

    assert history["RPM"] == [750.0]

    snapshot["RPM"] = SensorValue("RPM", "bad", "rpm", datetime(2026, 5, 22), True)
    tools._update_sensor_history(history, snapshot, max_points=1)
    assert history["RPM"] == [750.0]

    snapshot["RPM"] = SensorValue("RPM", "1000", "rpm", datetime(2026, 5, 22), True)
    tools._update_sensor_history(history, snapshot, max_points=1)
    assert history["RPM"] == [1000.0]


def test_graph_helpers_render_values() -> None:
    assert tools._graph_range("RPM", [750.0]) == (0.0, 7000.0)
    assert tools._bar_gauge(5.0, 0.0, 10.0, width=4) == "##-- 0..10"
    assert tools._history_line([0.0, 5.0, 10.0], 0.0, 10.0)
    assert tools._history_line([], 0.0, 10.0) == ""
    assert tools._history_line([1.0, 2.0], 1.0, 1.0) == "__"


def test_yes_no_and_supported_count_helpers() -> None:
    assert tools._yes_no(True) == "yes"
    assert tools._yes_no(False) == "no"
    assert tools._yes_no(None) == "unknown"
    assert tools._supported_count(None) == 0
    assert tools._supported_count(SimpleNamespace(supported_commands={1, 2, 3})) == 3


def test_read_number_selection_handles_valid_and_invalid_input(monkeypatch) -> None:
    monkeypatch.setattr(tools.sys.stdin, "isatty", lambda: False)

    assert tools._read_number_selection("2", 5, 0) == 1
    assert tools._read_number_selection("9", 5, 2) == 2


def test_read_number_selection_reads_second_digit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tools.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(tools, "_read_key_timeout", lambda: "2")

    assert tools._read_number_selection("1", 12, 0) == 11


def test_read_number_selection_handles_timeout_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tools.sys.stdin, "isatty", lambda: True)

    def fail_timeout() -> str:
        raise OSError

    monkeypatch.setattr(tools, "_read_key_timeout", fail_timeout)

    assert tools._read_number_selection("1", 12, 0) == 0


def test_main_dispatches_profile_command(monkeypatch: pytest.MonkeyPatch) -> None:
    profile = VehicleProfile(2018, "Ford", "F-150")
    calls: list[object] = []
    monkeypatch.setattr(tools, "prompt_vehicle_profile", lambda console: profile)
    monkeypatch.setattr(tools, "show_profile", lambda console, profile=None: calls.append(profile))

    assert tools.main(["profile"]) == 0
    assert calls == [profile]


def test_main_dispatches_menu_and_direct_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tools, "run_tools_menu", lambda args, console: 3)
    monkeypatch.setattr(tools, "run_direct_tool", lambda command, args, console: 4)

    assert tools.main([]) == 3
    assert tools.main(["dtcs"]) == 4


def test_main_tools_command_dispatches_menu(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tools, "run_tools_menu", lambda args, console: 6)

    assert tools.main(["tools"]) == 6


def test_main_dispatches_bounded_stellantis_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[argparse.Namespace] = []
    monkeypatch.setattr(
        tools, "run_stellantis_command", lambda args, console: captured.append(args) or 7
    )

    assert (
        tools.main(
            [
                "stellantis-scan",
                "--vehicle",
                "wrangler_jl_4xe_2024",
                "--port",
                "/dev/test",
            ]
        )
        == 7
    )
    assert (
        tools.main(
            [
                "stellantis-live",
                "--vehicle",
                "wrangler_jl_4xe_2024",
                "--group",
                "cruise",
                "--samples",
                "2",
                "--interval",
                "0.2",
            ]
        )
        == 7
    )
    assert captured[0].vehicle == "wrangler_jl_4xe_2024"
    assert captured[1].samples == 2


def test_stellantis_live_cli_requires_explicit_finite_samples() -> None:
    with pytest.raises(SystemExit) as error:
        tools.main(
            [
                "stellantis-live",
                "--vehicle",
                "wrangler_jl_4xe_2024",
                "--group",
                "cruise",
            ]
        )

    assert error.value.code == 2


def test_stellantis_command_builds_catalog_scanner_and_dispatches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = object()
    transport = object()
    scanner = object()
    monkeypatch.setattr(tools, "load_catalog", lambda name: catalog)
    monkeypatch.setattr(
        tools,
        "ELM327Transport",
        lambda port, timeout: transport if (port, timeout) == ("/dev/test", 2.0) else None,
    )
    monkeypatch.setattr(
        tools, "StellantisScanner", lambda actual_transport, actual_catalog: scanner
    )
    monkeypatch.setattr(tools, "run_scan", lambda console, actual_scanner: 4)

    result = tools.run_stellantis_command(
        argparse.Namespace(
            command="stellantis-scan",
            vehicle="wrangler_jl_4xe_2024",
            port="/dev/test",
            timeout=2.0,
        ),
        Console(file=None),
    )

    assert result == 4


def test_stellantis_live_command_passes_finite_bounds_and_reports_permission_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tools, "load_catalog", lambda name: object())
    monkeypatch.setattr(tools, "ELM327Transport", lambda port, timeout: object())
    monkeypatch.setattr(tools, "StellantisScanner", lambda transport, catalog: object())

    def fail(*args: object, **kwargs: object) -> int:
        assert kwargs["samples"] == 2
        assert kwargs["interval"] == 0.2
        raise ELM327ConnectionError("could not open /dev/test")

    monkeypatch.setattr(tools, "run_live", fail)
    console = Console(record=True)

    result = tools.run_stellantis_command(
        argparse.Namespace(
            command="stellantis-live",
            vehicle="wrangler_jl_4xe_2024",
            port="/dev/test",
            timeout=1.0,
            samples=2,
            interval=0.2,
        ),
        console,
    )

    assert result == 1
    assert "dialout" in console.export_text()


def test_run_tools_menu_handles_quit_profile_and_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    console = Console(file=None)
    profile = VehicleProfile(2018, "Ford", "F-150")
    args = argparse.Namespace()
    selections = iter([0, 1, 6])
    called: list[str] = []
    monkeypatch.setattr(
        tools, "_select_menu_item", lambda console, profile, selected: next(selections)
    )
    monkeypatch.setattr(tools, "prompt_vehicle_profile", lambda console: profile)
    monkeypatch.setattr(
        tools, "show_profile", lambda console, profile=None: called.append("profile")
    )
    monkeypatch.setattr(
        tools,
        "run_direct_tool",
        lambda tool_name, args, console, profile=None: called.append(tool_name) or 0,
    )
    monkeypatch.setattr(tools.Prompt, "ask", lambda *args, **kwargs: "")

    assert tools.run_tools_menu(args, console) == 0
    assert called == ["profile", "sensors"]


def test_run_tools_menu_prompts_for_missing_profile_and_returns_tool_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    console = Console(file=None)
    profile = VehicleProfile(2018, "Ford", "F-150")
    args = argparse.Namespace()
    monkeypatch.setattr(tools, "_select_menu_item", lambda console, profile, selected: 1)
    monkeypatch.setattr(tools, "prompt_vehicle_profile", lambda console: profile)
    monkeypatch.setattr(tools, "run_direct_tool", lambda *args, **kwargs: 9)

    assert tools.run_tools_menu(args, console) == 9


def test_prompt_menu_item_handles_quit_and_number(monkeypatch: pytest.MonkeyPatch) -> None:
    console = Console(file=None)
    monkeypatch.setattr(tools.Prompt, "ask", lambda *args, **kwargs: "q")
    assert tools._prompt_menu_item(console, None) == len(tools.MENU_ITEMS) - 1

    monkeypatch.setattr(tools.Prompt, "ask", lambda *args, **kwargs: "2")
    assert tools._prompt_menu_item(console, None) == 1


def test_select_menu_item_uses_prompt_when_not_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    console = Console(file=None)
    monkeypatch.setattr(tools.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(tools, "_prompt_menu_item", lambda console, profile: 5)

    assert tools._select_menu_item(console, None, 1) == 5


@pytest.mark.parametrize(
    ("keys", "expected"),
    [
        (["down", "enter"], 2),
        (["up", "q"], len(tools.MENU_ITEMS) - 1),
        (["3"], 2),
    ],
)
def test_select_menu_item_tty_navigation(
    keys: list[str], expected: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    console = Console(file=None)
    key_iter = iter(keys)
    monkeypatch.setattr(tools.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(tools, "_read_key", lambda: next(key_iter))
    monkeypatch.setattr(tools, "scan_ports", lambda: [])

    assert tools._select_menu_item(console, None, 1) == expected


def test_select_from_list_tty_up_and_invalid_number_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    console = Console(file=None)
    keys = iter(["up", "1", "enter"])
    monkeypatch.setattr(tools.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(tools, "_read_key", lambda: next(keys))
    monkeypatch.setattr(tools, "_read_number_selection", lambda first, count, current: None)

    assert tools._select_from_list(console, "Title", ["A", "B"]) == "A"


def test_prompt_vehicle_profile_keeps_profile_in_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    console = Console(file=None)
    monkeypatch.setattr(tools.IntPrompt, "ask", lambda *args, **kwargs: 2018)
    monkeypatch.setattr(tools, "select_vehicle_make", lambda console: "Ford")
    answers = iter(["F-150", "85000"])
    monkeypatch.setattr(tools.Prompt, "ask", lambda *args, **kwargs: next(answers))

    profile = tools.prompt_vehicle_profile(console)

    assert profile == VehicleProfile(2018, "Ford", "F-150", 85000)


def test_select_vehicle_make_prompts_for_other(monkeypatch: pytest.MonkeyPatch) -> None:
    console = Console(file=None)
    monkeypatch.setattr(tools, "_select_from_list", lambda console, title, options: "Other")
    monkeypatch.setattr(tools.Prompt, "ask", lambda *args, **kwargs: "Saab")

    assert tools.select_vehicle_make(console) == "Saab"


def test_select_vehicle_make_returns_known_make(monkeypatch: pytest.MonkeyPatch) -> None:
    console = Console(file=None)
    monkeypatch.setattr(tools, "_select_from_list", lambda console, title, options: "Ford")

    assert tools.select_vehicle_make(console) == "Ford"


def test_select_from_list_non_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    console = Console(file=None)
    monkeypatch.setattr(tools.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(tools.Prompt, "ask", lambda *args, **kwargs: "2")

    assert tools._select_from_list(console, "Title", ["A", "B"]) == "B"


def test_select_from_list_tty_navigation(monkeypatch: pytest.MonkeyPatch) -> None:
    console = Console(file=None)
    keys = iter(["down", "enter"])
    monkeypatch.setattr(tools.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(tools, "_read_key", lambda: next(keys))

    assert tools._select_from_list(console, "Title", ["A", "B"]) == "B"


def test_select_from_list_tty_digit_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    console = Console(file=None)
    keys = iter(["9", "2"])
    monkeypatch.setattr(tools.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(tools, "_read_key", lambda: next(keys))

    assert tools._select_from_list(console, "Title", ["A", "B"]) == "A"


class _FakeStdin(StringIO):
    def fileno(self) -> int:
        return 0

    def isatty(self) -> bool:
        return True


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("\x1b[A", "up"),
        ("\x1b[B", "down"),
        ("\x1b[C", "escape"),
        ("\n", "enter"),
        ("Q", "q"),
    ],
)
def test_read_key(monkeypatch: pytest.MonkeyPatch, raw: str, expected: str) -> None:
    monkeypatch.setattr(tools.sys, "stdin", _FakeStdin(raw))
    monkeypatch.setattr("termios.tcgetattr", lambda fd: "old")
    monkeypatch.setattr("termios.tcsetattr", lambda fd, when, settings: None)
    monkeypatch.setattr("tty.setraw", lambda fd: None)

    assert tools._read_key() == expected


def test_read_key_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tools.sys, "stdin", _FakeStdin("z"))
    monkeypatch.setattr("termios.tcgetattr", lambda fd: "old")
    monkeypatch.setattr("termios.tcsetattr", lambda fd, when, settings: None)
    monkeypatch.setattr("tty.setraw", lambda fd: None)
    monkeypatch.setattr("select.select", lambda read, write, error, timeout: (read, [], []))

    assert tools._read_key_timeout() == "z"

    monkeypatch.setattr("select.select", lambda read, write, error, timeout: ([], [], []))
    assert tools._read_key_timeout() == ""


def test_show_profile_renders_missing_and_present_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    console = Console(record=True)

    tools.show_profile(console)
    tools.show_profile(console, VehicleProfile(2018, "Ford", "F-150", 85000))

    output = console.export_text()
    assert "not set" in output
    assert "2018 Ford F-150" in output


class _FakeToolConnection:
    def __init__(self, connected: bool = True) -> None:
        self.connected = connected
        self.disconnected = False
        self.raw = SimpleNamespace(
            supported_commands={1, 2},
            protocol_name=lambda: "CAN",
        )

    def connect(self) -> bool:
        return self.connected

    def disconnect(self) -> None:
        self.disconnected = True

    def get_connection(self) -> object:
        return self.raw

    def get_port(self) -> str:
        return "/dev/test"


class _FakeSessionLog:
    def __init__(self, tool_name: str, profile: VehicleProfile | None) -> None:
        self.path = "session.jsonl"
        self.rows: list[tuple[str, dict[str, object]]] = []

    def write(self, event: str, payload: dict[str, object]) -> None:
        self.rows.append((event, payload))


@pytest.mark.parametrize(
    ("tool_name", "patched_name"),
    [
        ("sensors", "show_live_sensors"),
        ("dtcs", "show_dtcs"),
        ("readiness", "show_readiness"),
        ("freeze-frame", "show_freeze_frame"),
        ("snapshot", "show_health_snapshot"),
    ],
)
def test_run_direct_tool_dispatches_tool(
    tool_name: str, patched_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    console = Console(file=None)
    args = argparse.Namespace(port=None, protocol=None, baudrate=115200, timeout=1, samples=1)
    calls: list[str] = []
    fake_connection = _FakeToolConnection()
    monkeypatch.setattr(tools, "OBDConnection", lambda **kwargs: fake_connection)
    monkeypatch.setattr(tools, "scan_ports", lambda: [])
    monkeypatch.setattr(tools, patched_name, lambda *args, **kwargs: calls.append(patched_name))

    assert (
        tools.run_direct_tool(
            tool_name, args, console, profile=VehicleProfile(2018, "Ford", "F-150")
        )
        == 0
    )
    assert calls == [patched_name]
    assert fake_connection.disconnected is True


def test_run_direct_tool_handles_connection_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    console = Console(file=None)
    args = argparse.Namespace(port=None, protocol=None, baudrate=115200, timeout=1)
    monkeypatch.setattr(tools, "OBDConnection", lambda **kwargs: _FakeToolConnection(False))
    monkeypatch.setattr(tools, "scan_ports", lambda: [])

    assert (
        tools.run_direct_tool("dtcs", args, console, profile=VehicleProfile(2018, "Ford", "F-150"))
        == 1
    )


def test_run_direct_tool_returns_error_for_unknown_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    console = Console(file=None)
    args = argparse.Namespace(port=None, protocol=None, baudrate=115200, timeout=1)
    monkeypatch.setattr(tools, "OBDConnection", lambda **kwargs: _FakeToolConnection(True))
    monkeypatch.setattr(tools, "scan_ports", lambda: [])

    assert (
        tools.run_direct_tool(
            "bad-tool", args, console, profile=VehicleProfile(2018, "Ford", "F-150")
        )
        == 2
    )


def test_run_direct_tool_prompts_for_missing_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    console = Console(file=None)
    args = argparse.Namespace(port=None, protocol=None, baudrate=115200, timeout=1)
    profile = VehicleProfile(2018, "Ford", "F-150")
    called: list[str] = []
    monkeypatch.setattr(tools, "prompt_vehicle_profile", lambda console: profile)
    monkeypatch.setattr(tools, "OBDConnection", lambda **kwargs: _FakeToolConnection(True))
    monkeypatch.setattr(tools, "scan_ports", lambda: [])
    monkeypatch.setattr(tools, "show_dtcs", lambda *args, **kwargs: called.append("dtcs"))

    assert tools.run_direct_tool("dtcs", args, console) == 0
    assert called == ["dtcs"]


def test_query_named_commands_formats_supported_unsupported_and_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ok_command = object()
    unsupported_command = object()
    error_command = object()
    monkeypatch.setattr(
        tools.obd,
        "commands",
        SimpleNamespace(OK=ok_command, UNSUPPORTED=unsupported_command, ERROR=error_command),
    )

    def query(command: object) -> _Response:
        if command is error_command:
            raise RuntimeError("boom")
        return _Response(SimpleNamespace(magnitude=12.0, units="V"))

    conn = SimpleNamespace(supported_commands={ok_command, error_command}, query=query)

    rows = tools._query_named_commands(conn, ["OK", "UNSUPPORTED", "ERROR", "MISSING"])

    assert [row["status"] for row in rows] == ["ok", "unsupported", "error: boom"]


def test_readiness_rows_handles_status_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    command = object()
    payload = SimpleNamespace(
        MIL=False,
        DTC_count=0,
        ignition_type="spark",
        catalyst=SimpleNamespace(name="Catalyst", available=True, complete=False),
    )
    conn = SimpleNamespace(
        supported_commands={command},
        query=lambda command: _Response(payload),
    )

    rows = tools._readiness_rows(conn, "STATUS", command)

    assert {"source": "STATUS", "monitor": "MIL", "available": True, "complete": True} in rows
    assert {
        "source": "STATUS",
        "monitor": "Catalyst",
        "available": True,
        "complete": False,
    } in rows


def test_show_dtcs_renders_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    console = Console(record=True)
    monkeypatch.setattr(
        tools,
        "DTCReader",
        lambda connection: SimpleNamespace(
            get_dtcs=lambda: [DTCCode("P0420", "Catalyst", "confirmed", "warning", "emissions")]
        ),
    )

    tools.show_dtcs(console, object())  # type: ignore[arg-type]

    assert "P0420" in console.export_text()


def test_show_dtcs_renders_empty_state(monkeypatch: pytest.MonkeyPatch) -> None:
    console = Console(record=True)
    monkeypatch.setattr(tools, "DTCReader", lambda connection: SimpleNamespace(get_dtcs=lambda: []))

    tools.show_dtcs(console, object())  # type: ignore[arg-type]

    assert "No current or confirmed fault codes reported" in console.export_text()


def test_show_readiness_renders_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    console = Console(record=True)
    command = object()
    monkeypatch.setattr(tools, "READINESS_COMMANDS", ["STATUS"])
    monkeypatch.setattr(tools.obd, "commands", SimpleNamespace(STATUS=command))
    monkeypatch.setattr(
        tools,
        "_readiness_rows",
        lambda conn, source, command: [
            {"source": source, "monitor": "MIL", "available": True, "complete": False}
        ],
    )
    connection = SimpleNamespace(get_connection=lambda: SimpleNamespace())

    tools.show_readiness(console, connection)  # type: ignore[arg-type]

    assert "MIL" in console.export_text()


def test_show_readiness_renders_empty_state(monkeypatch: pytest.MonkeyPatch) -> None:
    console = Console(record=True)
    monkeypatch.setattr(tools, "READINESS_COMMANDS", [])
    connection = SimpleNamespace(get_connection=lambda: SimpleNamespace())

    tools.show_readiness(console, connection)  # type: ignore[arg-type]

    assert "No readiness data reported" in console.export_text()


def test_show_readiness_skips_missing_command(monkeypatch: pytest.MonkeyPatch) -> None:
    console = Console(record=True)
    monkeypatch.setattr(tools, "READINESS_COMMANDS", ["MISSING"])
    monkeypatch.setattr(tools.obd, "commands", SimpleNamespace())
    connection = SimpleNamespace(get_connection=lambda: SimpleNamespace())

    tools.show_readiness(console, connection)  # type: ignore[arg-type]

    assert "No readiness data reported" in console.export_text()


def test_show_freeze_frame_renders_rows_and_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    console = Console(record=True)
    connection = SimpleNamespace(get_connection=lambda: SimpleNamespace())
    monkeypatch.setattr(
        tools,
        "_query_named_commands",
        lambda conn, commands: [{"label": "RPM", "value": "750", "unit": "rpm", "status": "ok"}],
    )
    tools.show_freeze_frame(console, connection)  # type: ignore[arg-type]
    assert "RPM" in console.export_text()

    console = Console(record=True)
    monkeypatch.setattr(tools, "_query_named_commands", lambda conn, commands: [])
    tools.show_freeze_frame(console, connection)  # type: ignore[arg-type]
    assert "No supported freeze-frame PIDs reported" in console.export_text()


def test_show_health_snapshot_renders_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    console = Console(record=True)
    status_command = object()
    connection = SimpleNamespace(get_connection=lambda: SimpleNamespace())
    monkeypatch.setattr(
        tools,
        "_query_named_commands",
        lambda conn, commands: [{"label": "RPM", "value": "750", "unit": "rpm", "status": "ok"}],
    )
    monkeypatch.setattr(
        tools,
        "DTCReader",
        lambda connection: SimpleNamespace(
            get_dtcs=lambda: [DTCCode("P0420", "Catalyst", "confirmed", "warning", "emissions")]
        ),
    )
    monkeypatch.setattr(tools.obd, "commands", SimpleNamespace(STATUS=status_command))
    monkeypatch.setattr(
        tools,
        "_readiness_rows",
        lambda conn, source, command: [
            {"source": source, "monitor": "MIL", "available": True, "complete": False}
        ],
    )

    tools.show_health_snapshot(console, connection)  # type: ignore[arg-type]

    assert "Fault codes" in console.export_text()


def test_show_live_sensors_captures_one_sample(monkeypatch: pytest.MonkeyPatch) -> None:
    console = Console(file=None)
    snapshot = {"RPM": SensorValue("RPM", "750", "rpm", datetime(2026, 5, 22, 1, 2, 3), True)}

    class FakePoller:
        def __init__(self, connection: object, interval: float) -> None:
            pass

        def get_snapshot(self) -> dict[str, SensorValue]:
            return snapshot

    class FakeLive:
        def __init__(self, **kwargs: object) -> None:
            self.updated: list[object] = []

        def __enter__(self) -> FakeLive:
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def update(self, renderable: object) -> None:
            self.updated.append(renderable)

    monkeypatch.setattr(tools, "SensorPoller", FakePoller)
    monkeypatch.setattr(tools, "Live", FakeLive)
    monkeypatch.setattr(tools.time, "sleep", lambda seconds: None)

    tools.show_live_sensors(console, object(), samples=1, interval=0, show_graphs=False)  # type: ignore[arg-type]


def test_show_live_sensors_with_graphs_and_keyboard_interrupt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    console = Console(record=True)
    snapshot = {"RPM": SensorValue("RPM", "750", "rpm", datetime(2026, 5, 22, 1, 2, 3), True)}

    class FakePoller:
        def __init__(self, connection: object, interval: float) -> None:
            pass

        def get_snapshot(self) -> dict[str, SensorValue]:
            raise KeyboardInterrupt

    class FakeLive:
        def __init__(self, **kwargs: object) -> None:
            pass

        def __enter__(self) -> FakeLive:
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def update(self, renderable: object) -> None:
            pass

    monkeypatch.setattr(tools, "SensorPoller", FakePoller)
    monkeypatch.setattr(tools, "Live", FakeLive)
    tools.show_live_sensors(console, object(), samples=1, show_graphs=True)  # type: ignore[arg-type]
    assert "Stopped live sensors" in console.export_text()

    class OneSamplePoller:
        def __init__(self, connection: object, interval: float) -> None:
            pass

        def get_snapshot(self) -> dict[str, SensorValue]:
            return snapshot

    monkeypatch.setattr(tools, "SensorPoller", OneSamplePoller)
    monkeypatch.setattr(tools.time, "sleep", lambda seconds: None)
    tools.show_live_sensors(Console(file=None), object(), samples=1, show_graphs=True)  # type: ignore[arg-type]


def test_sensor_tables_and_graph_empty_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tools, "SENSOR_COMMANDS", ["RPM"])
    table = tools._sensor_table({}, "Sensors")
    assert table.row_count == 1

    graph = tools._sensor_graph_table({})
    assert graph.row_count == 1


def test_more_graph_helper_branches() -> None:
    assert tools._graph_range("UNKNOWN", [5.0]) == (4.0, 6.0)
    assert tools._graph_range("UNKNOWN", [1.0, 4.0]) == (1.0, 4.0)
    assert tools._bar_gauge(1.0, 1.0, 1.0, width=3) == "---"


def test_readiness_rows_handles_unsupported_exception_and_empty_response() -> None:
    command = object()
    unsupported_conn = SimpleNamespace(supported_commands=set())
    assert tools._readiness_rows(unsupported_conn, "STATUS", command) == [
        {"source": "STATUS", "monitor": "command", "available": False, "complete": False}
    ]

    failing_conn = SimpleNamespace(
        supported_commands={command}, query=lambda command: (_ for _ in ()).throw(RuntimeError())
    )
    assert tools._readiness_rows(failing_conn, "STATUS", command) == []

    empty_conn = SimpleNamespace(
        supported_commands={command}, query=lambda command: _Response(None, null=True)
    )
    assert tools._readiness_rows(empty_conn, "STATUS", command) == []


def test_require_raw_connection_raises_without_connection() -> None:
    with pytest.raises(RuntimeError, match="not active"):
        tools._require_raw_connection(SimpleNamespace(get_connection=lambda: None))  # type: ignore[arg-type]


def test_header_includes_profile_and_ports(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tools, "scan_ports", lambda: ["/dev/test"])

    panel = tools._header(VehicleProfile(2018, "Ford", "F-150", 85000))

    assert "2018 Ford F-150" in str(panel.renderable)
    assert "/dev/test" in str(panel.renderable)
