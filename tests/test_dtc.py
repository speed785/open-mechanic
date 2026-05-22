from __future__ import annotations

# pyright: reportMissingTypeStubs=false
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from open_mechanic import dtc
from open_mechanic.connection import OBDConnection
from open_mechanic.dtc import DTCClearNotConfirmed, DTCReader


def test_decode_returns_normalized_known_code(tmp_path: Path) -> None:
    db_path = tmp_path / "dtc_codes.json"
    _ = db_path.write_text(
        json.dumps(
            [
                {
                    "code": "P0420",
                    "description": "Catalyst system efficiency below threshold",
                    "severity": "warning",
                    "category": "emissions",
                }
            ]
        ),
        encoding="utf-8",
    )
    reader = DTCReader(OBDConnection(port="/dev/null"), dtc_db_path=str(db_path))

    decoded = reader.decode("p0420")

    assert decoded.code == "P0420"
    assert decoded.description == "Catalyst system efficiency below threshold"
    assert decoded.status == "unknown"
    assert decoded.severity == "warning"
    assert decoded.category == "emissions"


def test_decode_returns_unknown_defaults_for_missing_code(tmp_path: Path) -> None:
    db_path = tmp_path / "dtc_codes.json"
    _ = db_path.write_text("[]", encoding="utf-8")
    reader = DTCReader(OBDConnection(port="/dev/null"), dtc_db_path=str(db_path))

    decoded = reader.decode("P9999")

    assert decoded.code == "P9999"
    assert decoded.description == "Unknown code"
    assert decoded.status == "unknown"
    assert decoded.severity == "unknown"
    assert decoded.category == "unknown"


def test_clear_dtcs_requires_explicit_confirmation(tmp_path: Path) -> None:
    db_path = tmp_path / "dtc_codes.json"
    _ = db_path.write_text("[]", encoding="utf-8")
    reader = DTCReader(OBDConnection(port="/dev/null"), dtc_db_path=str(db_path))

    with pytest.raises(DTCClearNotConfirmed):
        _ = reader.clear_dtcs()


def test_default_dtc_database_loads_outside_repository_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    reader = DTCReader(OBDConnection(port="/dev/null"))

    decoded = reader.decode("P0420")

    assert decoded.code == "P0420"
    assert decoded.description != "Unknown code"
    assert decoded.severity != "unknown"


@pytest.mark.parametrize("payload", ["{", "{}", '[{"code": ""}, 12, {"code": 123}]'])
def test_dtc_database_invalid_payloads_fall_back_to_unknown(tmp_path: Path, payload: str) -> None:
    db_path = tmp_path / "dtc_codes.json"
    db_path.write_text(payload, encoding="utf-8")
    reader = DTCReader(OBDConnection(port="/dev/null"), dtc_db_path=str(db_path))

    assert reader.decode("P0420").description == "Unknown code"


def test_missing_explicit_dtc_database_path_falls_back_to_unknown(tmp_path: Path) -> None:
    reader = DTCReader(OBDConnection(port="/dev/null"), dtc_db_path=str(tmp_path / "missing.json"))

    assert reader.decode("P0420").description == "Unknown code"


class _FakeConnectionWrapper:
    def __init__(self, raw_connection: object | None, connected: bool = True) -> None:
        self._raw_connection = raw_connection
        self._connected = connected

    def get_connection(self) -> object | None:
        return self._raw_connection

    def is_connected(self) -> bool:
        return self._connected


class _FakeResponse:
    def __init__(self, value: object, null: bool = False) -> None:
        self.value = value
        self._null = null

    def is_null(self) -> bool:
        return self._null


class _FakeRawConnection:
    def __init__(self, responses: dict[object, _FakeResponse], fail: bool = False) -> None:
        self.responses = responses
        self.fail = fail
        self.queries: list[object] = []

    def query(self, command: object) -> _FakeResponse:
        if self.fail:
            raise RuntimeError("boom")
        self.queries.append(command)
        return self.responses[command]


