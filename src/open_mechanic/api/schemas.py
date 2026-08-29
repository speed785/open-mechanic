from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    status: str
    service: str


class VehicleProfileResponse(BaseModel):
    configured: bool
    year: int | None = None
    make: str | None = None
    model: str | None = None
    mileage: int | None = None


class SensorReadingResponse(BaseModel):
    name: str
    value: str
    unit: str | None
    supported: bool
    timestamp: datetime


class DTCResponse(BaseModel):
    code: str
    description: str
    status: str
    severity: str
    category: str


class HealthSnapshotResponse(BaseModel):
    connected: bool
    port: str | None
    protocol: str | None
    sensors: list[SensorReadingResponse]
    dtcs: list[DTCResponse]


class DiagnoseRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    year: int
    make: str
    model: str
    mileage: int
    vin: str | None = None
    external_sharing_authorized: bool = False


class DiagnosisResponse(BaseModel):
    severity: str
    summary: str
    likely_causes: list[str]
    repair_steps: list[str]
    estimated_cost_usd: dict[str, int]
    diy_feasible: bool
    diy_difficulty: str
    urgency: str
    disclaimer: str
    dtc_codes: list[str]
    vehicle_str: str
    cached: bool
    timestamp: datetime


class ProvenanceResponse(BaseModel):
    document: str
    url: str
    evidence: str
    applicability: str


class StellantisDTCResponse(BaseModel):
    identifier: int
    display: str
    definition: str
    status_mask: int
    status_flags: list[str]


class StellantisModuleResponse(BaseModel):
    module_key: str
    module_name: str
    state: str
    dtcs: list[StellantisDTCResponse]
    provenance: ProvenanceResponse
    error: str | None


class StellantisScanResponse(BaseModel):
    vehicle: str
    modules: list[StellantisModuleResponse]


class StellantisLiveValueResponse(BaseModel):
    module_key: str
    key: str
    label: str
    value: float | str | None
    raw_value: int | None
    unit: str | None
    timestamp: datetime
    fresh: bool
    state: str
    provenance: ProvenanceResponse
    error: str | None
    event_marker: str | None


class StellantisLiveSampleResponse(BaseModel):
    sample: int
    values: list[StellantisLiveValueResponse]


class StellantisLiveResponse(BaseModel):
    vehicle: str
    group: str
    samples: list[StellantisLiveSampleResponse]
