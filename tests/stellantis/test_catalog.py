from __future__ import annotations

import json
from types import MappingProxyType
from typing import Any

import pytest

from open_mechanic.manufacturers.stellantis.catalog import (
    CatalogValidationError,
    load_catalog,
)
from open_mechanic.protocols.uds import build_read_did


class _CatalogResource:
    def __init__(self, text: str) -> None:
        self._text = text

    def joinpath(self, *path_segments: str) -> _CatalogResource:
        return self

    def read_text(self, encoding: str | None = None) -> str:
        return self._text


class _MissingCatalogResource(_CatalogResource):
    def read_text(self, encoding: str | None = None) -> str:
        raise FileNotFoundError


def _valid_catalog_data() -> dict[str, Any]:
    return {
        "key": "synthetic",
        "name": "Synthetic test vehicle",
        "model_year": 2024,
        "modules": [
            {
                "key": "synthetic_control",
                "name": "Synthetic Control Module",
                "role": "test",
                "tx_id": "0x600",
                "rx_id": "0x608",
                "services": ["0x19", "0x22"],
                "source": {
                    "document": "Synthetic public protocol fixture",
                    "url": "https://example.test/protocol",
                },
                "dids": [
                    {
                        "identifier": "0x1234",
                        "label": "Synthetic cruise state",
                        "group": "cruise",
                        "signed": False,
                        "width": 1,
                        "scale": 1.0,
                        "offset": 0.0,
                        "unit": None,
                        "enum_map": {"0": "inactive", "1": "active"},
                        "source": {
                            "document": "Synthetic public protocol fixture",
                            "url": "https://example.test/protocol#did-1234",
                        },
                    }
                ],
            }
        ],
    }


def _install_catalog(
    monkeypatch: pytest.MonkeyPatch,
    data: object,
    *,
    raw_text: str | None = None,
) -> None:
    text = json.dumps(data) if raw_text is None else raw_text
    resource = _CatalogResource(text)
    monkeypatch.setattr(
        "open_mechanic.manufacturers.stellantis.catalog.resources.files",
        lambda package: resource,
    )


def test_2024_4xe_catalog_contains_required_module_roles() -> None:
    catalog = load_catalog("wrangler_jl_4xe_2024")
    assert {module.role for module in catalog.modules} >= {
        "powertrain",
        "hybrid",
        "transmission",
        "abs_esc",
        "steering",
        "body_gateway",
        "cluster",
        "adas",
    }


def test_every_cataloged_address_and_did_has_provenance() -> None:
    catalog = load_catalog("wrangler_jl_4xe_2024")
    for module in catalog.modules:
        assert module.source.document
        assert module.source.url.startswith("https://")
        for did in module.dids:
            assert did.source.document
            assert did.source.url.startswith("https://")


def test_catalog_exposes_only_immutable_scanner_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_catalog(monkeypatch, _valid_catalog_data())

    catalog = load_catalog("synthetic")
    module = catalog.modules[0]
    did = module.dids[0]

    assert isinstance(catalog.modules, tuple)
    assert isinstance(module.services, frozenset)
    assert isinstance(module.dids, tuple)
    assert module.cataloged_dids == frozenset({0x1234})
    assert isinstance(module.cataloged_dids, frozenset)
    assert isinstance(did.enum_map, MappingProxyType)
    assert build_read_did(
        0x1234,
        tx_id=module.tx_id,
        rx_id=module.rx_id,
        cataloged_dids=module.cataloged_dids,
    ).payload == bytes.fromhex("221234")


def test_rejects_duplicate_can_pairs(monkeypatch: pytest.MonkeyPatch) -> None:
    data = _valid_catalog_data()
    duplicate = dict(data["modules"][0])
    duplicate["key"] = "duplicate_control"
    duplicate["role"] = "duplicate"
    data["modules"].append(duplicate)
    _install_catalog(monkeypatch, data)

    with pytest.raises(CatalogValidationError, match="duplicate CAN pair"):
        load_catalog("synthetic")


def test_rejects_duplicate_dids_within_a_module(monkeypatch: pytest.MonkeyPatch) -> None:
    data = _valid_catalog_data()
    data["modules"][0]["dids"].append(dict(data["modules"][0]["dids"][0]))
    _install_catalog(monkeypatch, data)

    with pytest.raises(CatalogValidationError, match="duplicate DID"):
        load_catalog("synthetic")


def test_rejects_unsupported_service_values(monkeypatch: pytest.MonkeyPatch) -> None:
    data = _valid_catalog_data()
    data["modules"][0]["services"] = ["0x27"]
    _install_catalog(monkeypatch, data)

    with pytest.raises(CatalogValidationError, match="unsupported service"):
        load_catalog("synthetic")


@pytest.mark.parametrize("target", ["module", "did"])
def test_rejects_missing_provenance(
    monkeypatch: pytest.MonkeyPatch,
    target: str,
) -> None:
    data = _valid_catalog_data()
    if target == "module":
        data["modules"][0]["source"]["document"] = ""
    else:
        data["modules"][0]["dids"][0]["source"]["url"] = "http://not-secure.test"
    _install_catalog(monkeypatch, data)

    with pytest.raises(CatalogValidationError, match="provenance"):
        load_catalog("synthetic")


