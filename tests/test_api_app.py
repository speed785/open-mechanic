from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient

from open_mechanic.api import create_app
from open_mechanic.api.schemas import (
    DiagnoseRequest,
    DiagnosisResponse,
    DTCResponse,
    HealthSnapshotResponse,
    Mode6TestResponse,
    SensorReadingResponse,
    VehicleProfileResponse,
)


class FakeService:
    def __init__(self) -> None:
        self.diagnose_requests: list[DiagnoseRequest] = []

    def get_vehicle_profile(self) -> VehicleProfileResponse:
        return VehicleProfileResponse(
            configured=True,
            year=2018,
            make="Ford",
            model="F-150",
            mileage=85000,
        )

    def get_live_sensors(self) -> HealthSnapshotResponse:
        return HealthSnapshotResponse(
            connected=True,
            port="/dev/test",
            protocol="CAN",
            sensors=[
                SensorReadingResponse(
                    name="RPM",
                    value="750",
                    unit="rpm",
                    supported=True,
                    timestamp=datetime(2026, 5, 22, 1, 2, 3),
                )
            ],
            dtcs=[],
        )

    def get_dtcs(self) -> list[DTCResponse]:
        return [
            DTCResponse(
                code="P0420",
                description="Catalyst system efficiency below threshold",
                status="confirmed",
                severity="warning",
                category="emissions",
            )
        ]

    def get_mode6(self) -> list[Mode6TestResponse]:
        return [
            Mode6TestResponse(
                monitor="MONITOR_MISFIRE_CYLINDER_1",
                monitor_description="Misfire Cylinder 1 Data",
                category="misfire",
                test_id=1,
                test_name="Misfire counts",
                description="Misfire counts",
                value="12",
                minimum="0",
                maximum="5",
                unit="count",
                passed=False,
                status="failed",
            )
        ]

    def get_snapshot(self) -> HealthSnapshotResponse:
        return HealthSnapshotResponse(
            connected=True,
            port="/dev/test",
            protocol="CAN",
            sensors=[],
            dtcs=self.get_dtcs(),
            mode6=self.get_mode6(),
        )

    def diagnose(self, request: DiagnoseRequest) -> DiagnosisResponse:
        self.diagnose_requests.append(request)
        return DiagnosisResponse(
            severity="warning",
            summary="Catalyst efficiency below threshold",
            likely_causes=["Cause A", "Cause B"],
            repair_steps=["Step A", "Step B"],
            estimated_cost_usd={"low": 100, "high": 500},
            diy_feasible=False,
            diy_difficulty="moderate",
            urgency="soon",
            disclaimer="diagnostic disclaimer",
            dtc_codes=["P0420"],
            vehicle_str="2018 Ford F-150 (85,000 miles)",
            cached=False,
            timestamp=datetime(2026, 5, 22, 1, 2, 3),
        )


def test_health_endpoint_returns_ok() -> None:
    client = TestClient(create_app(service=FakeService()))

    assert client.get("/api/health").json() == {"status": "ok", "service": "open-mechanic"}


def test_vehicle_endpoint_returns_profile() -> None:
    client = TestClient(create_app(service=FakeService()))

    response = client.get("/api/vehicle")

    assert response.status_code == 200
    assert response.json()["model"] == "F-150"


def test_live_endpoint_returns_sensor_snapshot() -> None:
    client = TestClient(create_app(service=FakeService()))

    response = client.get("/api/live")

    assert response.status_code == 200
    assert response.json()["sensors"][0]["name"] == "RPM"


def test_dtc_endpoint_returns_fault_codes() -> None:
    client = TestClient(create_app(service=FakeService()))

    response = client.get("/api/dtc")

    assert response.status_code == 200
    assert response.json()[0]["code"] == "P0420"


def test_mode6_endpoint_returns_monitor_tests() -> None:
    client = TestClient(create_app(service=FakeService()))

    response = client.get("/api/mode6")

    assert response.status_code == 200
    assert response.json()[0]["monitor"] == "MONITOR_MISFIRE_CYLINDER_1"


def test_snapshot_endpoint_returns_combined_snapshot() -> None:
    client = TestClient(create_app(service=FakeService()))

    response = client.get("/api/snapshot")

    assert response.status_code == 200
    assert response.json()["dtcs"][0]["severity"] == "warning"
    assert response.json()["mode6"][0]["status"] == "failed"


def test_diagnose_endpoint_passes_request_to_service() -> None:
    service = FakeService()
    client = TestClient(create_app(service=service))

    response = client.post(
        "/api/diagnose",
        json={
            "year": 2018,
            "make": "Ford",
            "model": "F-150",
            "mileage": 85000,
            "bypass_cache": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["summary"] == "Catalyst efficiency below threshold"
    assert service.diagnose_requests[0].bypass_cache is True
