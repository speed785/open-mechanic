# Task 8 implementation report

## Scope completed

- Added documentation assertions before documentation edits and observed all four
  assertions fail for the intended missing/stale contracts.
- Updated `README.md`, `AGENTS.md`, Linux setup, API, AI provider, and future-development
  documentation for the OBDLink EX-only enhanced Stellantis path.
- Documented the 2024 Jeep Wrangler JL 4xe catalog, fixed protocol 6/115200 settings,
  finite CLI/API bounds, structured partial errors, current unsupported cruise DIDs,
  provenance/applicability, read-only allowlists, ephemeral defaults, and per-request AI
  sharing.
- Replaced examples with invented data explicitly labeled synthetic.
- Applied Ruff's mechanical formatting to five previously committed feature/test files
  that the required full formatting gate identified.
- Removed the full-suite SQLAlchemy UTC deprecation and SQLite connection warnings by
  using a non-deprecated naive-UTC default and disposing test engines/connections.

## Verification

- `.venv/bin/pytest tests/test_documentation.py -v --no-cov`: 4 passed.
- `.venv/bin/ruff format --check src tests scripts`: 52 files already formatted.
- `.venv/bin/ruff check src tests scripts`: passed.
- `.venv/bin/mypy src`: passed for 28 source files.
- `.venv/bin/pytest tests/ -v -W error`: 532 passed, 100.00% package line coverage,
  zero warnings.
- `git diff --check`: passed.
- Documentation privacy scan found no DTC-like code, VIN-like identifier, raw diagnostic
  frame, adapter serial value, or live diagnostic value. The only numeric example is
  invented and labeled synthetic.

## Hardware acceptance

Task 8 Step 6 was **NOT RUN**. No serial device was opened and no vehicle or adapter was
accessed. The parked hardware acceptance test remains pending explicit approval.

No network access occurred during this task.

## Review fix: CLI AI disclosure

The first review found one medium documentation mismatch: the docs described an
interactive confirmation prompt that is not implemented. A regression assertion was
added and observed failing before the docs changed. README, contributor guidance, AI
provider guidance, design, and plan now state the actual behavior: every CLI AI
invocation requires `--share-with-ai`; without it, the command lists the categories
that would be shared and exits before adapter or AI access without prompting.

Post-fix verification: Ruff format/check and mypy passed; all 532 tests passed with
100.00% package line coverage under `-W error`. Hardware and network remained unused.
