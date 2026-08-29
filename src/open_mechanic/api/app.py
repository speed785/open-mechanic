from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from typing import ParamSpec, TypeVar

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

P = ParamSpec("P")
T = TypeVar("T")


async def _run_blocking(call: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    """Run blocking diagnostic work without relying on Python's default executor."""
    loop = asyncio.get_running_loop()
    result: asyncio.Future[T] = loop.create_future()

    def invoke() -> None:
        try:
            value = call(*args, **kwargs)
        except BaseException as exc:
            loop.call_soon_threadsafe(result.set_exception, exc)
        else:
            loop.call_soon_threadsafe(result.set_result, value)

    threading.Thread(target=invoke, daemon=True).start()
    return await result


def create_app(service: DiagnosticAPIService | None = None) -> FastAPI:
    app = FastAPI(title="open-mechanic API", version="0.1.0")
    api_service = service or DiagnosticAPIService()

    @app.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", service="open-mechanic")

    @app.get("/api/vehicle", response_model=VehicleProfileResponse)
    async def vehicle() -> VehicleProfileResponse:
        return await _run_blocking(api_service.get_vehicle_profile)

    @app.get("/api/live", response_model=HealthSnapshotResponse)
    async def live() -> HealthSnapshotResponse:
        return await _run_blocking(api_service.get_live_sensors)

    @app.get("/api/dtc", response_model=list[DTCResponse])
    async def dtc() -> list[DTCResponse]:
        return await _run_blocking(api_service.get_dtcs)

    @app.get("/api/snapshot", response_model=HealthSnapshotResponse)
    async def snapshot() -> HealthSnapshotResponse:
        return await _run_blocking(api_service.get_snapshot)

    @app.post("/api/diagnose", response_model=DiagnosisResponse)
    async def diagnose(request: DiagnoseRequest) -> DiagnosisResponse:
        return await _run_blocking(api_service.diagnose, request)

    return app
