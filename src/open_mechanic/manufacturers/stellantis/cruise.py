"""Deterministic, non-diagnostic correlation for cataloged speed readings."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from open_mechanic.manufacturers.stellantis.models import LiveValue, ModuleState

_SAMPLE_INTERVAL_SECONDS = 1.0


@dataclass(frozen=True, slots=True)
class SpeedDisagreement:
    """Evidence that contemporaneous cataloged speed values disagree."""

    minimum: float
    maximum: float
    delta: float
    outlier_key: str
    unit: str

    @property
    def min(self) -> float:
        """Compatibility-friendly short name for the lowest observed value."""
        return self.minimum

    @property
    def max(self) -> float:
        """Compatibility-friendly short name for the highest observed value."""
        return self.maximum


def find_speed_disagreement(
    values: tuple[LiveValue, ...], *, threshold_kph: float
) -> SpeedDisagreement | None:
    """Return speed evidence only for fresh, same-unit, one-interval samples."""
    if threshold_kph < 0:
        raise ValueError("threshold_kph must not be negative")

    usable = tuple(
        value
        for value in values
        if value.fresh
        and value.state is ModuleState.RESPONDED
        and isinstance(value.value, int | float)
        and not isinstance(value.value, bool)
        and value.unit is not None
    )
    if len(usable) < 2:
        return None

    units = {value.unit for value in usable}
    if len(units) != 1:
        return None
    unit = usable[0].unit
    assert unit is not None
    if unit.casefold() != "kph":
        return None

    timestamps = [value.timestamp for value in usable]
    if (max(timestamps) - min(timestamps)).total_seconds() > _SAMPLE_INTERVAL_SECONDS:
        return None

    readings_by_value: list[tuple[LiveValue, float]] = []
    for value in usable:
        assert isinstance(value.value, int | float) and not isinstance(value.value, bool)
        readings_by_value.append((value, float(value.value)))
    readings = [reading for _, reading in readings_by_value]
    minimum = min(readings)
    maximum = max(readings)
    delta = maximum - minimum
    if delta <= threshold_kph:
        return None

    centre = median(readings)
    outlier, _ = max(readings_by_value, key=lambda item: (abs(item[1] - centre), item[0].key))
    return SpeedDisagreement(minimum, maximum, delta, outlier.key, unit)
