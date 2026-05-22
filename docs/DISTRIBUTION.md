# Distribution Notes

Last reviewed: 2026-05-22

open-mechanic is installable as an editable Python package today. The repo is not yet packaged for PyPI, Homebrew, Docker, or hosted multi-user deployment.

## Local Install

```bash
pip install -e ".[dev,api]"
```

Use Python 3.11 or newer. The local development checks have been verified with `uv`, which can create an isolated Python 3.11 environment even when the system Python is older.

## Runtime Modes

CLI:

```bash
open-mechanic
```

API:

```bash
uvicorn open_mechanic.api:create_app --factory --reload
```

Website:

```bash
cd website
npm ci
npm run build
```

## Hardware Expectations

- Linux: `/dev/ttyUSB0` is the default fallback. Users may need the `dialout` group.
- macOS: USB serial adapters usually appear as `/dev/cu.usbserial-*`.
- Windows: `COM3` is the default fallback.
- `OBD_PORT` and `OBD_PROTOCOL` can override automatic selection.

For API smoke tests without hardware, the backend returns `connected=false` rather than failing the request.

## Release Readiness Checklist

- Add packaged-data verification for wheels and source distributions.
- Add Docker images only after the API surface is stable enough for dashboard work.
- Decide whether hardware access in containers is an official supported path.
- Add a changelog before tagging the first public release.
- Keep the website clear about current local-first status versus hosted future plans.
