from __future__ import annotations

import json
from pathlib import Path

import pytest

from open_mechanic.local_store import (
    PROFILE_PATH,
    SESSIONS_DIR,
    SessionLog,
    VehicleProfile,
    ensure_local_dirs,
    load_vehicle_profile,
    save_vehicle_profile,
)


def test_vehicle_profile_label_omits_empty_parts() -> None:
    profile = VehicleProfile(year=2018, make=" Ford ", model=" F-150 ", mileage=85000)

    assert profile.label == "2018 Ford F-150"


def test_load_vehicle_profile_returns_none_for_missing_or_invalid_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    assert load_vehicle_profile() is None

    ensure_local_dirs()
    PROFILE_PATH.write_text("{", encoding="utf-8")
    assert load_vehicle_profile() is None

    PROFILE_PATH.write_text(json.dumps([]), encoding="utf-8")
    assert load_vehicle_profile() is None

    PROFILE_PATH.write_text(
        json.dumps({"year": "2018", "make": "Ford", "model": "F-150"}), encoding="utf-8"
    )
    assert load_vehicle_profile() is None

    PROFILE_PATH.write_text(
        json.dumps({"year": 2018, "make": "Ford", "model": "F-150", "mileage": "bad"}),
        encoding="utf-8",
    )
    assert load_vehicle_profile() == VehicleProfile(2018, "Ford", "F-150", None)


def test_save_and_load_vehicle_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    profile = VehicleProfile(year=2018, make="Ford", model="F-150", mileage=85000)

    save_vehicle_profile(profile)

    assert load_vehicle_profile() == profile


def test_session_log_writes_json_lines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    profile = VehicleProfile(year=2018, make="Ford", model="F-150")

    log = SessionLog("health snapshot", profile)
    log.write("event", {"ok": True})

    rows = [json.loads(line) for line in log.path.read_text(encoding="utf-8").splitlines()]
    assert log.path.parent == SESSIONS_DIR
    assert log.path.name.endswith("-health-snapshot.jsonl")
    assert rows[0]["event"] == "session_started"
    assert rows[0]["payload"]["vehicle"]["model"] == "F-150"
    assert rows[1]["event"] == "event"
    assert rows[1]["payload"] == {"ok": True}
