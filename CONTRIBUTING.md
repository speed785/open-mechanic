# Contributing to open-mechanic

Thanks for your interest in contributing. open-mechanic is an open-source project and contributions of all kinds are welcome.

---

## Ways to Contribute

You don't need an OBD adapter to contribute. Here's what's open to everyone:

- **Code** — bug fixes, new features, refactors
- **DTC database** — add fault codes to `data/dtc_codes.json` (no hardware needed)
- **Documentation** — setup guides, API docs, hardware notes
- **Bug reports** — detailed reports with reproduction steps
- **Hardware testing** — test on different vehicles, adapters, and operating systems

---

## Development Setup

```bash
git clone https://github.com/speed785/open-mechanic
cd open-mechanic
pip install -e ".[dev]"

cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY
```

Run the test suite:

```bash
pip install -e ".[dev,api]"
pytest
```

Run the linter:

```bash
ruff check src scripts tests
ruff format src scripts tests
```

Run type checking:

```bash
mypy src/
```

Run the local API:

```bash
pip install -e ".[api]"
uvicorn open_mechanic.api:create_app --factory --reload
```

Work on the website:

```bash
cd website
npm ci
npm run build
```

---

## Branch Strategy

- All work happens on feature branches. Never commit directly to `main`.
- Branch naming:
  - `feature/short-description` — new features
  - `fix/short-description` — bug fixes
  - `docs/short-description` — documentation only
  - `dtc/add-p0xxx-codes` — DTC database additions
- Open a PR against `main`. CI must pass before merging.
- This repo uses **squash merges only** — no merge commits, no rebase merges.

---

## Commit Messages

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add Ford extended PID support
fix: handle missing coolant temp sensor gracefully
docs: add macOS FTDI driver setup instructions
dtc: add P0420 catalyst efficiency codes
chore: update ruff to 0.4.0
```

Keep the subject line under 72 characters. Add a body if the change needs more context.

---

## Pull Request Process

1. Open a PR against `main` with a clear description of what changed and why.
2. CI must pass (lint, typecheck, tests).
3. Describe what hardware and OS you tested on, if relevant. If you don't have OBD hardware, say so — that's fine for non-hardware changes.
4. A maintainer will review and squash-merge when ready.

---

## Code Style

- **Formatter**: `ruff format` (enforced by CI)
- **Linter**: `ruff check` (enforced by CI)
- **Type hints**: required on all public functions and methods
- **Docstrings**: required on public functions — keep them short and factual
- **Data structures**: use dataclasses, not plain dicts, for structured data
- **No secrets**: never commit `.env` files or API keys

---

## Hardware Testing

If you have an OBD-II adapter, please note in your PR:

- Adapter model (e.g. OBDLink EX, generic ELM327)
- Vehicle (year, make, model)
- OS (Linux distro, macOS version, Windows version)
- Port used (e.g. `/dev/ttyUSB0`, `COM3`)

This helps us track compatibility and catch platform-specific issues early.

If you don't have hardware, you can still contribute to the DTC database, documentation, and any code that doesn't touch the OBD connection layer.

---

## DTC Database Contributions

The offline DTC reference lives in `data/dtc_codes.json`. Each entry looks like:

```json
{
  "code": "P0420",
  "description": "Catalyst System Efficiency Below Threshold (Bank 1)",
  "severity": "warning",
  "category": "emissions"
}
```

Valid severity values: `info`, `warning`, `critical`

Valid category values: `emissions`, `engine`, `transmission`, `fuel`, `electrical`, `body`, `chassis`, `network`

Use the [DTC Code Addition issue template](.github/ISSUE_TEMPLATE/dtc_addition.yml) to propose new codes, or open a PR directly with additions to `dtc_codes.json`.

---

## Disclaimer Requirement

Any code that produces AI diagnostic output **must** include this disclaimer in the result:

> This diagnosis is informational only and does not constitute professional mechanical advice. Consult a qualified mechanic before making safety-critical repairs.

The `DiagnosticEngine` class in `src/open_mechanic/ai/diagnose.py` is responsible for injecting this. Don't rely on callers to add it. Don't remove it.

---

## Questions

Open an issue or start a discussion. We're happy to help you get oriented.
