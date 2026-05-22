# Future Development Plan

Last reviewed: 2026-05-22

This document captures the current repository status and the most useful next improvements for open-mechanic. It is intended as a working plan for future development, not a release promise.

## Current Status

- Core package: Python package under `src/open_mechanic` with OBD connection handling, live sensor polling, DTC reading/decoding, local session logging, SQLite models, Anthropic-backed AI diagnostics, and a read-only FastAPI backend.
- CLI: `open-mechanic` entry point and read-only tools menu exist. `scripts/diagnose.py` also provides a direct diagnosis script.
- Website: Vite/TypeScript static site under `website/`, deployed through GitHub Pages workflows.
- Docs: Platform setup docs exist for Linux, macOS, and Windows.
- Tests: Python package line coverage is at 100% across connection, DTC, reader, AI diagnostics, local storage, DB models, CLI helper paths, and API paths.

## Verified Checks

These checks were run locally with `uv` using Python 3.11:

- `uv run --extra dev --extra api pytest`: pass, 134 tests, 100% line coverage.
- `uv run --extra dev --extra api ruff check src scripts tests`: pass.
- `uv run --extra dev --extra api mypy src`: pass.
- `cd website && npm ci && npm run build`: pass.

Environment note: the system `python3` is Apple Python 3.9.6, below the project requirement of Python 3.11+. `uv` successfully created a local `.venv` for validation.

## Highest Priority Improvements

1. Fix AI cache correctness. DONE

   `DiagnosticEngine` now keys cache entries by vehicle, DTC codes, and a normalized sensor snapshot so changed live data triggers a fresh diagnosis.

2. Package the DTC database reliably. DONE

   `DTCReader` now falls back to package resources via `importlib.resources`, and the DTC database is mirrored under `src/open_mechanic/data/`.

3. Harden AI response parsing. DONE

   The diagnostic path now validates that model JSON is an object and returns a disclaimer-bearing fallback for malformed output.

4. Add mocked OBD coverage. DONE

   Mocked coverage now covers unsupported PIDs, query exceptions, live sensor snapshots, `DTCReader.get_dtcs`, and the `clear_dtcs(confirmed=True)` path.

5. Fix `tools.py` type errors. DONE

   `tools.py` now typechecks cleanly.

6. Align docs with implementation. DONE

   README and docs now split available API functionality from planned dashboard, history, guide, distribution, and provider work.

7. Implement Phase 3 read-only FastAPI backend. DONE

   The API now exposes health, vehicle profile, live sensor, DTC, snapshot, and diagnosis endpoints through a dependency-injected service layer with 100% covered route and service tests.

## Near-Term Backlog

- Replace placeholder clone URLs with `https://github.com/speed785/open-mechanic`. DONE
- Make CI typecheck install the package with declared dependencies, for example `pip install -e ".[dev,api]"`, instead of installing only `mypy anthropic`. DONE
- Decide whether mypy should be strict now. DONE
- Implement or remove `scripts/diagnose.py --no-cache`; it is parsed but does not currently affect `DiagnosticEngine`. DONE
- Add tests around `DiagnosticEngine` with mocked Anthropic responses: valid JSON, fenced JSON, non-object JSON, missing fields, bad field types, API errors, cache behavior, and disclaimer injection. DONE
- Verify whether `SensorPoller` should use `getattr(obd.commands, name, None)` instead of membership checks against `obd.commands`. DONE
- Add a website development note covering `cd website`, `npm ci`, `npm run build`, and Pages deployment. DONE
- Add Open Graph/Twitter metadata to the website and verify asset paths under the GitHub Pages `/open-mechanic/` base path. DONE
- Add API contract docs for dashboard work. DONE
- Clarify AI provider strategy. DONE
- Add distribution and release readiness notes. DONE

## Suggested Milestones

### Milestone 1: Trustworthy CLI Foundation

- Fix cache key and AI parsing fallback behavior.
- Package DTC data correctly.
- Resolve mypy errors.
- Add mocked OBD and diagnostic engine tests.
- Update README quick start and current-capability language.

### Milestone 2: Developer Experience and CI

- Align CI with local commands.
- Add coverage reporting for core modules.
- Document Python 3.11+ setup with `uv` and standard `pip` paths.
- Add a short website development section.

### Milestone 3: Interface Work

- FastAPI read-only backend foundation is complete.
- Build the dashboard against `docs/API.md` instead of static marketing copy.
- Add history and guide endpoints after persistence and content licensing are finalized.

### Milestone 4: Release Readiness

- Clarify the AI provider story: Anthropic-only, pluggable providers, or local models. DONE in `docs/AI_PROVIDERS.md`.
- Add distribution notes for package install, hardware permissions, and platform-specific adapter setup. DONE in `docs/DISTRIBUTION.md`.
- Audit all safety language around DTC clearing and AI diagnostic disclaimers.
- Add issue templates or labels for DTC database additions, hardware reports, and platform setup bugs.
