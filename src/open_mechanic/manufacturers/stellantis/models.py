"""Immutable results for bounded Stellantis diagnostic reads."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ModuleState(StrEnum):
    """Observable result of one cataloged module request."""

    RESPONDED = "responded"
    UNSUPPORTED = "unsupported"
    TIMED_OUT = "timed_out"
    NEGATIVE_RESPONSE = "negative_response"
    GATEWAY_BLOCKED = "gateway_blocked"


@dataclass(frozen=True, slots=True)
class ModuleDTC:
    """A three-byte UDS DTC and its unmodified status byte."""

    identifier: int
    status_mask: int


@dataclass(frozen=True, slots=True)
class LiveValue:
    """One ephemeral, catalog-decoded live reading or unavailable result."""

    module_key: str
    key: str
    label: str
    value: float | str | None
    raw_value: int | None
    unit: str | None
    timestamp: datetime
    fresh: bool
    state: ModuleState
    applicability: str
    error: str | None = None
    event_marker: str | None = None


@dataclass(frozen=True, slots=True)
class ModuleScanResult:
    """DTC result for one cataloged module, including partial failures."""

    module_key: str
    module_name: str
    state: ModuleState
    dtcs: tuple[ModuleDTC, ...]
    applicability: str
    error: str | None = None


@dataclass(frozen=True, slots=True)
class StellantisScanResult:
    """Immutable in-memory collection of all module DTC results."""

    modules: tuple[ModuleScanResult, ...]

    def module(self, key: str) -> ModuleScanResult:
        """Return a result by stable catalog module key."""
        for module in self.modules:
            if module.module_key == key:
                return module
        raise KeyError(f"module {key!r} is not present in this scan")
