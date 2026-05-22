from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any

from open_mechanic.reader import SensorPoller


class _FakeConnectionWrapper:
    def __init__(self, raw_connection: object | None) -> None:
        self._raw_connection = raw_connection

    def get_connection(self) -> object | None:
        return self._raw_connection


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
        response: _FakeResponse | None = None,
        fail: bool = False,
    ) -> None:
        self.supported_commands = supported_commands
        self.response = response or _FakeResponse(SimpleNamespace(magnitude=750.0, units="rpm"))
        self.fail = fail
        self.queries: list[object] = []

    def is_connected(self) -> bool:
        return True

    def query(self, command: object) -> _FakeResponse:
        if self.fail:
            raise RuntimeError("boom")
        self.queries.append(command)
        return self.response


def test_sensor_poller_uses_attribute_lookup_for_command_registry(monkeypatch: Any) -> None:
    rpm_command = object()
    fake_commands = SimpleNamespace(RPM=rpm_command)
    fake_raw_connection = _FakeRawConnection({rpm_command})
    poller = SensorPoller(_FakeConnectionWrapper(fake_raw_connection))  # type: ignore[arg-type]
    monkeypatch.setattr("open_mechanic.reader.obd.commands", fake_commands)
    monkeypatch.setattr("open_mechanic.reader.SENSOR_COMMANDS", ["RPM", "SPEED"])

    snapshot = poller.get_snapshot()

    assert snapshot["RPM"].supported is True
    assert snapshot["RPM"].value == "750.00"
    assert "SPEED" not in snapshot
    assert fake_raw_connection.queries == [rpm_command]


def test_sensor_poller_returns_empty_without_connection() -> None:
    poller = SensorPoller(_FakeConnectionWrapper(None))  # type: ignore[arg-type]

    assert poller.get_snapshot() == {}


def test_sensor_poller_marks_unsupported_command(monkeypatch: Any) -> None:
    rpm_command = object()
    fake_raw_connection = _FakeRawConnection(set())
    poller = SensorPoller(_FakeConnectionWrapper(fake_raw_connection))  # type: ignore[arg-type]
    monkeypatch.setattr("open_mechanic.reader.obd.commands", SimpleNamespace(RPM=rpm_command))
    monkeypatch.setattr("open_mechanic.reader.SENSOR_COMMANDS", ["RPM"])

    snapshot = poller.get_snapshot()

    assert snapshot["RPM"].supported is False
    assert snapshot["RPM"].value == "N/A"
    assert fake_raw_connection.queries == []


def test_sensor_poller_marks_null_response_as_unsupported(monkeypatch: Any) -> None:
    rpm_command = object()
    fake_raw_connection = _FakeRawConnection({rpm_command}, response=_FakeResponse(None, null=True))
    poller = SensorPoller(_FakeConnectionWrapper(fake_raw_connection))  # type: ignore[arg-type]
    monkeypatch.setattr("open_mechanic.reader.obd.commands", SimpleNamespace(RPM=rpm_command))
    monkeypatch.setattr("open_mechanic.reader.SENSOR_COMMANDS", ["RPM"])

    snapshot = poller.get_snapshot()

    assert snapshot["RPM"].supported is False
    assert snapshot["RPM"].value == "N/A"


def test_sensor_poller_marks_query_exception_as_unsupported(monkeypatch: Any) -> None:
    rpm_command = object()
    fake_raw_connection = _FakeRawConnection({rpm_command}, fail=True)
    poller = SensorPoller(_FakeConnectionWrapper(fake_raw_connection))  # type: ignore[arg-type]
    monkeypatch.setattr("open_mechanic.reader.obd.commands", SimpleNamespace(RPM=rpm_command))
    monkeypatch.setattr("open_mechanic.reader.SENSOR_COMMANDS", ["RPM"])

    snapshot = poller.get_snapshot()

    assert snapshot["RPM"].supported is False


def test_sensor_poller_start_and_stop_polling(monkeypatch: Any) -> None:
    poller = SensorPoller(_FakeConnectionWrapper(None), interval=0.01)  # type: ignore[arg-type]
    snapshots: list[dict[str, object]] = []
    monkeypatch.setattr(poller, "get_snapshot", lambda: {})

    poller.start_polling(snapshots.append)
    for _ in range(20):
        if snapshots:
            break
        time.sleep(0.01)
    poller.stop_polling()

    assert poller.is_polling() is False
    assert snapshots


def test_sensor_poller_start_polling_is_idempotent(monkeypatch: Any) -> None:
    poller = SensorPoller(_FakeConnectionWrapper(None), interval=0.01)  # type: ignore[arg-type]
    monkeypatch.setattr(poller, "get_snapshot", lambda: {})
    poller.start_polling(lambda snapshot: None)
    first_thread = poller._thread
    poller.start_polling(lambda snapshot: None)
    poller.stop_polling()

    assert first_thread is not None
    assert poller._thread is first_thread
