from __future__ import annotations

from open_mechanic.dashboard import DashboardState, DashboardView
from open_mechanic.tools import main


def test_dashboard_state_defaults_to_disconnected_overview() -> None:
    state = DashboardState()

    assert state.connected is False
    assert state.active_view == DashboardView.OVERVIEW
    assert state.adapter_label == "Disconnected"
    assert state.status_line == "Offline - connect an OBD adapter to stream live vehicle data"


def test_dashboard_state_arrow_navigation_wraps_views() -> None:
    state = DashboardState()

    state.select_previous_view()

    assert state.active_view == DashboardView.LOGS

    state.select_next_view()

    assert state.active_view == DashboardView.OVERVIEW


def test_main_accepts_dashboard_help(capsys) -> None:  # type: ignore[no-untyped-def]
    status = main(["dashboard", "--help"])
    captured = capsys.readouterr()

    assert status == 0
    assert "--interval" in captured.out
    assert "--offline" in captured.out
