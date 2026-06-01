from __future__ import annotations

from datetime import datetime

from open_mechanic.ai.diagnose import DISCLAIMER
from open_mechanic.ai.providers import DiagnosticProvider


class FakeProvider(DiagnosticProvider):
    name = "fake"

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        return """
        {
          "severity": "warning",
          "summary": "The vehicle needs follow-up inspection.",
          "likely_causes": ["Loose gas cap"],
          "repair_steps": ["Inspect cap seal"],
          "estimated_cost_usd": {"low": 20, "high": 80},
          "diy_feasible": true,
          "diy_difficulty": "easy",
          "urgency": "soon",
          "disclaimer": "provider text"
        }
        """


def test_web_schemas_importable() -> None:
    from open_mechanic.web.schemas import SensorResponse, StatusResponse

    status = StatusResponse(
        version="0.1.0",
        connected=False,
        port=None,
        protocol=None,
        provider_name="not configured",
        provider_configured=False,
        vehicle_profile=None,
        latest_poll_at=None,
    )
    sensors = SensorResponse(sensors=[])

    assert status.connected is False
    assert sensors.sensors == []


def test_dashboard_service_starts_disconnected_offline() -> None:
    from open_mechanic.web.service import DashboardService

    service = DashboardService(offline=True)

    status = service.get_status()
    assert status.connected is False
    assert service.get_sensors().sensors == []
    assert service.get_dtcs().dtcs == []


def test_web_api_status_and_no_clear_route() -> None:
    from fastapi.testclient import TestClient

    from open_mechanic.web.app import create_app

    client = TestClient(create_app(offline=True))

    response = client.get("/api/status")
    assert response.status_code == 200
    assert response.json()["connected"] is False

    assert client.post("/api/clear-dtcs").status_code == 404


def test_static_file_helper_rejects_paths_outside_static_dir() -> None:
    from open_mechanic.web.app import STATIC_DIR, _safe_static_file

    assert _safe_static_file("index.html") == (STATIC_DIR / "index.html").resolve()
    assert _safe_static_file("../pyproject.toml") is None


def test_web_static_route_does_not_serve_path_traversal() -> None:
    from fastapi.testclient import TestClient

    from open_mechanic.web.app import create_app

    client = TestClient(create_app(offline=True))

    response = client.get("/%2E%2E/pyproject.toml")

    assert response.status_code in {200, 404}
    assert b"[project]" not in response.content


def test_web_command_help_is_registered(capsys) -> None:  # type: ignore[no-untyped-def]
    from open_mechanic.tools import main

    status = main(["web", "--help"])

    captured = capsys.readouterr()
    assert status == 0
    assert "--host" in captured.out
    assert "--offline" in captured.out
    assert "--no-gui" in captured.out


def test_dashboard_status_distinguishes_offline_from_disconnected() -> None:
    from open_mechanic.web.service import DashboardService

    offline_service = DashboardService(offline=True, provider=FakeProvider())
    offline_status = offline_service.get_status()

    disconnected_service = DashboardService(offline=False, provider=FakeProvider())
    disconnected_status = disconnected_service.get_status()

    assert offline_status.offline is True
    assert offline_status.connected is False
    assert offline_status.adapter_state == "offline"
    assert offline_status.adapter_message is None
    assert disconnected_status.offline is False
    assert disconnected_status.connected is False
    assert disconnected_status.adapter_state == "disconnected"


def test_schedule_web_gui_open_starts_delayed_timer() -> None:
    from rich.console import Console

    from open_mechanic.tools import _schedule_web_gui_open

    calls: list[tuple[float, object, tuple[object, ...]]] = []

    class FakeTimer:
        daemon = False

        def __init__(self, delay: float, callback: object, args: tuple[object, ...]) -> None:
            calls.append((delay, callback, args))

        def start(self) -> None:
            calls.append((-1, "started", ()))

    console = Console()

    _schedule_web_gui_open("http://127.0.0.1:8000", console, delay=0.25, timer_factory=FakeTimer)

    assert calls[0][0] == 0.25
    assert calls[0][2] == ("http://127.0.0.1:8000", console)
    assert calls[1] == (-1, "started", ())


def test_loopback_host_detection_for_web_warning() -> None:
    from open_mechanic.tools import _is_loopback_host

    assert _is_loopback_host("127.0.0.1") is True
    assert _is_loopback_host("localhost") is True
    assert _is_loopback_host("::1") is True
    assert _is_loopback_host("0.0.0.0") is False
    assert _is_loopback_host("192.168.1.10") is False


def test_should_open_browser_respects_no_gui() -> None:
    from argparse import Namespace

    from open_mechanic.tools import _should_open_web_gui

    assert _should_open_web_gui(Namespace(no_gui=True, reload=False)) is False
    assert _should_open_web_gui(Namespace(no_gui=False, reload=False)) is True
    assert _should_open_web_gui(Namespace(no_gui=False, reload=True)) is False


def test_dashboard_service_diagnosis_preserves_disclaimer() -> None:
    from open_mechanic.web.schemas import DiagnosisRequest, VehicleProfileRequest
    from open_mechanic.web.service import DashboardService

    service = DashboardService(offline=True, provider=FakeProvider())

    result = service.diagnose(
        DiagnosisRequest(
            vehicle=VehicleProfileRequest(
                year=2018,
                make="Ford",
                model="F-150",
                mileage=85000,
                vin=None,
            ),
            generated_at=datetime.now(),
        )
    )

    assert result.provider == "fake"
    assert result.disclaimer == DISCLAIMER
