from __future__ import annotations

import threading
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import httpx2
import pytest

from open_mechanic.ai.diagnose import DiagnosticEngine, ExternalSharingNotAuthorized
from open_mechanic.api import create_app
from open_mechanic.api.schemas import (
    DiagnoseRequest,
    DiagnosisResponse,
    DTCResponse,
    HealthSnapshotResponse,
    SensorReadingResponse,
    VehicleProfileResponse,
)
from open_mechanic.api.services import DiagnosticAPIService


class FakeService:
    def __init__(self) -> None:
        self.diagnose_requests: list[DiagnoseRequest] = []
        self.snapshot_thread_id: int | None = None

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

    def get_snapshot(self) -> HealthSnapshotResponse:
        self.snapshot_thread_id = threading.get_ident()
        return HealthSnapshotResponse(
            connected=True,
            port="/dev/test",
            protocol="CAN",
            sensors=[],
            dtcs=self.get_dtcs(),
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


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _transport(service: FakeService) -> httpx2.ASGITransport:
    return httpx2.ASGITransport(app=create_app(service=service))


@pytest.mark.anyio
async def test_health_endpoint_returns_ok() -> None:
    async with httpx2.AsyncClient(transport=_transport(FakeService()), base_url="http://test") as client:
        response = await client.get("/api/health")

    assert response.json() == {"status": "ok", "service": "open-mechanic"}


@pytest.mark.anyio
async def test_vehicle_endpoint_returns_profile() -> None:
    async with httpx2.AsyncClient(transport=_transport(FakeService()), base_url="http://test") as client:
        response = await client.get("/api/vehicle")

    assert response.status_code == 200
    assert response.json()["model"] == "F-150"


@pytest.mark.anyio
async def test_live_endpoint_returns_sensor_snapshot() -> None:
    async with httpx2.AsyncClient(transport=_transport(FakeService()), base_url="http://test") as client:
        response = await client.get("/api/live")

    assert response.status_code == 200
    assert response.json()["sensors"][0]["name"] == "RPM"


@pytest.mark.anyio
async def test_dtc_endpoint_returns_fault_codes() -> None:
    async with httpx2.AsyncClient(transport=_transport(FakeService()), base_url="http://test") as client:
        response = await client.get("/api/dtc")

    assert response.status_code == 200
    assert response.json()[0]["code"] == "P0420"


@pytest.mark.anyio
async def test_snapshot_endpoint_returns_combined_snapshot() -> None:
    service = FakeService()
    event_loop_thread_id = threading.get_ident()
    async with httpx2.AsyncClient(transport=_transport(service), base_url="http://test") as client:
        response = await client.get("/api/snapshot")

    assert response.status_code == 200
    assert response.json()["dtcs"][0]["severity"] == "warning"
    assert service.snapshot_thread_id is not None
    assert service.snapshot_thread_id != event_loop_thread_id


@pytest.mark.anyio
async def test_diagnose_endpoint_passes_request_to_service() -> None:
    service = FakeService()
    async with httpx2.AsyncClient(transport=_transport(service), base_url="http://test") as client:
        response = await client.post(
            "/api/diagnose",
            json={
                "year": 2018,
                "make": "Ford",
                "model": "F-150",
                "mileage": 85000,
                "external_sharing_authorized": True,
            },
        )

    assert response.status_code == 200
    assert response.json()["summary"] == "Catalyst efficiency below threshold"
    assert service.diagnose_requests[0].external_sharing_authorized is True


@pytest.mark.anyio
async def test_api_authorization_applies_to_one_request_only() -> None:
    class RecordingMessages:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def create(self, **kwargs: Any) -> SimpleNamespace:
            self.calls.append(kwargs)
            return SimpleNamespace(
                content=[SimpleNamespace(text='{"summary":"ok","severity":"info"}')]
            )

    messages = RecordingMessages()
    engine = DiagnosticEngine(api_key="test")
    engine._client = SimpleNamespace(messages=messages)  # type: ignore[assignment]
    service = DiagnosticAPIService(engine_factory=lambda: engine)
    empty_snapshot = HealthSnapshotResponse(
        connected=False, port=None, protocol=None, sensors=[], dtcs=[]
    )
    service.get_snapshot = lambda: empty_snapshot  # type: ignore[method-assign]
    transport = _transport(service)  # type: ignore[arg-type]
    async with httpx2.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(
            "/api/diagnose",
            json={"year": 2020, "make": "Example", "model": "Vehicle", "mileage": 1,
                  "external_sharing_authorized": True},
        )
        with pytest.raises(ExternalSharingNotAuthorized):
            await client.post(
                "/api/diagnose",
                json={"year": 2020, "make": "Example", "model": "Vehicle", "mileage": 1},
            )

    assert first.status_code == 200
    assert len(messages.calls) == 1
