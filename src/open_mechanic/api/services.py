from __future__ import annotations

import os
from collections.abc import Callable

from open_mechanic.ai.diagnose import DiagnosticEngine
from open_mechanic.connection import OBDConnection
from open_mechanic.db.models import VehicleProfile as DiagnosticVehicleProfile
from open_mechanic.dtc import DTCCode, DTCReader
from open_mechanic.local_store import VehicleProfile as LocalVehicleProfile
from open_mechanic.local_store import load_vehicle_profile
from open_mechanic.mode6 import (
    MisfireFinding,
    MisfireSummary,
    Mode6Reader,
    Mode6TestResult,
    diagnose_misfires,
)
from open_mechanic.reader import SensorPoller, SensorValue

from .schemas import (
    DiagnoseRequest,
    DiagnosisResponse,
    DTCResponse,
    HealthSnapshotResponse,
    MisfireFindingResponse,
    MisfireSummaryResponse,
    Mode6TestResponse,
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

    def get_mode6(self) -> list[Mode6TestResponse]:
        connection = self._connection_factory()
        connected = connection.connect()
        if not connected:
            return []

        try:
            return _mode6_responses(Mode6Reader(connection).get_results())
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
            sensor_snapshot = SensorPoller(connection).get_snapshot()
            dtcs = DTCReader(connection).get_dtcs()
            mode6_results = Mode6Reader(connection).get_results()
            misfire_summary = diagnose_misfires(mode6_results, dtcs, sensor_snapshot)
            return HealthSnapshotResponse(
                connected=True,
                port=connection.get_port(),
                protocol=protocol,
                sensors=_sensor_responses(sensor_snapshot),
                dtcs=_dtc_responses(dtcs),
                mode6=_mode6_responses(mode6_results),
                misfire_summary=_misfire_summary_response(misfire_summary),
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
        mode6_results = [
            Mode6TestResult(
                monitor=item.monitor,
                monitor_description=item.monitor_description,
                category=item.category,
                test_id=item.test_id,
                test_name=item.test_name,
                description=item.description,
                value=item.value,
                minimum=item.minimum,
                maximum=item.maximum,
                unit=item.unit,
                passed=item.passed,
                status=item.status,
            )
            for item in snapshot.mode6
        ]
        misfire_summary = (
            _misfire_summary_from_response(snapshot.misfire_summary)
            if snapshot.misfire_summary is not None
            else None
        )
        result = self._engine_factory().diagnose(
            vehicle,
            dtcs,
            sensor_snapshot,
            mode6_results=mode6_results,
            misfire_summary=misfire_summary,
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


def _mode6_responses(results: list[Mode6TestResult]) -> list[Mode6TestResponse]:
    return [
        Mode6TestResponse(
            monitor=result.monitor,
            monitor_description=result.monitor_description,
            category=result.category,
            test_id=result.test_id,
            test_name=result.test_name,
            description=result.description,
            value=result.value,
            minimum=result.minimum,
            maximum=result.maximum,
            unit=result.unit,
            passed=result.passed,
            status=result.status,
        )
        for result in results
    ]


def _misfire_summary_response(summary: MisfireSummary) -> MisfireSummaryResponse:
    return MisfireSummaryResponse(
        supported=summary.supported,
        status=summary.status,
        summary=summary.summary,
        findings=[
            MisfireFindingResponse(
                source=finding.source,
                severity=finding.severity,
                detail=finding.detail,
                cylinder=finding.cylinder,
                value=finding.value,
                threshold=finding.threshold,
            )
            for finding in summary.findings
        ],
    )


def _misfire_summary_from_response(summary: MisfireSummaryResponse) -> MisfireSummary:
    return MisfireSummary(
        supported=summary.supported,
        status=summary.status,
        summary=summary.summary,
        findings=[
            MisfireFinding(
                source=finding.source,
                severity=finding.severity,
                detail=finding.detail,
                cylinder=finding.cylinder,
                value=finding.value,
                threshold=finding.threshold,
            )
            for finding in summary.findings
        ],
    )


def _default_connection() -> OBDConnection:
    timeout = float(os.getenv("OPEN_MECHANIC_API_OBD_TIMEOUT", "3.0"))
    max_retries = int(os.getenv("OPEN_MECHANIC_API_OBD_RETRIES", "1"))
    return OBDConnection(timeout=timeout, max_retries=max_retries)
