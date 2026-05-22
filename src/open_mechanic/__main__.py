"""Entry point for open-mechanic CLI."""

from __future__ import annotations

import sys

from open_mechanic.tools import main as tools_main


def main() -> None:
    """Run the open-mechanic command-line interface."""
    raise SystemExit(tools_main(sys.argv[1:]))


if __name__ == "__main__":  # pragma: no cover
    main()