@pytest.mark.parametrize(
    ("field", "value"),
    [("scale", float("nan")), ("offset", float("inf"))],
)
def test_rejects_non_finite_scaling(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: float,
) -> None:
    data = _valid_catalog_data()
    data["modules"][0]["dids"][0][field] = value
    _install_catalog(monkeypatch, data)

    with pytest.raises(CatalogValidationError, match="finite"):
        load_catalog("synthetic")


def test_rejects_cruise_did_without_unit_or_enum_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _valid_catalog_data()
    data["modules"][0]["dids"][0]["enum_map"] = {}
    _install_catalog(monkeypatch, data)

    with pytest.raises(CatalogValidationError, match="cruise DID"):
        load_catalog("synthetic")


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ([], "catalog must be an object"),
        ({"modules": {}}, "modules must be an array"),
        ({"modules": []}, "missing catalog field"),
    ],
)
def test_rejects_malformed_catalog_schema(
    monkeypatch: pytest.MonkeyPatch,
    data: object,
    message: str,
) -> None:
    _install_catalog(monkeypatch, data)

    with pytest.raises(CatalogValidationError, match=message):
        load_catalog("synthetic")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("name", "", "non-empty string"),
        ("model_year", True, "must be an integer"),
    ],
)
def test_rejects_invalid_catalog_scalar(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
    message: str,
) -> None:
    data = _valid_catalog_data()
    data[field] = value
    _install_catalog(monkeypatch, data)

    with pytest.raises(CatalogValidationError, match=message):
        load_catalog("synthetic")


@pytest.mark.parametrize(
    ("value", "message"),
    [("7E0", "hexadecimal string"), ("0x800", "exceeds 0x7FF")],
)
def test_rejects_invalid_physical_address(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
    message: str,
) -> None:
    data = _valid_catalog_data()
    data["modules"][0]["tx_id"] = value
    _install_catalog(monkeypatch, data)

    with pytest.raises(CatalogValidationError, match=message):
        load_catalog("synthetic")


@pytest.mark.parametrize(
    ("enum_map", "message"),
    [
        ({"not-an-int": "invalid"}, "keys must be integers"),
        ({"1": "active", "0x1": "duplicate"}, "duplicate integer keys"),
    ],
)
def test_rejects_invalid_enum_map(
    monkeypatch: pytest.MonkeyPatch,
    enum_map: dict[str, str],
    message: str,
) -> None:
    data = _valid_catalog_data()
    data["modules"][0]["dids"][0]["enum_map"] = enum_map
    _install_catalog(monkeypatch, data)

    with pytest.raises(CatalogValidationError, match=message):
        load_catalog("synthetic")


def test_rejects_non_boolean_did_signedness(monkeypatch: pytest.MonkeyPatch) -> None:
    data = _valid_catalog_data()
    data["modules"][0]["dids"][0]["signed"] = 0
    _install_catalog(monkeypatch, data)

    with pytest.raises(CatalogValidationError, match="signed must be a boolean"):
        load_catalog("synthetic")


def test_requires_read_service_when_module_has_dids(monkeypatch: pytest.MonkeyPatch) -> None:
    data = _valid_catalog_data()
    data["modules"][0]["services"] = ["0x19"]
    _install_catalog(monkeypatch, data)

    with pytest.raises(CatalogValidationError, match="must allow service 0x22"):
        load_catalog("synthetic")


def test_rejects_empty_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    data = _valid_catalog_data()
    data["modules"] = []
    _install_catalog(monkeypatch, data)

    with pytest.raises(CatalogValidationError, match="at least one module"):
        load_catalog("synthetic")


def test_rejects_duplicate_module_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    data = _valid_catalog_data()
    duplicate = dict(data["modules"][0])
    duplicate["tx_id"] = "0x601"
    duplicate["rx_id"] = "0x609"
    data["modules"].append(duplicate)
    _install_catalog(monkeypatch, data)

    with pytest.raises(CatalogValidationError, match="duplicate module key"):
        load_catalog("synthetic")


def test_rejects_unsafe_catalog_name() -> None:
    with pytest.raises(CatalogValidationError, match="catalog name"):
        load_catalog("../synthetic")


def test_reports_missing_catalog_resource(monkeypatch: pytest.MonkeyPatch) -> None:
    resource = _MissingCatalogResource("")
    monkeypatch.setattr(
        "open_mechanic.manufacturers.stellantis.catalog.resources.files",
        lambda package: resource,
    )

    with pytest.raises(CatalogValidationError, match="not available"):
        load_catalog("synthetic")


def test_rejects_invalid_catalog_json(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_catalog(monkeypatch, {}, raw_text="{")

    with pytest.raises(CatalogValidationError, match="not valid JSON"):
        load_catalog("synthetic")


def test_rejects_resource_with_mismatched_key(monkeypatch: pytest.MonkeyPatch) -> None:
    data = _valid_catalog_data()
    data["key"] = "different"
    _install_catalog(monkeypatch, data)

    with pytest.raises(CatalogValidationError, match="does not match"):
        load_catalog("synthetic")
