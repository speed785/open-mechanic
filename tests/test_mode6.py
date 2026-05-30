from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from open_mechanic import mode6
from open_mechanic.dtc import DTCCode
from open_mechanic.mode6 import Mode6Reader, Mode6TestResult, diagnose_misfires
from open_mechanic.reader import SensorValue


class _FakeCommand:
    def __init__(self, name: str, desc: str, pid: int, mode: int = 6) -> None:
        self.name = name
        self.desc = desc
        self.pid = pid
        self.mode = mode

    def __repr__(self) -> str:
        return self.name


class _FakeResponse:
    def __init__(self, value: object, null: bool = False) -> None:
        self.value = value
        self._null = null

    def is_null(self) -> bool:
        return self._null


class _FakeRawConnection:
    def __init__(
        self,
        supported_commands: set[object],
        responses: dict[object, _FakeResponse],
        fail: bool = False,
    ) -> None:
        self.supported_commands = supported_commands
        self.responses = responses
        self.fail = fail
        self.queries: list[object] = []

    def query(self, command: object) -> _FakeResponse:
        if self.fail:
            raise RuntimeError("boom")
        self.queries.append(command)
        return self.responses[command]


class _FakeConnectionWrapper:
    def __init__(self, raw_connection: object | None, connected: bool = True) -> None:
        self._raw_connection = raw_connection
        self._connected = connected

    def get_connection(self) -> object | None:
        return self._raw_connection

    def is_connected(self) -> bool:
        return self._connected


def _result(
    passed: bool | None = False, monitor: str = "MONITOR_MISFIRE_CYLINDER_2"
) -> Mode6TestResult:
    return Mode6TestResult(
        monitor=monitor,
        monitor_description="Misfire Cylinder 2 Data",
        category="misfire",
        test_id=1,
        test_name="Misfire counts",
        description="Misfire counts",
        value="12",
        minimum="0",
        maximum="5",
        unit="count",
        passed=passed,
        status="failed" if passed is False else "passed" if passed else "unknown",
    )


def test_reader_returns_empty_when_disconnected() -> None:
    assert Mode6Reader(_FakeConnectionWrapper(None, connected=False)).get_results() == []  # type: ignore[arg-type]


def test_reader_queries_supported_mode6_commands_in_pid_order(monkeypatch: Any) -> None:
    misfire = _FakeCommand("MONITOR_MISFIRE_CYLINDER_1", "Misfire Cylinder 1 Data", 162)
    catalyst = _FakeCommand("MONITOR_CATALYST_B1", "Catalyst Monitor Bank 1", 33)
    mids = _FakeCommand("MIDS_F", "Supported MIDs", 160)
    mode1 = _FakeCommand("MONITOR_NOT_MODE6", "Not Mode 6", 1, mode=1)
    test = SimpleNamespace(
        tid=1,
        name="Rich to lean sensor threshold",
        desc="O2 threshold",
        value=SimpleNamespace(magnitude=0.8, units="V"),
        min=SimpleNamespace(magnitude=0.1, units="V"),
        max=SimpleNamespace(magnitude=1.0, units="V"),
    )
    raw = _FakeRawConnection(
        {misfire, catalyst},
        {
            misfire: _FakeResponse(SimpleNamespace(tests=[test])),
            catalyst: _FakeResponse(SimpleNamespace(tests=[test])),
        },
    )
    monkeypatch.setattr(
        mode6.obd,
        "commands",
        SimpleNamespace(
            MONITOR_MISFIRE_CYLINDER_1=misfire,
            MONITOR_CATALYST_B1=catalyst,
            MIDS_F=mids,
            MONITOR_NOT_MODE6=mode1,
        ),
    )

    results = Mode6Reader(_FakeConnectionWrapper(raw)).get_results()  # type: ignore[arg-type]

    assert [item.monitor for item in results] == [
        "MONITOR_CATALYST_B1",
        "MONITOR_MISFIRE_CYLINDER_1",
    ]
    assert results[0].category == "catalyst"
    assert results[0].passed is True
    assert results[0].unit == "V"
    assert raw.queries == [catalyst, misfire]


def test_reader_can_limit_to_misfire_commands(monkeypatch: Any) -> None:
    misfire = _FakeCommand("MONITOR_MISFIRE_GENERAL", "Misfire Monitor General Data", 161)
    catalyst = _FakeCommand("MONITOR_CATALYST_B1", "Catalyst Monitor Bank 1", 33)
    raw = _FakeRawConnection(
        {misfire, catalyst},
        {
            misfire: _FakeResponse(SimpleNamespace(tests=[])),
            catalyst: _FakeResponse(SimpleNamespace(tests=[])),
        },
    )
    monkeypatch.setattr(
        mode6.obd,
        "commands",
        SimpleNamespace(MONITOR_MISFIRE_GENERAL=misfire, MONITOR_CATALYST_B1=catalyst),
    )

    results = Mode6Reader(_FakeConnectionWrapper(raw)).get_results(only_misfire=True)  # type: ignore[arg-type]

    assert [result.monitor for result in results] == ["MONITOR_MISFIRE_GENERAL"]
    assert results[0].status == "no tests"


