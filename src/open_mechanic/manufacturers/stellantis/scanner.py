"""Catalog-bounded, read-only Stellantis diagnostic orchestration."""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Protocol

from open_mechanic.manufacturers.stellantis.catalog import (
    DIDDefinition,
    ModuleDefinition,
    VehicleCatalog,
)
from open_mechanic.manufacturers.stellantis.models import (
    LiveValue,
    ModuleDTC,
    ModuleScanResult,
    ModuleState,
    StellantisScanResult,
)
from open_mechanic.protocols.elm327 import ELM327Error, ELM327TimeoutError, RawDiagnosticResponse
from open_mechanic.protocols.requests import DiagnosticRequest
from open_mechanic.protocols.uds import (
    UDSProtocolError,
    build_read_did,
    build_read_dtcs,
    parse_negative_response,
    parse_read_did,
    parse_read_dtcs,
)

_KEY_COMPONENT = re.compile(r"[^a-z0-9]+")


class DiagnosticTransport(Protocol):
    """Small read-only transport surface used by the scanner."""

    def open(self) -> None: ...

    def close(self) -> None: ...

    def exchange(self, request: DiagnosticRequest) -> list[RawDiagnosticResponse]: ...


class StellantisScanner:
    """Perform one private, bounded scan against a validated vehicle catalog."""

    def __init__(self, transport: DiagnosticTransport, catalog: VehicleCatalog) -> None:
        self._transport = transport
        self._catalog = catalog
        self._last_cruise_values: tuple[LiveValue, ...] = ()

    def scan_dtcs(self) -> StellantisScanResult:
        """Read DTCs per module while retaining successes after any module failure."""
        eligible = tuple(module for module in self._catalog.modules if 0x19 in module.services)
        results: list[ModuleScanResult] = []
        if not eligible:
            return StellantisScanResult(
                tuple(self._unsupported_scan_result(module) for module in self._catalog.modules)
            )

        try:
            self._transport.open()
            for module in self._catalog.modules:
                if module not in eligible:
                    results.append(self._unsupported_scan_result(module))
                    continue
                results.append(self._scan_module_dtcs(module))
        finally:
            self._transport.close()
        return StellantisScanResult(tuple(results))

    def read_group(self, group: str) -> tuple[LiveValue, ...]:
        """Read only cataloged DIDs in a live-data group, without DID discovery."""
        requested = tuple(
            (module, did)
            for module in self._catalog.modules
            for did in module.dids
            if did.group == group and 0x22 in module.services
        )
        if not requested:
            return tuple(
                self._not_cataloged_value(module, group) for module in self._catalog.modules
            )

        values: list[LiveValue] = []
        blocked_modules: dict[str, str] = {}
        try:
            self._transport.open()
            for module, did in requested:
                blocked_error = blocked_modules.get(module.key)
                if blocked_error is not None:
                    value = self._unavailable_value(
                        module,
                        did,
                        datetime.now(UTC),
                        ModuleState.GATEWAY_BLOCKED,
                        blocked_error,
                    )
                else:
                    value = self._read_did(module, did)
                    if value.state is ModuleState.GATEWAY_BLOCKED:
                        blocked_modules[module.key] = value.error or "security gateway denied read"
                values.append(self._with_cruise_event_marker(value) if group == "cruise" else value)
        finally:
            self._transport.close()
        if group == "cruise":
            self._last_cruise_values = tuple(values)
        return tuple(values)

    def _scan_module_dtcs(self, module: ModuleDefinition) -> ModuleScanResult:
        try:
            payload = self._exchange_payload(
                build_read_dtcs(tx_id=module.tx_id, rx_id=module.rx_id)
            )
        except (TimeoutError, ELM327TimeoutError) as error:
            return self._scan_result(module, ModuleState.TIMED_OUT, error=str(error))
        except ELM327Error as error:
            return self._scan_result(module, ModuleState.NEGATIVE_RESPONSE, error=str(error))

        state, response_error = self._response_state(payload, expected_service=0x19)
        if state is not ModuleState.RESPONDED:
            return self._scan_result(module, state, error=response_error)
        assert payload is not None
        try:
            dtcs = tuple(
                ModuleDTC(dtc.identifier, dtc.status_mask) for dtc in parse_read_dtcs(payload)
            )
        except UDSProtocolError as error:
            return self._scan_result(module, ModuleState.NEGATIVE_RESPONSE, error=str(error))
        return self._scan_result(module, ModuleState.RESPONDED, dtcs=dtcs)

    def _read_did(self, module: ModuleDefinition, did: DIDDefinition) -> LiveValue:
        timestamp = datetime.now(UTC)
        try:
            request = build_read_did(
                did.identifier,
                tx_id=module.tx_id,
                rx_id=module.rx_id,
                cataloged_dids=module.cataloged_dids,
            )
            payload = self._exchange_payload(request)
        except (TimeoutError, ELM327TimeoutError) as error:
            return self._unavailable_value(
                module, did, timestamp, ModuleState.TIMED_OUT, str(error)
            )
        except (ELM327Error, UDSProtocolError) as error:
            return self._unavailable_value(
                module, did, timestamp, ModuleState.NEGATIVE_RESPONSE, str(error)
            )

        state, response_error = self._response_state(payload, expected_service=0x22)
        if state is not ModuleState.RESPONDED:
            return self._unavailable_value(module, did, timestamp, state, response_error)
        assert payload is not None
        try:
            raw = parse_read_did(payload, did.identifier)
            return self._decoded_value(module, did, raw, timestamp)
        except UDSProtocolError as error:
            return self._unavailable_value(
                module, did, timestamp, ModuleState.NEGATIVE_RESPONSE, str(error)
            )

    def _exchange_payload(self, request: DiagnosticRequest) -> bytes | None:
        replies = self._transport.exchange(request)
        expected = tuple(
            payload
            for payload in self._payloads(replies)
            if payload[0] is None or payload[0] == request.rx_id
        )
        return expected[0][1] if expected else None

    @staticmethod
    def _payloads(
        replies: Iterable[RawDiagnosticResponse],
    ) -> Iterable[tuple[int | None, bytes]]:
        for reply in replies:
            if isinstance(reply, bytes):
                yield None, reply
            else:
                yield reply.responder_id, reply.payload

    @staticmethod
    def _response_state(
        payload: bytes | None, *, expected_service: int
    ) -> tuple[ModuleState, str | None]:
        if payload is None:
            return ModuleState.UNSUPPORTED, "no response"
        if payload[:1] != b"\x7f":
            return ModuleState.RESPONDED, None
        try:
            response = parse_negative_response(payload)
        except UDSProtocolError as error:
            return ModuleState.NEGATIVE_RESPONSE, str(error)
        if response.service != expected_service:
            return (
                ModuleState.NEGATIVE_RESPONSE,
                "negative response service mismatch: "
                f"expected 0x{expected_service:02X}, got 0x{response.service:02X} "
                f"({response.meaning}, NRC 0x{response.code:02X})",
            )
        state = (
            ModuleState.GATEWAY_BLOCKED if response.code == 0x33 else ModuleState.NEGATIVE_RESPONSE
        )
        return (
            state,
            f"negative response service 0x{response.service:02X}: "
            f"{response.meaning} (NRC 0x{response.code:02X})",
        )

    @staticmethod
    def _scan_result(
        module: ModuleDefinition,
        state: ModuleState,
        *,
        dtcs: tuple[ModuleDTC, ...] = (),
        error: str | None = None,
    ) -> ModuleScanResult:
        return ModuleScanResult(
            module.key,
            module.name,
            state,
            dtcs,
            module.source.applicability,
            error,
        )

    def _unsupported_scan_result(self, module: ModuleDefinition) -> ModuleScanResult:
        return self._scan_result(
            module,
            ModuleState.UNSUPPORTED,
            error="DTC reading is not cataloged for this module",
        )

    @staticmethod
    def _value_key(label: str) -> str:
        return _KEY_COMPONENT.sub("_", label.casefold()).strip("_")

    def _not_cataloged_value(self, module: ModuleDefinition, group: str) -> LiveValue:
        return LiveValue(
            module.key,
            group,
            group.replace("_", " ").title(),
            None,
            None,
            None,
            datetime.now(UTC),
            False,
            ModuleState.UNSUPPORTED,
            module.source.applicability,
            f"not cataloged for group {group}",
        )

    def _unavailable_value(
        self,
        module: ModuleDefinition,
        did: DIDDefinition,
        timestamp: datetime,
        state: ModuleState,
        error: str | None,
    ) -> LiveValue:
        return LiveValue(
            module.key,
            self._value_key(did.label),
            did.label,
            None,
            None,
            did.unit,
            timestamp,
            False,
            state,
            module.source.applicability,
            error,
        )

    def _decoded_value(
        self,
        module: ModuleDefinition,
        did: DIDDefinition,
        raw: bytes,
        timestamp: datetime,
    ) -> LiveValue:
        if len(raw) != did.width:
            return self._unavailable_value(
                module,
                did,
                timestamp,
                ModuleState.NEGATIVE_RESPONSE,
                f"expected {did.width} data bytes, got {len(raw)}",
            )
        if self._value_key(did.label) == "vin":
            return LiveValue(
                module.key,
                "vin",
                did.label,
                "[redacted]",
                None,
                did.unit,
                timestamp,
                True,
                ModuleState.RESPONDED,
                module.source.applicability,
            )
        raw_value = int.from_bytes(raw, "big", signed=did.signed)
        if did.enum_map:
            hex_width = did.width * 2
            value: float | str = did.enum_map.get(
                raw_value, f"unknown (0x{raw_value:0{hex_width}X})"
            )
        else:
            value = raw_value * did.scale + did.offset
        return LiveValue(
            module.key,
            self._value_key(did.label),
            did.label,
            value,
            raw_value,
            did.unit,
            timestamp,
            True,
            ModuleState.RESPONDED,
            module.source.applicability,
        )

    def _with_cruise_event_marker(self, value: LiveValue) -> LiveValue:
        if value.key != "cruise_state" or not isinstance(value.value, str):
            return value
        previous = next(
            (
                prior
                for prior in self._last_cruise_values
                if prior.module_key == value.module_key and prior.key == value.key
            ),
            None,
        )
        if (
            previous is None
            or previous.value != "engaged"
            or value.value not in {"cancelled", "unavailable"}
        ):
            return value
        return LiveValue(
            value.module_key,
            value.key,
            value.label,
            value.value,
            value.raw_value,
            value.unit,
            value.timestamp,
            value.fresh,
            value.state,
            value.applicability,
            value.error,
            f"engaged_to_{value.value}",
        )
