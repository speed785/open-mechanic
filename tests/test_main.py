from __future__ import annotations

import pytest

from open_mechanic import __main__


def test_main_exits_with_tools_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(__main__.sys, "argv", ["open-mechanic", "profile"])
    monkeypatch.setattr(__main__, "tools_main", lambda argv: 7)

    with pytest.raises(SystemExit) as exc:
        __main__.main()

    assert exc.value.code == 7
