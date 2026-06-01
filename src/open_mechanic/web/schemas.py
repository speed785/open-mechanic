from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class VehicleProfileResponse(BaseModel):
    year: int
    make: str
    model: str
    mileage: int | None = None
    vin: str | None = None
    label: str


class VehicleProfileRequest(BaseModel):
    year: int = Field(ge=1900, le=2100)
    make: str = Field(min_length=1)
    model: str = Field(min_length=1)
    mileage: int = Field(ge=0)
    vin: str | None = None


class StatusResponse(BaseModel):
    version: str
    connected: bool
    offline: bool = False
    adapter_state: str = "disconnected"
    adapter_message: str | None = None
    port: str | None
    protocol: str | None
    provider_name: str
    provider_configured: bool
    vehicle_profile: VehicleProfileResponse | None
    latest_poll_at: datetime | None


class ConnectRequest(BaseModel):
    port: str | None = None
    protocol: str | None = None
    baudrate: int = 115200
    timeout: float = 10.0
    offline: bool = False


class SensorReadingResponse(BaseModel):
    name: str
    value: str
    unit: str | None
    timestamp: datetime
    supported: bool


class SensorResponse(BaseModel):
    sensors: list[SensorReadingResponse]


class DTCResponseItem(BaseModel):
    code: str
    description: str
    status: str
    severity: str
    category: str


class DTCResponse(BaseModel):
    dtcs: list[DTCResponseItem]


class DiagnosisRequest(BaseModel):
    vehicle: VehicleProfileRequest
    generated_at: datetime | None = None


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
    vehicle: str
    provider: str
    cached: bool = False


class ReportSummary(BaseModel):
    filename: str
    path: str
    created_at: datetime | None
    severity: str | None = None
    summary: str | None = None
    vehicle: str | None = None
    provider: str | None = None


class ReportListResponse(BaseModel):
    reports: list[ReportSummary]


class MessageResponse(BaseModel):
    ok: bool
    message: str
