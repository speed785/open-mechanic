from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import AsyncIterator
from concurrent.futures import Future as WorkerFuture
from contextlib import asynccontextmanager
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import httpx2
import pytest

from open_mechanic.ai.diagnose import DiagnosticEngine
from open_mechanic.api import create_app
from open_mechanic.api.app import (
    DiagnosticWorkerPool,
    WorkerPoolClosed,
    WorkerPoolSaturated,
)
from open_mechanic.api.schemas import (
    DiagnoseRequest,
    DiagnosisResponse,
    DTCResponse,
    HealthSnapshotResponse,
    SensorReadingResponse,
    VehicleProfileResponse,
)
from open_mechanic.db.models import VehicleProfile as DiagnosticVehicleProfile


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

    def get_stellantis_dtcs(self, vehicle: str, port: str, timeout: float) -> Any:
        from open_mechanic.api.schemas import StellantisScanResponse

        assert (vehicle, port, timeout) == ("wrangler_jl_4xe_2024", "/dev/test", 1.5)
        return StellantisScanResponse(vehicle=vehicle, modules=[])

    def get_stellantis_live(
        self, vehicle: str, group: str, port: str, timeout: float, *, samples: int, interval: float
    ) -> Any:
        from open_mechanic.api.schemas import StellantisLiveResponse

        assert (vehicle, group, port, timeout, samples, interval) == (
            "wrangler_jl_4xe_2024",
            "cruise",
            "/dev/test",
            1.5,
            2,
            0.2,
        )
        return StellantisLiveResponse(vehicle=vehicle, group=group, samples=[])


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@asynccontextmanager
async def _client(
    service: Any, worker_pool: DiagnosticWorkerPool | None = None
) -> AsyncIterator[httpx2.AsyncClient]:
    app = create_app(service=service, worker_pool=worker_pool)
    async with (
        app.router.lifespan_context(app),
        httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://test"
        ) as client,
    ):
        yield client


@pytest.mark.anyio
async def test_health_endpoint_returns_ok() -> None:
    async with _client(FakeService()) as client:
        response = await client.get("/api/health")

    assert response.json() == {"status": "ok", "service": "open-mechanic"}


@pytest.mark.anyio
async def test_vehicle_endpoint_returns_profile() -> None:
    async with _client(FakeService()) as client:
        response = await client.get("/api/vehicle")

    assert response.status_code == 200
    assert response.json()["model"] == "F-150"


@pytest.mark.anyio
async def test_live_endpoint_returns_sensor_snapshot() -> None:
    async with _client(FakeService()) as client:
        response = await client.get("/api/live")

    assert response.status_code == 200
    assert response.json()["sensors"][0]["name"] == "RPM"


@pytest.mark.anyio
async def test_dtc_endpoint_returns_fault_codes() -> None:
    async with _client(FakeService()) as client:
        response = await client.get("/api/dtc")

    assert response.status_code == 200
    assert response.json()[0]["code"] == "P0420"


@pytest.mark.anyio
async def test_snapshot_endpoint_returns_combined_snapshot() -> None:
    service = FakeService()
    event_loop_thread_id = threading.get_ident()
    async with _client(service) as client:
        response = await client.get("/api/snapshot")

    assert response.status_code == 200
    assert response.json()["dtcs"][0]["severity"] == "warning"
    assert service.snapshot_thread_id is not None
    assert service.snapshot_thread_id != event_loop_thread_id


