from __future__ import annotations

import asyncio
import queue
import threading
from collections.abc import AsyncIterator, Callable
from concurrent.futures import Future as WorkerFuture
from contextlib import asynccontextmanager
from typing import ParamSpec, TypeVar, cast

from fastapi import FastAPI, HTTPException

from open_mechanic.ai.diagnose import ExternalSharingNotAuthorized

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


class DiagnosticWorkerPool:
    """Application-owned bounded pool for blocking serial and AI calls."""

    def __init__(self, max_workers: int = 4) -> None:
        self.max_workers = max_workers
        self.closed = False
        self._jobs: queue.Queue[object] = queue.Queue()
        self._threads: list[threading.Thread] = []
        self._start_lock = threading.Lock()

    def _ensure_started(self) -> None:
        with self._start_lock:
            if self._threads:
                return
            for index in range(self.max_workers):
                thread = threading.Thread(
                    target=self._worker,
                    name=f"open-mechanic-api-{index}",
                )
                thread.start()
                self._threads.append(thread)

    @property
    def worker_count(self) -> int:
        return len(self._threads)

    def _worker(self) -> None:
        while True:
            job = self._jobs.get()
            if job is None:
                return
            call, result = cast(
                tuple[Callable[[], object], WorkerFuture[object]],
                job,
            )
            if not result.set_running_or_notify_cancel():
                continue
            try:
                value = call()
            except BaseException as exc:
                result.set_exception(exc)
            else:
                result.set_result(value)

    async def run(self, call: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
        if self.closed:
            raise RuntimeError("diagnostic worker pool is closed")
        self._ensure_started()
        result: WorkerFuture[object] = WorkerFuture()
        self._jobs.put_nowait((lambda: call(*args, **kwargs), result))
        try:
            while not result.done():
                await asyncio.sleep(0.001)
            return cast(T, result.result())
        except asyncio.CancelledError:
            result.cancel()
            raise

    def shutdown(self) -> None:
        if self.closed:
            return
        self.closed = True
        for _ in self._threads:
            self._jobs.put_nowait(None)
        for thread in self._threads:
            thread.join()


def create_app(service: DiagnosticAPIService | None = None) -> FastAPI:
    worker_pool = DiagnosticWorkerPool()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            worker_pool.shutdown()

    app = FastAPI(title="open-mechanic API", version="0.1.0", lifespan=lifespan)
    app.state.diagnostic_worker_pool = worker_pool
    api_service = service or DiagnosticAPIService()

    @app.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", service="open-mechanic")

    @app.get("/api/vehicle", response_model=VehicleProfileResponse)
    async def vehicle() -> VehicleProfileResponse:
        return await worker_pool.run(api_service.get_vehicle_profile)

    @app.get("/api/live", response_model=HealthSnapshotResponse)
    async def live() -> HealthSnapshotResponse:
        return await worker_pool.run(api_service.get_live_sensors)

    @app.get("/api/dtc", response_model=list[DTCResponse])
    async def dtc() -> list[DTCResponse]:
        return await worker_pool.run(api_service.get_dtcs)

    @app.get("/api/snapshot", response_model=HealthSnapshotResponse)
    async def snapshot() -> HealthSnapshotResponse:
        return await worker_pool.run(api_service.get_snapshot)

    @app.post("/api/diagnose", response_model=DiagnosisResponse)
    async def diagnose(request: DiagnoseRequest) -> DiagnosisResponse:
        try:
            return await worker_pool.run(api_service.diagnose, request)
        except ExternalSharingNotAuthorized as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    return app
