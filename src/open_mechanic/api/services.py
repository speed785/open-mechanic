from __future__ import annotations

import os
import time
from collections.abc import Callable

from open_mechanic.ai.diagnose import DiagnosticEngine
from open_mechanic.connection import OBDConnection
from open_mechanic.db.models import VehicleProfile as DiagnosticVehicleProfile
from open_mechanic.dtc import DTCCode, DTCReader
from open_mechanic.local_store import VehicleProfile as LocalVehicleProfile
from open_mechanic.manufacturers.stellantis.catalog import VehicleCatalog, load_catalog
from open_mechanic.manufacturers.stellantis.cli import dtc_status_flags, validate_live_bounds
from open_mechanic.manufacturers.stellantis.scanner import StellantisScanner
from open_mechanic.protocols.elm327 import ELM327Transport
from open_mechanic.reader import SensorPoller, SensorValue

from .schemas import (
    DiagnoseRequest,
    DiagnosisResponse,
    DTCResponse,
    HealthSnapshotResponse,
    ProvenanceResponse,
    SensorReadingResponse,
    StellantisDTCResponse,
    StellantisLiveResponse,
    StellantisLiveSampleResponse,
    StellantisLiveValueResponse,
    StellantisModuleResponse,
    StellantisScanResponse,
    VehicleProfileResponse,
)

ConnectionFactory = Callable[[], OBDConnection]
ProfileLoader = Callable[[], LocalVehicleProfile | None]
EngineFactory = Callable[[], DiagnosticEngine]
StellantisScannerFactory = Callable[[str, float, VehicleCatalog], StellantisScanner]


class DiagnosticAPIService:
    def __init__(
        self,
        connection_factory: ConnectionFactory | None = None,
        profile_loader: ProfileLoader = lambda: None,
        engine_factory: EngineFactory | None = None,
        stellantis_scanner_factory: StellantisScannerFactory | None = None,
    ) -> None:
        self._connection_factory = connection_factory or _default_connection
        self._profile_loader = profile_loader
        self._engine_factory = engine_factory or DiagnosticEngine
        self._stellantis_scanner_factory = stellantis_scanner_factory or _default_stellantis_scanner

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
            external_sharing_authorized=request.external_sharing_authorized,
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

    def get_stellantis_dtcs(
        self, vehicle: str, port: str, timeout: float
    ) -> StellantisScanResponse:
        catalog = load_catalog(vehicle)
        scanner = self._stellantis_scanner_factory(port, timeout, catalog)
        result = scanner.scan_dtcs()
        modules = []
        by_key = {module.key: module for module in catalog.modules}
        for module in result.modules:
            source = by_key[module.module_key].source
            modules.append(
                StellantisModuleResponse(
                    module_key=module.module_key,
                    module_name=module.module_name,
                    state=module.state.value,
                    dtcs=[
                        StellantisDTCResponse(
                            identifier=dtc.identifier,
                            display=f"0x{dtc.identifier:06X}",
                            definition="unknown",
                            status_mask=dtc.status_mask,
                            status_flags=list(dtc_status_flags(dtc.status_mask)),
                        )
                        for dtc in module.dtcs
                    ],
                    provenance=_provenance_response(source),
                    error=module.error,
                )
            )
        return StellantisScanResponse(vehicle=vehicle, modules=modules)

    def get_stellantis_live(
        self,
        vehicle: str,
        group: str,
        port: str,
        timeout: float,
        *,
        samples: int,
        interval: float,
    ) -> StellantisLiveResponse:
        validate_live_bounds(samples, interval)
        catalog = load_catalog(vehicle)
        scanner = self._stellantis_scanner_factory(port, timeout, catalog)
        by_key = {module.key: module for module in catalog.modules}
        rendered_samples = []
        for sample in range(1, samples + 1):
            values = scanner.read_group(group)
            rendered_samples.append(
                StellantisLiveSampleResponse(
                    sample=sample,
                    values=[
                        StellantisLiveValueResponse(
                            module_key=value.module_key,
                            key=value.key,
                            label=value.label,
                            value=value.value,
                            raw_value=value.raw_value,
                            unit=value.unit,
                            timestamp=value.timestamp,
                            fresh=value.fresh,
                            state=value.state.value,
                            provenance=_provenance_response(by_key[value.module_key].source),
                            error=value.error,
                            event_marker=value.event_marker,
                        )
                        for value in values
                    ],
                )
            )
            if sample < samples:
                time.sleep(interval)
        return StellantisLiveResponse(vehicle=vehicle, group=group, samples=rendered_samples)


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


def _default_stellantis_scanner(
    port: str, timeout: float, catalog: VehicleCatalog
) -> StellantisScanner:
    return StellantisScanner(ELM327Transport(port, timeout=timeout), catalog)


def _provenance_response(source: object) -> ProvenanceResponse:
    return ProvenanceResponse.model_validate(source, from_attributes=True)
