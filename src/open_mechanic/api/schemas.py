from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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


class Mode6TestResponse(BaseModel):
    monitor: str
    monitor_description: str
    category: str
    test_id: int | None
    test_name: str
    description: str
    value: str
    minimum: str
    maximum: str
    unit: str | None
    passed: bool | None
    status: str


class MisfireFindingResponse(BaseModel):
    source: str
    severity: str
    detail: str
    cylinder: int | None = None
    value: str | None = None
    threshold: str | None = None


class MisfireSummaryResponse(BaseModel):
    supported: bool
    status: str
    summary: str
    findings: list[MisfireFindingResponse] = Field(default_factory=list)


class HealthSnapshotResponse(BaseModel):
    connected: bool
    port: str | None
    protocol: str | None
    sensors: list[SensorReadingResponse]
    dtcs: list[DTCResponse]
    mode6: list[Mode6TestResponse] = Field(default_factory=list)
    misfire_summary: MisfireSummaryResponse | None = None


class DiagnoseRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    year: int
    make: str
    model: str
    mileage: int
    vin: str | None = None
    bypass_cache: bool = False


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
