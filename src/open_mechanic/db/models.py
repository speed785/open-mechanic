"""SQLAlchemy 2.0 ORM models for open-mechanic database layer."""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import Engine, ForeignKey, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Base(DeclarativeBase):
    pass


def _utc_now() -> datetime:
    """Return a naive UTC timestamp for the existing SQLite schema."""
    return datetime.now(UTC).replace(tzinfo=None)


class VehicleProfile(Base):
    """Stores vehicle identity and mileage for diagnostic context."""

    __tablename__ = "vehicle_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    year: Mapped[int]
    make: Mapped[str]
    model: Mapped[str]
    mileage: Mapped[int]
    vin: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(default=_utc_now)


class DiagnosticSession(Base):
    """Represents a single OBD-II diagnostic session for a vehicle."""

    __tablename__ = "diagnostic_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicle_profiles.id"))
    started_at: Mapped[datetime] = mapped_column(default=_utc_now)
    ended_at: Mapped[datetime | None]
    port_used: Mapped[str]
    protocol: Mapped[str | None]


class SensorReading(Base):
    """A single sensor value captured during a diagnostic session."""

    __tablename__ = "sensor_readings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("diagnostic_sessions.id"))
    timestamp: Mapped[datetime] = mapped_column(default=_utc_now)
    sensor_name: Mapped[str]
    value: Mapped[str]  # stored as string to accommodate all OBD-II value types
    unit: Mapped[str | None]


class DTCRecord(Base):
    """A Diagnostic Trouble Code recorded during a session."""

    __tablename__ = "dtc_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("diagnostic_sessions.id"))
    timestamp: Mapped[datetime] = mapped_column(default=_utc_now)
    code: Mapped[str]
    description: Mapped[str | None]
    status: Mapped[str]  # "pending" or "confirmed"
    severity: Mapped[str | None]
    category: Mapped[str | None]


class DiagnosisResult(Base):
    """AI-generated diagnostic result for a session, including disclaimer."""

    __tablename__ = "diagnosis_results"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("diagnostic_sessions.id"))
    timestamp: Mapped[datetime] = mapped_column(default=_utc_now)
    severity: Mapped[str]
    summary: Mapped[str]
    raw_json: Mapped[str]  # full Claude JSON response as text
    disclaimer: Mapped[str]


def init_db(db_path: str | None = None) -> Engine:
    """Initialise the SQLite database and create all tables.

    Args:
        db_path: Path to the SQLite file. Defaults to the ``DB_PATH`` env var
                 or ``data/sessions.db`` if unset.

    Returns:
        The configured SQLAlchemy :class:`Engine`.
    """
    load_dotenv()
    resolved_path: str = db_path or os.getenv("DB_PATH") or "data/sessions.db"
    Path(resolved_path).parent.mkdir(parents=True, exist_ok=True)
    engine: Engine = create_engine(f"sqlite:///{resolved_path}", echo=False)
    Base.metadata.create_all(engine)
    return engine


@contextmanager
def get_session(engine: Engine) -> Generator[Session, None, None]:
    """Context manager that yields a SQLAlchemy :class:`Session`.

    Commits on clean exit, rolls back on exception, and always closes.

    Args:
        engine: The SQLAlchemy engine returned by :func:`init_db`.

    Yields:
        An active :class:`Session` bound to *engine*.
    """
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
