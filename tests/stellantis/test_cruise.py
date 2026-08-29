from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from open_mechanic.manufacturers.stellantis.cruise import find_speed_disagreement
from open_mechanic.manufacturers.stellantis.models import LiveValue, ModuleState


def _speed(key: str, value: float, timestamp: datetime, *, fresh: bool = True) -> LiveValue:
    return LiveValue(
        module_key="abs_esc",
        key=key,
        label=key,
        value=value,
        raw_value=None,
        unit="kph",
        timestamp=timestamp,
        fresh=fresh,
        state=ModuleState.RESPONDED,
        applicability="exact_model_year",
    )


def test_flags_one_wheel_speed_that_diverges_at_cruise_speed() -> None:
    timestamp = datetime(2026, 8, 29, tzinfo=UTC)
    values = (
        _speed("wheel_speed_front_left", 80.0, timestamp),
        _speed("wheel_speed_front_right", 80.2, timestamp),
        _speed("wheel_speed_rear_left", 79.9, timestamp),
        _speed("wheel_speed_rear_right", 67.0, timestamp),
    )

    mismatch = find_speed_disagreement(values, threshold_kph=3.0)

    assert mismatch is not None
    assert mismatch.outlier_key == "wheel_speed_rear_right"
    assert mismatch.minimum == 67.0
    assert mismatch.maximum == 80.2
    assert mismatch.delta == pytest.approx(13.2)
    assert mismatch.min == mismatch.minimum
    assert mismatch.max == mismatch.maximum


def test_ignores_stale_or_noncontemporaneous_speed_values() -> None:
    timestamp = datetime(2026, 8, 29, tzinfo=UTC)
    values = (
        _speed("wheel_speed_front_left", 80.0, timestamp),
        _speed("wheel_speed_front_right", 60.0, timestamp + timedelta(seconds=2)),
        _speed("wheel_speed_rear_left", 80.0, timestamp, fresh=False),
    )

    assert find_speed_disagreement(values, threshold_kph=3.0) is None


def test_does_not_flag_speeds_below_the_threshold() -> None:
    timestamp = datetime(2026, 8, 29, tzinfo=UTC)
    values = (
        _speed("wheel_speed_front_left", 80.0, timestamp),
        _speed("wheel_speed_front_right", 82.9, timestamp),
    )

    assert find_speed_disagreement(values, threshold_kph=3.0) is None


def test_requires_two_fresh_kph_readings_and_a_valid_threshold() -> None:
    timestamp = datetime(2026, 8, 29, tzinfo=UTC)
    one_value = (_speed("wheel_speed_front_left", 80.0, timestamp),)
    mph_value = LiveValue(
        module_key="cluster",
        key="vehicle_speed",
        label="vehicle speed",
        value=20.0,
        raw_value=20,
        unit="mph",
        timestamp=timestamp,
        fresh=True,
        state=ModuleState.RESPONDED,
        applicability="exact_model_year",
    )

    assert find_speed_disagreement(one_value, threshold_kph=3.0) is None
    assert find_speed_disagreement((*one_value, mph_value), threshold_kph=3.0) is None
    assert find_speed_disagreement((mph_value, mph_value), threshold_kph=3.0) is None
    with pytest.raises(ValueError, match="must not be negative"):
        find_speed_disagreement(one_value, threshold_kph=-1.0)
