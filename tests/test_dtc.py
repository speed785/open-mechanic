from __future__ import annotations

# pyright: reportMissingTypeStubs=false
import json
from pathlib import Path

import pytest

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