def test_reader_skips_unsupported_monitor_commands(monkeypatch: Any) -> None:
    misfire = _FakeCommand("MONITOR_MISFIRE_GENERAL", "Misfire Monitor General Data", 161)
    raw = _FakeRawConnection(set(), {misfire: _FakeResponse(SimpleNamespace(tests=[]))})
    monkeypatch.setattr(mode6.obd, "commands", SimpleNamespace(MONITOR_MISFIRE_GENERAL=misfire))

    results = Mode6Reader(_FakeConnectionWrapper(raw)).get_results()  # type: ignore[arg-type]

    assert results == []
    assert raw.queries == []


def test_query_handles_null_response_and_query_error() -> None:
    command = _FakeCommand("MONITOR_EVAP_040", "EVAP Monitor", 59)
    null_conn = _FakeRawConnection({command}, {command: _FakeResponse(None, null=True)})
    failing_conn = _FakeRawConnection({command}, {}, fail=True)

    assert mode6._query_mode6_monitor(null_conn, command)[0].status == "no data"
    assert mode6._query_mode6_monitor(failing_conn, command)[0].status == "error: boom"


def test_result_from_test_handles_unknown_names_and_uncomparable_values() -> None:
    command = object()
    test = SimpleNamespace(tid="bad", value="bad", min=0, max=1)

    result = mode6._mode6_result_from_test(command, test)

    assert result.monitor == str(command)
    assert result.test_id is None
    assert result.test_name == "Unknown test"
    assert result.passed is None
    assert result.status == "unknown"


def test_diagnose_misfires_combines_mode6_dtc_and_sensor_findings() -> None:
    sensor = SensorValue("SHORT_FUEL_TRIM_1", "18.5", "%", SimpleNamespace(), True)  # type: ignore[arg-type]
    dtcs = [
        DTCCode("P0300", "Random misfire", "pending", "warning", "engine"),
        DTCCode("P0310", "Cylinder 10 misfire", "confirmed", "critical", "engine"),
    ]

    summary = diagnose_misfires(
        [_result(False)],
        dtcs,
        {"SHORT_FUEL_TRIM_1": sensor, "LONG_FUEL_TRIM_1": {"value": "-16", "supported": True}},
    )

    assert summary.supported is True
    assert summary.status == "confirmed_misfire"
    assert {finding.source for finding in summary.findings} == {"mode6", "dtc", "sensor"}
    assert any(finding.cylinder == 10 for finding in summary.findings)


def test_diagnose_misfires_reports_possible_watch_clean_and_no_data() -> None:
    possible = diagnose_misfires([_result(False)], [], {})
    watch = diagnose_misfires([], [], {"SHORT_FUEL_TRIM_1": "20"})
    clean = diagnose_misfires([_result(True)], [], {})
    no_data = diagnose_misfires([], [], {"SHORT_FUEL_TRIM_1": {"value": "99", "supported": False}})

    assert possible.status == "possible_misfire"
    assert watch.status == "watch"
    assert clean.status == "no_misfire_detected"
    assert no_data.status == "no_mode6_misfire_data"


def test_private_helpers_cover_category_and_conversion_branches(monkeypatch: Any) -> None:
    monkeypatch.setattr(mode6.obd, "commands", None)

    assert mode6._mode6_monitor_commands(only_misfire=False) == []
    marker = object()
    assert mode6._monitor_tests([marker]) == [marker]
    assert mode6._monitor_tests("not a monitor") == []
    assert mode6._format_measurement(None) == ("N/A", None)
    assert mode6._category_from_monitor("MONITOR_O2_B1S1") == "oxygen_sensor"
    assert mode6._category_from_monitor("MONITOR_EVAP_040") == "evap"
    assert mode6._category_from_monitor("MONITOR_EGR_B1") == "egr"
    assert mode6._category_from_monitor("MONITOR_FUEL_SYSTEM_B1") == "fuel"
    assert mode6._category_from_monitor("MONITOR_BOOST_PRESSURE_B1") == "boost"
    assert mode6._category_from_monitor("MONITOR_UNKNOWN") == "other"
    assert mode6._cylinder_from_dtc("P0300") is None
    assert mode6._cylinder_from_dtc("P0308") == 8
    assert mode6._cylinder_from_dtc("P0201") is None
    assert mode6._cylinder_from_monitor("MONITOR_MISFIRE_GENERAL") is None
    assert mode6._sensor_float({"RPM": {"value": "bad"}}, "RPM") is None
    assert mode6._sensor_float({"RPM": SimpleNamespace(value="12", supported=False)}, "RPM") is None
    assert mode6._coerce_float(True) is None
    assert mode6._coerce_float(object()) is None
    assert mode6._status_from_passed(False) == "failed"
