from __future__ import annotations

import json
import threading
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from open_mechanic import __version__
from open_mechanic.ai.diagnose import DiagnosticEngine
from open_mechanic.ai.providers import (
    DiagnosticProvider,
    ProviderConfigurationError,
    select_provider,
)
from open_mechanic.connection import OBDConnection
from open_mechanic.db.models import VehicleProfile as DbVehicleProfile
from open_mechanic.dtc import DTCReader
from open_mechanic.local_store import SESSIONS_DIR, load_vehicle_profile
from open_mechanic.reader import SensorPoller
from open_mechanic.web.schemas import (
    ConnectRequest,
    DiagnosisRequest,
    DiagnosisResponse,
    DTCResponse,
    DTCResponseItem,
    MessageResponse,
    ReportListResponse,
    ReportSummary,
    SensorReadingResponse,
    SensorResponse,
    StatusResponse,
    VehicleProfileResponse,
)


class DashboardService:
    def __init__(
        self,
        *,
        offline: bool = False,
        provider: DiagnosticProvider | None = None,
        provider_name: str | None = None,
    ) -> None:
        self._offline = offline
        self._provider = provider
        self._provider_name = provider_name
        self._provider_error: str | None = None
        self._adapter_message: str | None = None
        self._connection: OBDConnection | None = None
        self._poller: SensorPoller | None = None
        self._latest_poll_at: datetime | None = None
        self._adapter_lock = threading.Lock()

        if provider is None:
            self._resolve_provider()

    def _resolve_provider(self) -> None:
        try:
            self._provider = select_provider(self._provider_name)
            self._provider_error = None
        except ProviderConfigurationError as exc:
            self._provider = None
            self._provider_error = str(exc)

    def get_status(self) -> StatusResponse:
        raw_conn = self._connection.get_connection() if self._connection is not None else None
        protocol = raw_conn.protocol_name() if raw_conn is not None else None
        connected = self._connection is not None and self._connection.is_connected()
        if self._offline:
            adapter_state = "offline"
        elif connected:
            adapter_state = "connected"
        elif self._adapter_message:
            adapter_state = "error"
        else:
            adapter_state = "disconnected"
        return StatusResponse(
            version=__version__,
            connected=connected,
            offline=self._offline,
            adapter_state=adapter_state,
            adapter_message=self._adapter_message,
            port=self._connection.get_port() if self._connection is not None else None,
            protocol=protocol,
            provider_name=self._provider.name if self._provider is not None else "not configured",
            provider_configured=self._provider is not None,
            vehicle_profile=_profile_response(),
            latest_poll_at=self._latest_poll_at,
        )

    def connect(self, request: ConnectRequest) -> MessageResponse:
        with self._adapter_lock:
            self._disconnect_unlocked()
            self._adapter_message = None
            self._offline = request.offline
            if request.offline:
                return MessageResponse(ok=True, message="Offline mode enabled.")

            connection = OBDConnection(
                port=request.port,
                protocol=request.protocol,
                baudrate=request.baudrate,
                timeout=request.timeout,
                max_retries=1,
            )
            if not connection.connect():
                self._adapter_message = "No OBD adapter connection."
                return MessageResponse(ok=False, message=self._adapter_message)

            self._connection = connection
            self._poller = SensorPoller(connection)
            return MessageResponse(ok=True, message="Connected to OBD adapter.")

    def disconnect(self) -> MessageResponse:
        with self._adapter_lock:
            self._disconnect_unlocked()
            self._offline = False
            self._adapter_message = "Disconnected."
        return MessageResponse(ok=True, message="Disconnected.")

    def _disconnect_unlocked(self) -> None:
        if self._connection is not None:
            self._connection.disconnect()
        self._connection = None
        self._poller = None

    def get_sensors(self) -> SensorResponse:
        with self._adapter_lock:
            if self._offline or self._poller is None:
                return SensorResponse(sensors=[])

            snapshot = self._poller.get_snapshot()
            self._latest_poll_at = datetime.now()
            return SensorResponse(
                sensors=[
                    SensorReadingResponse(
                        name=sensor.name,
                        value=sensor.value,
                        unit=sensor.unit,
                        timestamp=sensor.timestamp,
                        supported=sensor.supported,
                    )
                    for sensor in snapshot.values()
                ]
            )

    def get_dtcs(self) -> DTCResponse:
        with self._adapter_lock:
            if self._offline or self._connection is None:
                return DTCResponse(dtcs=[])

            return DTCResponse(
                dtcs=[
                    DTCResponseItem(
                        code=dtc.code,
                        description=dtc.description,
                        status=dtc.status,
                        severity=dtc.severity,
                        category=dtc.category,
                    )
                    for dtc in DTCReader(self._connection).get_dtcs()
                ]
            )

    def list_reports(self) -> ReportListResponse:
        reports: list[ReportSummary] = []
        if not SESSIONS_DIR.exists():
            return ReportListResponse(reports=reports)

        for path in sorted(SESSIONS_DIR.glob("*-diagnosis.json"), reverse=True):
            payload = _read_json(path)
            reports.append(
                ReportSummary(
                    filename=path.name,
                    path=str(path),
                    created_at=datetime.fromtimestamp(path.stat().st_mtime),
                    severity=_string_or_none(payload.get("severity")),
                    summary=_string_or_none(payload.get("summary")),
                    vehicle=_string_or_none(payload.get("vehicle")),
                    provider=_string_or_none(payload.get("provider")),
                )
            )
        return ReportListResponse(reports=reports)

    def diagnose(self, request: DiagnosisRequest) -> DiagnosisResponse:
        provider = self._provider
        if provider is None:
            self._resolve_provider()
            provider = self._provider
        engine = DiagnosticEngine(provider=provider, provider_name=self._provider_name)
        vehicle = DbVehicleProfile(
            year=request.vehicle.year,
            make=request.vehicle.make,
            model=request.vehicle.model,
            mileage=request.vehicle.mileage,
            vin=request.vehicle.vin,
            created_at=request.generated_at or datetime.now(),
        )
        result = engine.diagnose(vehicle, self.get_dtcs().dtcs, _sensor_context(self.get_sensors()))
        return DiagnosisResponse(
            severity=result.severity,
            summary=result.summary,
            likely_causes=result.likely_causes,
            repair_steps=result.repair_steps,
            estimated_cost_usd=result.estimated_cost_usd,
            diy_feasible=result.diy_feasible,
            diy_difficulty=result.diy_difficulty,
            urgency=result.urgency,
            disclaimer=result.disclaimer,
            dtc_codes=result.dtc_codes,
            vehicle=result.vehicle_str,
            provider=result.provider,
            cached=result.cached,
        )


def _profile_response() -> VehicleProfileResponse | None:
    profile = load_vehicle_profile()
    if profile is None:
        return None
    return VehicleProfileResponse(
        year=profile.year,
        make=profile.make,
        model=profile.model,
        mileage=profile.mileage,
        vin=None,
        label=profile.label,
    )


def _sensor_context(response: SensorResponse) -> dict[str, object]:
    return {sensor.name: asdict(sensor) if hasattr(sensor, "__dataclass_fields__") else sensor.model_dump() for sensor in response.sensors}


def _read_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None