@pytest.mark.anyio
async def test_stellantis_routes_delegate_validated_bounded_requests() -> None:
    async with _client(FakeService()) as client:
        scan = await client.get(
            "/api/stellantis/wrangler_jl_4xe_2024/dtc",
            params={"port": "/dev/test", "timeout": 1.5},
        )
        live = await client.get(
            "/api/stellantis/wrangler_jl_4xe_2024/live/cruise",
            params={"port": "/dev/test", "timeout": 1.5, "samples": 2, "interval": 0.2},
        )

    assert scan.status_code == 200
    assert scan.json() == {"vehicle": "wrangler_jl_4xe_2024", "modules": []}
    assert live.status_code == 200
    assert live.json() == {
        "vehicle": "wrangler_jl_4xe_2024",
        "group": "cruise",
        "samples": [],
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/api/stellantis/not_a_vehicle/dtc", {}),
        ("/api/stellantis/wrangler_jl_4xe_2024/live/not_a_group", {}),
        ("/api/stellantis/wrangler_jl_4xe_2024/live/cruise", {"samples": 0}),
        ("/api/stellantis/wrangler_jl_4xe_2024/live/cruise", {"samples": 61}),
        ("/api/stellantis/wrangler_jl_4xe_2024/live/cruise", {"interval": 0}),
        ("/api/stellantis/wrangler_jl_4xe_2024/live/cruise", {"interval": 10.1}),
    ],
)
async def test_stellantis_routes_reject_unknown_or_unbounded_requests(
    path: str, params: dict[str, float]
) -> None:
    async with _client(FakeService()) as client:
        response = await client.get(path, params=params)

    assert response.status_code in {404, 422}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "path",
    [
        "/api/stellantis/wrangler_jl_4xe_2024/dtc",
        "/api/stellantis/wrangler_jl_4xe_2024/live/cruise",
    ],
)
async def test_stellantis_adapter_failures_are_actionable_503_without_private_details(
    path: str,
) -> None:
    from open_mechanic.protocols.elm327 import ELM327ConnectionError

    class FailedService(FakeService):
        def get_stellantis_dtcs(self, vehicle: str, port: str, timeout: float) -> Any:
            raise ELM327ConnectionError("could not open /dev/private-car-adapter")

        def get_stellantis_live(self, *args: Any, **kwargs: Any) -> Any:
            raise ELM327ConnectionError("could not open /dev/private-car-adapter")

    async with _client(FailedService()) as client:
        response = await client.get(path)

    assert response.status_code == 503
    assert response.json() == {
        "detail": "OBDLink EX unavailable; check the configured port and dialout group or udev ACL"
    }
    assert "private-car-adapter" not in response.text


@pytest.mark.anyio
async def test_diagnose_endpoint_passes_request_to_service() -> None:
    service = FakeService()
    async with _client(service) as client:
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
    engine = object.__new__(DiagnosticEngine)
    engine._model = "test-model"
    engine._client = SimpleNamespace(messages=messages)  # type: ignore[assignment]

    class BoundaryService(FakeService):
        def diagnose(self, request: DiagnoseRequest) -> DiagnosisResponse:
            engine.diagnose(
                DiagnosticVehicleProfile(
                    year=request.year,
                    make=request.make,
                    model=request.model,
                    mileage=request.mileage,
                ),
                [],
                {},
                external_sharing_authorized=request.external_sharing_authorized,
            )
            return super().diagnose(request)

    service = BoundaryService()
    async with _client(service) as client:
        async with asyncio.timeout(2):
            first = await client.post(
                "/api/diagnose",
                json={
                    "year": 2020,
                    "make": "Example",
                    "model": "Vehicle",
                    "mileage": 1,
                    "external_sharing_authorized": True,
                },
            )
        async with asyncio.timeout(2):
            second = await client.post(
                "/api/diagnose",
                json={"year": 2020, "make": "Example", "model": "Vehicle", "mileage": 1},
            )

    assert first.status_code == 200
    assert second.status_code == 403
    assert len(messages.calls) == 1


@pytest.mark.anyio
async def test_worker_pool_is_bounded_and_propagates_exceptions() -> None:
    pool = DiagnosticWorkerPool(max_workers=2)

    assert pool.max_workers == 2
    assert await pool.run(lambda: "first") == "first"
    assert await pool.run(lambda: "second") == "second"
    assert pool.worker_count == 2
    with pytest.raises(RuntimeError, match="worker failed"):
        await pool.run(lambda: (_ for _ in ()).throw(RuntimeError("worker failed")))

    pool.shutdown()
    assert pool.closed is True


@pytest.mark.anyio
async def test_worker_pool_rejects_when_pending_queue_is_full() -> None:
    pool = DiagnosticWorkerPool(max_workers=1, max_pending_jobs=1)
    started = threading.Event()
    release = threading.Event()

    def block() -> None:
        started.set()
        release.wait(timeout=1)

    running = asyncio.create_task(pool.run(block))
    while not started.is_set():
        await asyncio.sleep(0)
    queued = asyncio.create_task(pool.run(lambda: None))
    await asyncio.sleep(0)

    with pytest.raises(WorkerPoolSaturated):
        await pool.run(lambda: None)

    release.set()
    await running
    await queued
    pool.shutdown()


@pytest.mark.anyio
async def test_saturated_api_returns_503() -> None:
    pool = DiagnosticWorkerPool(max_workers=1, max_pending_jobs=1)
    started = threading.Event()
    release = threading.Event()
    running = asyncio.create_task(pool.run(lambda: (started.set(), release.wait(timeout=1))))
    while not started.is_set():
        await asyncio.sleep(0)
    queued = asyncio.create_task(pool.run(lambda: None))
    await asyncio.sleep(0)

    async with _client(FakeService(), worker_pool=pool) as client:
        response = await client.get("/api/snapshot")
        assert response.status_code == 503
        release.set()
        await running
        await queued


