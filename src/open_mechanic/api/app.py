from __future__ import annotations

from fastapi import FastAPI

from .schemas import (
    DiagnoseRequest,
    DiagnosisResponse,
    DTCResponse,
    HealthResponse,
    HealthSnapshotResponse,
    VehicleProfileResponse,
)
from .services import DiagnosticAPIService


def create_app(service: DiagnosticAPIService | None = None) -> FastAPI:
    app = FastAPI(title="open-mechanic API", version="0.1.0")
    api_service = service or DiagnosticAPIService()

    @app.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", service="open-mechanic")

    @app.get("/api/vehicle", response_model=VehicleProfileResponse)
    async def vehicle() -> VehicleProfileResponse:
        return api_service.get_vehicle_profile()

    @app.get("/api/live", response_model=HealthSnapshotResponse)
    async def live() -> HealthSnapshotResponse:
        return api_service.get_live_sensors()

    @app.get("/api/dtc", response_model=list[DTCResponse])
    async def dtc() -> list[DTCResponse]:
        return api_service.get_dtcs()

    @app.get("/api/snapshot", response_model=HealthSnapshotResponse)
    async def snapshot() -> HealthSnapshotResponse:
        return api_service.get_snapshot()

    @app.post("/api/diagnose", response_model=DiagnosisResponse)
    async def diagnose(request: DiagnoseRequest) -> DiagnosisResponse:
        return api_service.diagnose(request)

    return app
