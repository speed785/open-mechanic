from __future__ import annotations

from pathlib import Path

import pytest

from open_mechanic.db.models import VehicleProfile, get_session, init_db


def test_init_db_creates_parent_directory_and_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "sessions.db"

    engine = init_db(str(db_path))

    assert db_path.exists()
    assert sorted(engine.dialect.get_table_names(engine.connect())) == sorted(
        [
            "diagnostic_sessions",
            "diagnosis_results",
            "dtc_records",
            "sensor_readings",
            "vehicle_profiles",
        ]
    )


def test_get_session_commits_on_success(tmp_path: Path) -> None:
    engine = init_db(str(tmp_path / "sessions.db"))

    with get_session(engine) as session:
        session.add(VehicleProfile(year=2018, make="Ford", model="F-150", mileage=85000, vin=None))

    with get_session(engine) as session:
        assert session.query(VehicleProfile).count() == 1


def test_get_session_rolls_back_on_error(tmp_path: Path) -> None:
    engine = init_db(str(tmp_path / "sessions.db"))

    with pytest.raises(RuntimeError), get_session(engine) as session:
        session.add(VehicleProfile(year=2018, make="Ford", model="F-150", mileage=85000, vin=None))
        raise RuntimeError("boom")

    with get_session(engine) as session:
        assert session.query(VehicleProfile).count() == 0