@pytest.mark.anyio
async def test_worker_pool_cancellation_does_not_report_invalid_state() -> None:
    pool = DiagnosticWorkerPool(max_workers=1)
    started = threading.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    errors: list[dict[str, Any]] = []
    previous_handler = loop.get_exception_handler()
    loop.set_exception_handler(lambda loop, context: errors.append(context))

    def blocking_call() -> None:
        started.set()
        release.wait(timeout=1)

    try:
        task = asyncio.create_task(pool.run(blocking_call))
        while not started.is_set():
            await asyncio.sleep(0)
        queued = asyncio.create_task(pool.run(lambda: pytest.fail("cancelled job must not run")))
        await asyncio.sleep(0)
        queued.cancel()
        with pytest.raises(asyncio.CancelledError):
            await queued
        release.set()
        await task
        await asyncio.sleep(0.01)
        assert errors == []
    finally:
        loop.set_exception_handler(previous_handler)
        release.set()
        pool.shutdown()


@pytest.mark.anyio
async def test_app_lifespan_shuts_down_worker_pool() -> None:
    app = create_app(service=FakeService())
    pool = app.state.diagnostic_worker_pool

    assert pool.closed is False
    async with app.router.lifespan_context(app):
        assert app.state.diagnostic_worker_pool is pool
        assert pool.closed is False
    assert pool.closed is True
    pool.shutdown()
    with pytest.raises(RuntimeError, match="closed"):
        await pool.run(lambda: None)


@pytest.mark.anyio
async def test_shutdown_closes_admission_cancels_queue_and_has_bounded_wait() -> None:
    pool = DiagnosticWorkerPool(
        max_workers=1,
        max_pending_jobs=1,
        shutdown_timeout_seconds=0.02,
    )
    started = threading.Event()
    release = threading.Event()
    running = asyncio.create_task(pool.run(lambda: (started.set(), release.wait(timeout=1))))
    while not started.is_set():
        await asyncio.sleep(0)
    queued = asyncio.create_task(pool.run(lambda: None))
    await asyncio.sleep(0)

    before = asyncio.get_running_loop().time()
    pool.shutdown()
    elapsed = asyncio.get_running_loop().time() - before

    assert elapsed < 0.2
    async with asyncio.timeout(0.2):
        with pytest.raises(WorkerPoolClosed):
            await queued
    with pytest.raises(WorkerPoolClosed):
        await pool.run(lambda: None)
    release.set()
    await running


@pytest.mark.anyio
async def test_shutdown_admission_race_never_orphans_submission() -> None:
    pool = DiagnosticWorkerPool(max_workers=1, max_pending_jobs=1)
    shutdown_started = threading.Event()

    def shut_down() -> None:
        shutdown_started.set()
        pool.shutdown()

    shutdown_thread = threading.Thread(target=shut_down)
    shutdown_thread.start()
    while not shutdown_started.is_set():
        await asyncio.sleep(0)

    async with asyncio.timeout(0.2):
        with pytest.raises(WorkerPoolClosed):
            await pool.run(lambda: None)
    shutdown_thread.join(timeout=0.2)
    assert shutdown_thread.is_alive() is False


@pytest.mark.anyio
async def test_shutdown_cancels_job_dequeued_before_close_transition() -> None:
    pool = DiagnosticWorkerPool(max_workers=1, max_pending_jobs=1)
    result: WorkerFuture[object] = WorkerFuture()
    with pool._state_lock:
        pool._ensure_started_locked()
        pool._jobs.put_nowait((lambda: pytest.fail("closed job must not run"), result))
        deadline = time.monotonic() + 0.2
        while pool._jobs.qsize() != 0 and time.monotonic() < deadline:
            time.sleep(0.001)
        assert pool._jobs.qsize() == 0
        pool.closed = True
        pool._jobs.put_nowait(None)

    async with asyncio.timeout(0.2):
        while not result.cancelled():
            await asyncio.sleep(0.001)
    for thread in pool._threads:
        thread.join(timeout=0.2)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_workers": 0},
        {"max_pending_jobs": 0},
        {"shutdown_timeout_seconds": -1},
    ],
)
def test_worker_pool_rejects_invalid_limits(kwargs: dict[str, int]) -> None:
    with pytest.raises(ValueError, match="worker limits"):
        DiagnosticWorkerPool(**kwargs)