def test_get_dtcs_reads_pending_and_confirmed_codes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "dtc_codes.json"
    db_path.write_text(
        json.dumps(
            [
                {
                    "code": "P0420",
                    "description": "Catalyst system efficiency below threshold",
                    "severity": "warning",
                    "category": "emissions",
                },
                {
                    "code": "P0171",
                    "description": "System too lean",
                    "severity": "critical",
                    "category": "fuel",
                },
            ]
        ),
        encoding="utf-8",
    )
    pending_command = object()
    confirmed_command = object()
    raw_connection = _FakeRawConnection(
        {
            pending_command: _FakeResponse([("P0420", "pending")]),
            confirmed_command: _FakeResponse([("P0171", "confirmed"), ("P0420", "confirmed")]),
        }
    )
    monkeypatch.setattr(
        dtc.obd,
        "commands",
        SimpleNamespace(GET_CURRENT_DTC=pending_command, GET_DTC=confirmed_command),
    )
    reader = DTCReader(
        _FakeConnectionWrapper(raw_connection),  # type: ignore[arg-type]
        dtc_db_path=str(db_path),
    )

    codes = reader.get_dtcs()

    assert [(code.code, code.status, code.severity) for code in codes] == [
        ("P0171", "confirmed", "critical"),
        ("P0420", "confirmed", "warning"),
    ]


def test_get_dtcs_returns_empty_when_disconnected() -> None:
    reader = DTCReader(_FakeConnectionWrapper(None, connected=False))  # type: ignore[arg-type]

    assert reader.get_dtcs() == []


def test_clear_dtcs_confirmed_queries_clear_command(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_command = object()
    raw_connection = _FakeRawConnection({clear_command: _FakeResponse(None)})
    monkeypatch.setattr(dtc.obd, "commands", SimpleNamespace(CLEAR_DTC=clear_command))
    reader = DTCReader(_FakeConnectionWrapper(raw_connection))  # type: ignore[arg-type]

    assert reader.clear_dtcs(confirmed=True) is True
    assert raw_connection.queries == [clear_command]


def test_read_dtc_command_ignores_invalid_responses(monkeypatch: pytest.MonkeyPatch) -> None:
    command = object()
    raw_connection = _FakeRawConnection(
        {
            command: _FakeResponse(
                [
                    (),
                    (123,),
                    ("",),
                    ("P9999",),
                ]
            )
        }
    )
    reader = DTCReader(_FakeConnectionWrapper(raw_connection))  # type: ignore[arg-type]

    codes = reader._read_dtc_command(command, "pending")

    assert [code.code for code in codes] == ["P9999"]
    assert codes[0].description == "Unknown code"


def test_read_dtc_command_returns_empty_for_query_errors() -> None:
    reader = DTCReader(_FakeConnectionWrapper(_FakeRawConnection({}, fail=True)))  # type: ignore[arg-type]

    assert reader._read_dtc_command(object(), "pending") == []


def test_read_dtc_command_returns_empty_without_raw_connection() -> None:
    reader = DTCReader(_FakeConnectionWrapper(None))  # type: ignore[arg-type]

    assert reader._read_dtc_command(object(), "pending") == []


@pytest.mark.parametrize("response", [None, _FakeResponse(None), _FakeResponse("P0420")])
def test_read_dtc_command_returns_empty_for_empty_or_non_list_response(response: object) -> None:
    command = object()
    raw_connection = _FakeRawConnection({command: response})  # type: ignore[dict-item]
    reader = DTCReader(_FakeConnectionWrapper(raw_connection))  # type: ignore[arg-type]

    assert reader._read_dtc_command(command, "pending") == []


def test_get_dtcs_returns_empty_when_commands_are_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dtc.obd, "commands", SimpleNamespace())
    reader = DTCReader(_FakeConnectionWrapper(_FakeRawConnection({})))  # type: ignore[arg-type]

    assert reader.get_dtcs() == []


def test_clear_dtcs_returns_false_when_disconnected_or_command_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader = DTCReader(_FakeConnectionWrapper(None, connected=False))  # type: ignore[arg-type]
    assert reader.clear_dtcs(confirmed=True) is False

    monkeypatch.setattr(dtc.obd, "commands", SimpleNamespace())
    reader = DTCReader(_FakeConnectionWrapper(_FakeRawConnection({})))  # type: ignore[arg-type]
    assert reader.clear_dtcs(confirmed=True) is False


def test_clear_dtcs_returns_false_on_query_error(monkeypatch: pytest.MonkeyPatch) -> None:
    command = object()
    monkeypatch.setattr(dtc.obd, "commands", SimpleNamespace(CLEAR_DTC=command))
    reader = DTCReader(_FakeConnectionWrapper(_FakeRawConnection({}, fail=True)))  # type: ignore[arg-type]

    assert reader.clear_dtcs(confirmed=True) is False
