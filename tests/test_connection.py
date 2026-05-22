from __future__ import annotations

from types import SimpleNamespace

import pytest

from open_mechanic import connection
from open_mechanic.connection import ConnectionStatus, OBDConnection, get_default_port, scan_ports


def test_default_ports_by_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(connection.platform, "system", lambda: "Linux")
    assert get_default_port() == "/dev/ttyUSB0"

    monkeypatch.setattr(connection.platform, "system", lambda: "Windows")
    assert get_default_port() == "COM3"

    monkeypatch.setattr(connection.platform, "system", lambda: "OtherOS")
    assert get_default_port() == "/dev/ttyUSB0"


def test_default_port_uses_first_macos_usbserial(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(connection.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        connection.glob,
        "glob",
        lambda pattern: ["/dev/cu.usbserial-A"] if pattern.startswith("/dev/cu") else [],
    )

    assert get_default_port() == "/dev/cu.usbserial-A"


def test_default_port_uses_macos_tty_fallbacks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(connection.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        connection.glob,
        "glob",
        lambda pattern: ["/dev/tty.usbserial-B"] if pattern.startswith("/dev/tty") else [],
    )

    assert get_default_port() == "/dev/tty.usbserial-B"

    monkeypatch.setattr(connection.glob, "glob", lambda pattern: [])
    assert get_default_port() == "/dev/cu.usbserial-0"


def test_scan_ports_by_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(connection.platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        connection.glob,
        "glob",
        lambda pattern: ["/dev/ttyUSB1"] if pattern == "/dev/ttyUSB*" else ["/dev/ttyACM0"],
    )
    assert scan_ports() == ["/dev/ttyACM0", "/dev/ttyUSB1"]

    monkeypatch.setattr(connection.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        connection.list_ports,
        "comports",
        lambda: [SimpleNamespace(device="COM4"), SimpleNamespace(device="COM3")],
    )
    assert scan_ports() == ["COM3", "COM4"]

    monkeypatch.setattr(connection.platform, "system", lambda: "OtherOS")
    assert scan_ports() == []


def test_connection_uses_env_port_and_protocol(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBD_PORT", "/dev/test")
    monkeypatch.setenv("OBD_PROTOCOL", "6")
    monkeypatch.setattr(connection, "scan_ports", lambda: [])

    obd_connection = OBDConnection()

    assert obd_connection.get_port() == "/dev/test"


def test_connect_success_and_disconnect(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeOBD:
        closed = False

        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def is_connected(self) -> bool:
            return True

        def protocol_name(self) -> str:
            return "CAN"

        def close(self) -> None:
            self.closed = True

    monkeypatch.setattr(connection.obd, "OBD", FakeOBD)
    obd_connection = OBDConnection(port="/dev/test", max_retries=1)

    assert obd_connection.connect() is True
    assert obd_connection.is_connected() is True
    assert obd_connection.get_status() is ConnectionStatus.CONNECTED

    raw_connection = obd_connection.get_connection()
    obd_connection.disconnect()

    assert raw_connection is not None
    assert raw_connection.closed is True
    assert obd_connection.get_status() is ConnectionStatus.DISCONNECTED


def test_connect_failure_sets_failed_status(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeOBD:
        def __init__(self, **kwargs: object) -> None:
            pass

        def is_connected(self) -> bool:
            return False

    monkeypatch.setattr(connection.obd, "OBD", FakeOBD)
    obd_connection = OBDConnection(port="/dev/test", max_retries=1)

    assert obd_connection.connect() is False
    assert obd_connection.get_status() is ConnectionStatus.FAILED


def test_connect_uses_progressive_retry_delays(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeOBD:
        def __init__(self, **kwargs: object) -> None:
            pass

        def is_connected(self) -> bool:
            return False

    delays: list[float] = []
    monkeypatch.setattr(connection.obd, "OBD", FakeOBD)
    monkeypatch.setattr(connection.time, "sleep", delays.append)

    assert OBDConnection(port="/dev/test", max_retries=4).connect() is False
    assert delays == [0.5, 1.0, 2.0]


def test_connect_retries_after_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0

    class FakeOBD:
        def __init__(self, **kwargs: object) -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("busy")

        def is_connected(self) -> bool:
            return True

        def protocol_name(self) -> str:
            return "CAN"

    monkeypatch.setattr(connection.obd, "OBD", FakeOBD)
    monkeypatch.setattr(connection.time, "sleep", lambda seconds: None)
    obd_connection = OBDConnection(port="/dev/test", max_retries=2)

    assert obd_connection.connect() is True
    assert attempts == 2


def test_connection_context_manager_disconnects(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeOBD:
        closed = False

        def __init__(self, **kwargs: object) -> None:
            pass

        def is_connected(self) -> bool:
            return True

        def protocol_name(self) -> str:
            return "CAN"

        def close(self) -> None:
            self.closed = True

    monkeypatch.setattr(connection.obd, "OBD", FakeOBD)

    with OBDConnection(port="/dev/test", max_retries=1) as obd_connection:
        raw_connection = obd_connection.get_connection()

    assert raw_connection is not None
    assert raw_connection.closed is True
