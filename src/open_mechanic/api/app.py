from __future__ import annotations

import asyncio
import queue
import threading
import time
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
DEFAULT_MAX_PENDING_JOBS = 8
DEFAULT_SHUTDOWN_TIMEOUT_SECONDS = 0.25


class WorkerPoolUnavailable(RuntimeError):
    """Base class for worker admission failures."""


class WorkerPoolClosed(WorkerPoolUnavailable):
    """Raised when work is submitted after shutdown starts."""


class WorkerPoolSaturated(WorkerPoolUnavailable):
    """Raised immediately when the finite pending queue is full."""


class DiagnosticWorkerPool:
    """Application-owned bounded pool for blocking serial and AI calls."""

    def __init__(
        self,
        max_workers: int = 4,
        max_pending_jobs: int = DEFAULT_MAX_PENDING_JOBS,
        shutdown_timeout_seconds: float = DEFAULT_SHUTDOWN_TIMEOUT_SECONDS,
    ) -> None:
        if max_workers < 1 or max_pending_jobs < 1 or shutdown_timeout_seconds < 0:
            raise ValueError("worker limits must be positive and shutdown timeout non-negative")
        self.max_workers = max_workers
        self.max_pending_jobs = max_pending_jobs
        self.shutdown_timeout_seconds = shutdown_timeout_seconds
        self.closed = False
        self._jobs: queue.Queue[object] = queue.Queue(maxsize=max_pending_jobs)
        self._threads: list[threading.Thread] = []
        self._state_lock = threading.Lock()

    def _ensure_started_locked(self) -> None:
        if self._threads:
            return
        for index in range(self.max_workers):
            thread = threading.Thread(
                target=self._worker,
                name=f"open-mechanic-api-{index}",
                daemon=True,
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
                self._jobs.put_nowait(None)
                return
            call, result = cast(
                tuple[Callable[[], object], WorkerFuture[object]],
                job,
            )
            with self._state_lock:
                if self.closed:
                    result.cancel()
                    continue
                if not result.set_running_or_notify_cancel():
                    continue
            try:
                value = call()
            except BaseException as exc:
                result.set_exception(exc)
            else:
                result.set_result(value)

    async def run(self, call: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
        result: WorkerFuture[object] = WorkerFuture()
        with self._state_lock:
            if self.closed:
                raise WorkerPoolClosed("diagnostic worker pool is closed")
            self._ensure_started_locked()
            try:
                self._jobs.put_nowait((lambda: call(*args, **kwargs), result))
            except queue.Full as exc:
                raise WorkerPoolSaturated("diagnostic worker pool is saturated") from exc
        try:
            while not result.done():
                await asyncio.sleep(0.001)
            if result.cancelled() and self.closed:
                raise WorkerPoolClosed("diagnostic job cancelled during shutdown")
            return cast(T, result.result())
        except asyncio.CancelledError:
            result.cancel()
            raise

    def shutdown(self) -> None:
        with self._state_lock:
            if self.closed:
                return
            self.closed = True
            while True:
                try:
                    job = self._jobs.get_nowait()
                except queue.Empty:
                    break
                if job is not None:
                    _, result = cast(tuple[Callable[[], object], WorkerFuture[object]], job)
                    result.cancel()
            if self._threads:
                self._jobs.put_nowait(None)

        deadline = time.monotonic() + self.shutdown_timeout_seconds
        for thread in self._threads:
            remaining = max(0.0, deadline - time.monotonic())
            thread.join(timeout=remaining)


def create_app(
    service: DiagnosticAPIService | None = None,
    worker_pool: DiagnosticWorkerPool | None = None,
) -> FastAPI:
    diagnostic_workers = worker_pool or DiagnosticWorkerPool()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            diagnostic_workers.shutdown()

    app = FastAPI(title="open-mechanic API", version="0.1.0", lifespan=lifespan)
    app.state.diagnostic_worker_pool = diagnostic_workers
    api_service = service or DiagnosticAPIService()

    @app.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", service="open-mechanic")

    @app.get("/api/vehicle", response_model=VehicleProfileResponse)
    async def vehicle() -> VehicleProfileResponse:
        return await _run_service(diagnostic_workers, api_service.get_vehicle_profile)

    @app.get("/api/live", response_model=HealthSnapshotResponse)
    async def live() -> HealthSnapshotResponse:
        return await _run_service(diagnostic_workers, api_service.get_live_sensors)

    @app.get("/api/dtc", response_model=list[DTCResponse])
    async def dtc() -> list[DTCResponse]:
        return await _run_service(diagnostic_workers, api_service.get_dtcs)

    @app.get("/api/snapshot", response_model=HealthSnapshotResponse)
    async def snapshot() -> HealthSnapshotResponse:
        return await _run_service(diagnostic_workers, api_service.get_snapshot)

    @app.post("/api/diagnose", response_model=DiagnosisResponse)
    async def diagnose(request: DiagnoseRequest) -> DiagnosisResponse:
        try:
            return await _run_service(diagnostic_workers, api_service.diagnose, request)
        except ExternalSharingNotAuthorized as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    return app


async def _run_service(
    worker_pool: DiagnosticWorkerPool,
    call: Callable[P, T],
    *args: P.args,
    **kwargs: P.kwargs,
) -> T:
    try:
        return await worker_pool.run(call, *args, **kwargs)
    except WorkerPoolUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
