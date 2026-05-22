from __future__ import annotations

import os
from collections.abc import Callable

from open_mechanic.ai.diagnose import DiagnosticEngine
from open_mechanic.connection import OBDConnection
from open_mechanic.db.models import VehicleProfile as DiagnosticVehicleProfile
from open_mechanic.dtc import DTCCode, DTCReader
from open_mechanic.local_store import VehicleProfile as LocalVehicleProfile
from open_mechanic.local_store import load_vehicle_profile
from open_mechanic.reader import SensorPoller, SensorValue

from .schemas import (
    DiagnoseRequest,
    DiagnosisResponse,
    DTCResponse,
    HealthSnapshotResponse,
    SensorReadingResponse,
    VehicleProfileResponse,
)

ConnectionFactory = Callable[[], OBDConnection]
ProfileLoader = Callable[[], LocalVehicleProfile | None]
EngineFactory = Callable[[], DiagnosticEngine]


class DiagnosticAPIService:
    def __init__(
        self,
        connection_factory: ConnectionFactory | None = None,
        profile_loader: ProfileLoader = load_vehicle_profile,
        engine_factory: EngineFactory | None = None,
    ) -> None:
        self._connection_factory = connection_factory or _default_connection
        self._profile_loader = profile_loader
        self._engine_factory = engine_factory or DiagnosticEngine

    def get_vehicle_profile(self) -> VehicleProfileResponse:
        profile = self._profile_loader()
        if profile is None:
            return VehicleProfileResponse(configured=False)

        return VehicleProfileResponse(
            configured=True,
            year=profile.year,
            make=profile.make,
            model=profile.model,
            mileage=profile.mileage,
        )

    def get_live_sensors(self) -> HealthSnapshotResponse:
        connection = self._connection_factory()
        connected = connection.connect()
        if not connected:
            return HealthSnapshotResponse(
                connected=False,
                port=connection.get_port(),
                protocol=None,
                sensors=[],
                dtcs=[],
            )

        try:
            raw_connection = connection.get_connection()
            protocol = raw_connection.protocol_name() if raw_connection is not None else None
            sensors = _sensor_responses(SensorPoller(connection).get_snapshot())
            return HealthSnapshotResponse(
                connected=True,
                port=connection.get_port(),
                protocol=protocol,
                sensors=sensors,
                dtcs=[],
            )
        finally:
            connection.disconnect()

    def get_dtcs(self) -> list[DTCResponse]:
        connection = self._connection_factory()
        connected = connection.connect()
        if not connected:
            return []

        try:
            return _dtc_responses(DTCReader(connection).get_dtcs())
        finally:
            connection.disconnect()

    def get_snapshot(self) -> HealthSnapshotResponse:
        connection = self._connection_factory()
        connected = connection.connect()
        if not connected:
            return HealthSnapshotResponse(
                connected=False,
                port=connection.get_port(),
                protocol=None,
                sensors=[],
                dtcs=[],
            )

        try:
            raw_connection = connection.get_connection()
            protocol = raw_connection.protocol_name() if raw_connection is not None else None
            return HealthSnapshotResponse(
                connected=True,
                port=connection.get_port(),
                protocol=protocol,
                sensors=_sensor_responses(SensorPoller(connection).get_snapshot()),
                dtcs=_dtc_responses(DTCReader(connection).get_dtcs()),
            )
        finally:
            connection.disconnect()

    def diagnose(self, request: DiagnoseRequest) -> DiagnosisResponse:
        snapshot = self.get_snapshot()
        vehicle = DiagnosticVehicleProfile(
            year=request.year,
            make=request.make,
            model=request.model,
            mileage=request.mileage,
            vin=request.vin,
        )
        dtcs = [
            DTCCode(
                code=dtc.code,
                description=dtc.description,
                status=dtc.status,
                severity=dtc.severity,
                category=dtc.category,
            )
            for dtc in snapshot.dtcs
        ]
        sensor_snapshot = {
            sensor.name: {
                "value": sensor.value,
                "unit": sensor.unit,
                "supported": sensor.supported,
            }
            for sensor in snapshot.sensors
        }
        result = self._engine_factory().diagnose(
            vehicle,
            dtcs,
            sensor_snapshot,
            bypass_cache=request.bypass_cache,
        )
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
            vehicle_str=result.vehicle_str,
            cached=result.cached,
            timestamp=result.timestamp,
        )


def _sensor_responses(snapshot: dict[str, SensorValue]) -> list[SensorReadingResponse]:
    return [
        SensorReadingResponse(
            name=sensor.name,
            value=sensor.value,
            unit=sensor.unit,
            supported=sensor.supported,
            timestamp=sensor.timestamp,
        )
        for sensor in snapshot.values()
    ]


def _dtc_responses(dtcs: list[DTCCode]) -> list[DTCResponse]:
    return [
        DTCResponse(
            code=dtc.code,
            description=dtc.description,
            status=dtc.status,
            severity=dtc.severity,
            category=dtc.category,
        )
        for dtc in dtcs
    ]


def _default_connection() -> OBDConnection:
    timeout = float(os.getenv("OPEN_MECHANIC_API_OBD_TIMEOUT", "3.0"))
    max_retries = int(os.getenv("OPEN_MECHANIC_API_OBD_RETRIES", "1"))
    return OBDConnection(timeout=timeout, max_retries=max_retries)
