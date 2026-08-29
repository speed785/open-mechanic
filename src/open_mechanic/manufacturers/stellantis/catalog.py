"""Immutable, provenance-checked Stellantis vehicle catalogs."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from importlib import resources
from ipaddress import ip_address
from types import MappingProxyType
from typing import cast
from urllib.parse import urlsplit

_CATALOG_NAME = re.compile(r"[a-z0-9_]+")
_HEX_VALUE = re.compile(r"0x[0-9A-Fa-f]+")
_DNS_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")
_IPV4_CANDIDATE = re.compile(r"[0-9.]+")
_SAFE_SERVICES = frozenset({0x19, 0x22, 0x3E})
_PROVENANCE_CLASSIFICATIONS = frozenset(
    {
        ("vehicle_fixture", "exact_model_year"),
        ("community_reference", "community_unverified"),
    }
)


class CatalogValidationError(ValueError):
    """Raised when packaged catalog data is missing, malformed, or unsafe."""


@dataclass(frozen=True, slots=True)
class Provenance:
    """Short public-source metadata for a catalog entry."""

    document: str
    url: str
    evidence: str
    applicability: str


@dataclass(frozen=True, slots=True)
class DIDDefinition:
    """One source-verified UDS ReadDataByIdentifier decoding rule."""

    identifier: int
    label: str
    group: str
    signed: bool
    width: int
    scale: float
    offset: float
    unit: str | None
    enum_map: Mapping[int, str]
    source: Provenance


@dataclass(frozen=True, slots=True)
class ModuleDefinition:
    """One catalog-approved physical diagnostic module."""

    key: str
    name: str
    role: str
    tx_id: int
    rx_id: int
    services: frozenset[int]
    dids: tuple[DIDDefinition, ...]
    source: Provenance
    cataloged_dids: frozenset[int] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "cataloged_dids", frozenset(did.identifier for did in self.dids))


@dataclass(frozen=True, slots=True)
class VehicleCatalog:
    """A validated manufacturer catalog for one vehicle family and model year."""

    key: str
    name: str
    model_year: int
    modules: tuple[ModuleDefinition, ...]


def _mapping(value: object, field_name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise CatalogValidationError(f"{field_name} must be an object")
    return cast(dict[str, object], value)


def _list(value: object, field_name: str) -> list[object]:
    if not isinstance(value, list):
        raise CatalogValidationError(f"{field_name} must be an array")
    return value


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CatalogValidationError(f"{field_name} must be a non-empty string")
    return value


def _integer(value: object, field_name: str, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise CatalogValidationError(f"{field_name} must be an integer from {minimum} to {maximum}")
    return value


def _hex_integer(value: object, field_name: str, *, maximum: int) -> int:
    if not isinstance(value, str) or _HEX_VALUE.fullmatch(value) is None:
        raise CatalogValidationError(f"{field_name} must be a hexadecimal string")
    parsed = int(value, 16)
    if parsed > maximum:
        raise CatalogValidationError(f"{field_name} exceeds 0x{maximum:X}")
    return parsed


def _finite_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise CatalogValidationError(f"{field_name} must be finite")
    try:
        parsed = float(value)
    except OverflowError as exc:
        raise CatalogValidationError(f"{field_name} must be finite") from exc
    if not math.isfinite(parsed):
        raise CatalogValidationError(f"{field_name} must be finite")
    return parsed


def _is_valid_network_host(hostname: str) -> bool:
    try:
        ip_address(hostname)
    except ValueError:
        if ":" in hostname or _IPV4_CANDIDATE.fullmatch(hostname) is not None:
            return False
        return len(hostname) <= 253 and all(
            _DNS_LABEL.fullmatch(label) is not None for label in hostname.split(".")
        )
    return True


def _is_https_url_with_network_location(value: str) -> bool:
    # urlsplit normalizes some raw controls, so reject them before parsing.
    if any(
        character.isspace() or ord(character) < 0x20 or ord(character) == 0x7F
        for character in value
    ):
        return False
    try:
        parsed = urlsplit(value)
        _port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.hostname is not None
        and _is_valid_network_host(parsed.hostname)
    )


def _parse_source(value: object) -> Provenance:
    raw = _mapping(value, "provenance")
    document = raw.get("document")
    url = raw.get("url")
    evidence = raw.get("evidence")
    applicability = raw.get("applicability")
    if (
        not isinstance(document, str)
        or not document.strip()
        or not isinstance(url, str)
        or not _is_https_url_with_network_location(url)
    ):
        raise CatalogValidationError("provenance requires a document and HTTPS URL")
    if (
        not isinstance(evidence, str)
        or not isinstance(applicability, str)
        or (evidence, applicability) not in _PROVENANCE_CLASSIFICATIONS
    ):
        raise CatalogValidationError(
            "provenance has an unsupported evidence or applicability value"
        )
    return Provenance(
        document=document,
        url=url,
        evidence=evidence,
        applicability=applicability,
    )


def _parse_enum_map(value: object, *, width: int, signed: bool) -> Mapping[int, str]:
    raw = _mapping(value, "DID enum_map")
    parsed: dict[int, str] = {}
    bit_width = width * 8
    minimum = -(1 << (bit_width - 1)) if signed else 0
    maximum = (1 << (bit_width - 1)) - 1 if signed else (1 << bit_width) - 1
    for key, label_value in raw.items():
        try:
            enum_key = int(key, 0)
        except ValueError as exc:
            raise CatalogValidationError("DID enum_map keys must be integers") from exc
        if enum_key in parsed:
            raise CatalogValidationError("DID enum_map contains duplicate integer keys")
        if not minimum <= enum_key <= maximum:
            raise CatalogValidationError("DID enum_map key is not representable by its width")
        parsed[enum_key] = _text(label_value, "DID enum label")
    return MappingProxyType(parsed)


def _parse_did(value: object) -> DIDDefinition:
    raw = _mapping(value, "DID")
    identifier = _hex_integer(raw["identifier"], "DID identifier", maximum=0xFFFF)
    group = _text(raw["group"], "DID group")
    signed = raw["signed"]
    if type(signed) is not bool:
        raise CatalogValidationError("DID signed must be a boolean")
    width = _integer(raw["width"], "DID width", minimum=1, maximum=8)
    unit_value = raw["unit"]
    unit = None if unit_value is None else _text(unit_value, "DID unit")
    enum_map = _parse_enum_map(raw["enum_map"], width=width, signed=signed)
    if group == "cruise" and unit is None and not enum_map:
        raise CatalogValidationError("cruise DID requires a unit or enum mapping")
    return DIDDefinition(
        identifier=identifier,
        label=_text(raw["label"], "DID label"),
        group=group,
        signed=signed,
        width=width,
        scale=_finite_number(raw["scale"], "DID scale"),
        offset=_finite_number(raw["offset"], "DID offset"),
        unit=unit,
        enum_map=enum_map,
        source=_parse_source(raw["source"]),
    )


def _parse_module(value: object) -> ModuleDefinition:
    raw = _mapping(value, "module")
    service_values = _list(raw["services"], "module services")
    services = frozenset(
        _hex_integer(service, "module service", maximum=0xFF) for service in service_values
    )
    if not services or not services <= _SAFE_SERVICES:
        raise CatalogValidationError("module contains an unsupported service")
    dids = tuple(_parse_did(did) for did in _list(raw["dids"], "module DIDs"))
    did_identifiers = [did.identifier for did in dids]
    if len(did_identifiers) != len(set(did_identifiers)):
        raise CatalogValidationError("module contains a duplicate DID")
    if dids and 0x22 not in services:
        raise CatalogValidationError("module with DIDs must allow service 0x22")
    return ModuleDefinition(
        key=_text(raw["key"], "module key"),
        name=_text(raw["name"], "module name"),
        role=_text(raw["role"], "module role"),
        tx_id=_hex_integer(raw["tx_id"], "module tx_id", maximum=0x7FF),
        rx_id=_hex_integer(raw["rx_id"], "module rx_id", maximum=0x7FF),
        services=services,
        dids=dids,
        source=_parse_source(raw["source"]),
    )


def _parse_catalog(value: object) -> VehicleCatalog:
    raw = _mapping(value, "catalog")
    try:
        modules = tuple(_parse_module(module) for module in _list(raw["modules"], "modules"))
        catalog = VehicleCatalog(
            key=_text(raw["key"], "catalog key"),
            name=_text(raw["name"], "catalog name"),
            model_year=_integer(raw["model_year"], "model_year", minimum=1886, maximum=9999),
            modules=modules,
        )
    except KeyError as exc:
        raise CatalogValidationError(f"missing catalog field: {exc.args[0]}") from None
    if not catalog.modules:
        raise CatalogValidationError("catalog must contain at least one module")
    module_keys = [module.key for module in catalog.modules]
    if len(module_keys) != len(set(module_keys)):
        raise CatalogValidationError("catalog contains a duplicate module key")
    tx_ids = [module.tx_id for module in catalog.modules]
    if len(tx_ids) != len(set(tx_ids)):
        raise CatalogValidationError("catalog contains a duplicate tx_id")
    rx_ids = [module.rx_id for module in catalog.modules]
    if len(rx_ids) != len(set(rx_ids)):
        raise CatalogValidationError("catalog contains a duplicate rx_id")
    return catalog


def load_catalog(name: str) -> VehicleCatalog:
    """Load and validate one packaged Stellantis catalog by stable key."""
    if not isinstance(name, str) or _CATALOG_NAME.fullmatch(name) is None:
        raise CatalogValidationError(
            "catalog name must contain only lowercase letters, digits, and underscores"
        )
    try:
        text = (
            resources.files(__package__)
            .joinpath("catalogs", f"{name}.json")
            .read_text(encoding="utf-8")
        )
    except (FileNotFoundError, ModuleNotFoundError, OSError) as exc:
        raise CatalogValidationError(f"catalog {name!r} is not available") from exc
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CatalogValidationError(f"catalog {name!r} is not valid JSON") from exc
    catalog = _parse_catalog(decoded)
    if catalog.key != name:
        raise CatalogValidationError("catalog key does not match its resource name")
    return catalog
