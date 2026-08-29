from __future__ import annotations

from datetime import datetime
from typing import Any

from open_mechanic.ai.diagnose import DiagnosisResult
from open_mechanic.api.schemas import DiagnoseRequest
from open_mechanic.api.services import DiagnosticAPIService, _default_connection
from open_mechanic.dtc import DTCCode
from open_mechanic.local_store import VehicleProfile
from open_mechanic.reader import SensorValue


class FakeRawConnection:
    def protocol_name(self) -> str:
        return "CAN"


class FakeConnection:
    def __init__(self, *, connects: bool = True) -> None:
        self.connects = connects
        self.disconnected = False

    def connect(self) -> bool:
        return self.connects

    def disconnect(self) -> None:
        self.disconnected = True

    def get_port(self) -> str:
        return "/dev/test"

    def get_connection(self) -> FakeRawConnection | None:
        if not self.connects:
            return None
        return FakeRawConnection()


class FakeSensorPoller:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    def get_snapshot(self) -> dict[str, SensorValue]:
        return {
            "RPM": SensorValue(
                name="RPM",
                value="750",
                unit="rpm",
                supported=True,
                timestamp=datetime(2026, 5, 22, 1, 2, 3),
            )
        }


class FakeDTCReader:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    def get_dtcs(self) -> list[DTCCode]:
        return [
            DTCCode(
                code="P0420",
                description="Catalyst system efficiency below threshold",
                status="confirmed",
                severity="warning",
                category="emissions",
            )
        ]


class FakeEngine:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, list[DTCCode], dict[str, Any], bool]] = []

    def diagnose(
        self,
        vehicle: Any,
        dtcs: list[DTCCode],
        sensor_snapshot: dict[str, Any],
        *,
        external_sharing_authorized: bool = False,
    ) -> DiagnosisResult:
        self.calls.append((vehicle, dtcs, sensor_snapshot, external_sharing_authorized))
        return DiagnosisResult(
            severity="warning",
            summary="Catalyst efficiency below threshold",
            likely_causes=["Cause A"],
            repair_steps=["Step A"],
            estimated_cost_usd={"low": 100, "high": 500},
            diy_feasible=False,
            diy_difficulty="moderate",
            urgency="soon",
            disclaimer="diagnostic disclaimer",
            dtc_codes=[dtc.code for dtc in dtcs],
            vehicle_str=f"{vehicle.year} {vehicle.make} {vehicle.model} ({vehicle.mileage:,} miles)",
            cached=False,
            timestamp=datetime(2026, 5, 22, 1, 2, 3),
        )


def test_vehicle_profile_reports_unconfigured_when_profile_missing() -> None:
    service = DiagnosticAPIService(profile_loader=lambda: None)

    profile = service.get_vehicle_profile()

    assert profile.configured is False
    assert profile.make is None


def test_vehicle_profile_maps_local_profile() -> None:
    service = DiagnosticAPIService(
        profile_loader=lambda: VehicleProfile(
            year=2018,
            make="Ford",
            model="F-150",
            mileage=85000,
        )
    )

    profile = service.get_vehicle_profile()

    assert profile.configured is True
    assert profile.year == 2018
    assert profile.model == "F-150"


def test_live_sensors_returns_empty_snapshot_when_adapter_unavailable() -> None:
    service = DiagnosticAPIService(connection_factory=lambda: FakeConnection(connects=False))

    snapshot = service.get_live_sensors()

    assert snapshot.connected is False
    assert snapshot.port == "/dev/test"
    assert snapshot.sensors == []
    assert snapshot.dtcs == []


def test_get_dtcs_returns_empty_list_when_adapter_unavailable() -> None:
    service = DiagnosticAPIService(connection_factory=lambda: FakeConnection(connects=False))

    assert service.get_dtcs() == []


def test_get_dtcs_maps_codes_and_disconnects(monkeypatch: Any) -> None:
    connection = FakeConnection()
    monkeypatch.setattr("open_mechanic.api.services.DTCReader", FakeDTCReader)
    service = DiagnosticAPIService(connection_factory=lambda: connection)

    dtcs = service.get_dtcs()

    assert dtcs[0].code == "P0420"
    assert connection.disconnected is True


def test_snapshot_returns_empty_snapshot_when_adapter_unavailable() -> None:
    service = DiagnosticAPIService(connection_factory=lambda: FakeConnection(connects=False))

    snapshot = service.get_snapshot()

    assert snapshot.connected is False
    assert snapshot.port == "/dev/test"
    assert snapshot.sensors == []
    assert snapshot.dtcs == []


def test_live_sensors_maps_sensor_values_and_disconnects(monkeypatch: Any) -> None:
    connection = FakeConnection()
    monkeypatch.setattr("open_mechanic.api.services.SensorPoller", FakeSensorPoller)
    service = DiagnosticAPIService(connection_factory=lambda: connection)

    snapshot = service.get_live_sensors()

    assert snapshot.connected is True
    assert snapshot.protocol == "CAN"
    assert snapshot.sensors[0].name == "RPM"
    assert connection.disconnected is True


def test_snapshot_combines_sensors_and_dtcs(monkeypatch: Any) -> None:
    connection = FakeConnection()
    monkeypatch.setattr("open_mechanic.api.services.SensorPoller", FakeSensorPoller)
    monkeypatch.setattr("open_mechanic.api.services.DTCReader", FakeDTCReader)
    service = DiagnosticAPIService(connection_factory=lambda: connection)

    snapshot = service.get_snapshot()

    assert snapshot.connected is True
    assert snapshot.sensors[0].value == "750"
    assert snapshot.dtcs[0].code == "P0420"
    assert connection.disconnected is True


def test_diagnose_passes_vehicle_snapshot_and_sharing_authorization(monkeypatch: Any) -> None:
    engine = FakeEngine()
    monkeypatch.setattr("open_mechanic.api.services.SensorPoller", FakeSensorPoller)
    monkeypatch.setattr("open_mechanic.api.services.DTCReader", FakeDTCReader)
    service = DiagnosticAPIService(
        connection_factory=lambda: FakeConnection(),
        engine_factory=lambda: engine,
    )

    result = service.diagnose(
        DiagnoseRequest(
            year=2018,
            make="Ford",
            model="F-150",
            mileage=85000,
            external_sharing_authorized=True,
        )
    )

    vehicle, dtcs, sensor_snapshot, sharing_authorized = engine.calls[0]
    assert result.summary == "Catalyst efficiency below threshold"
    assert vehicle.model == "F-150"
    assert dtcs[0].code == "P0420"
    assert sensor_snapshot["RPM"]["supported"] is True
    assert sharing_authorized is True


def test_default_connection_uses_api_tuned_timeout(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    class CapturingConnection:
        def __init__(self, *, timeout: float, max_retries: int) -> None:
            captured["timeout"] = timeout
            captured["max_retries"] = max_retries

    monkeypatch.setenv("OPEN_MECHANIC_API_OBD_TIMEOUT", "1.5")
    monkeypatch.setenv("OPEN_MECHANIC_API_OBD_RETRIES", "2")
    monkeypatch.setattr("open_mechanic.api.services.OBDConnection", CapturingConnection)

    _ = _default_connection()

    assert captured == {"timeout": 1.5, "max_retries": 2}
