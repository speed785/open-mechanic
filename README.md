# open-mechanic

Open-source, local-first vehicle diagnostics for Linux, macOS, and Windows. Normal
scans render data in the current process. **No diagnostic history is saved by default.**
Nothing is sent to an AI provider without explicit per-request authorization.

## Hardware and supported vehicle

[OBDLink EX USB](https://www.obdlink.com/products/obdlink-ex/) is the **only required diagnostic hardware**
for the enhanced Stellantis path. Generic ELM327 adapters may
work with generic emissions OBD-II commands but are not supported for this path.

The first enhanced catalog targets the **2024 Jeep Wrangler JL 4xe**, fixed at 115200
baud and ISO 15765-4 CAN 11-bit/500 kbit (protocol 6). It is read-only and does not
require or claim support for AutoAuth or an SGW bypass cable. Gateway denials are
reported; the tool never unlocks or bypasses the gateway.

Catalog coverage is conservative:

- Public exact-model-year evidence supports powertrain, hybrid-control, and
  transmission addresses.
- Other addresses are visibly labeled `community_unverified`.
- No manufacturer-specific cruise DIDs have acceptable public verification yet. The
  cruise view reports unsupported fields instead of guessing identifiers or values.

## Install

Python 3.11 or newer is required.

```bash
git clone https://github.com/speed785/open-mechanic
cd open-mechanic
pip install -e ".[dev,api]"
```

Linux users should complete the non-root serial permission steps in
[docs/SETUP_LINUX.md](docs/SETUP_LINUX.md).

## Parked read-only scan

Park safely, set the parking brake, and put the ignition in RUN with the engine off.

```bash
open-mechanic stellantis-scan \
  --vehicle wrangler_jl_4xe_2024 \
  --port /dev/ttyUSB0 --protocol 6 --baudrate 115200
```

Timeouts, negative replies, gateway restrictions, unsupported modules, and unverified
applicability remain structured partial errors. One unavailable module does not erase
other module results.

## Bounded cruise observation

```bash
open-mechanic stellantis-live \
  --vehicle wrangler_jl_4xe_2024 --group cruise \
  --samples 3 --interval 1 \
  --port /dev/ttyUSB0 --protocol 6 --baudrate 115200
```

`--samples` is 1–60; `--interval` and `--timeout` are greater than zero and at most 10
seconds. Do the parked scan first. During any later moving test, a passenger or qualified technician
must operate the computer; the driver must never operate it.

## Safety and privacy boundary

The enhanced transport accepts only OBD-II services `01`, `02`, `03`, `07`, `09`, and
`0A`; UDS ReadDTCInformation (`0x19`); cataloged ReadDataByIdentifier (`0x22`); and
bounded TesterPresent (`0x3E`). It exposes no arbitrary command console, address sweep,
security access, actuator command, coding, flashing, DTC clear, or gateway bypass.
Disallowed requests are rejected before the serial port opens.

Local scans create no profiles, JSONL logs, database rows, result caches, telemetry, or
network calls. AI diagnosis is separate and optional. Every CLI AI invocation requires `--share-with-ai`.
Without it, the command displays the categories that would be shared
and exits before adapter or AI access. Consent lasts for one invocation, and AI
responses are not cached.

## Local API and AI

```bash
uvicorn open_mechanic.api:create_app --factory --reload
```

Enhanced endpoints are:

```text
GET /api/stellantis/wrangler_jl_4xe_2024/dtc
GET /api/stellantis/wrangler_jl_4xe_2024/live/cruise?samples=3&interval=1
```

See [docs/API.md](docs/API.md). AI is unnecessary for local scanning. One CLI AI
request can be authorized with:

```bash
python scripts/diagnose.py --vehicle "Synthetic Example Vehicle" \
  --mileage 10000 --protocol 6 --share-with-ai
```

That vehicle is an invented synthetic example, not observed data. See
[docs/AI_PROVIDERS.md](docs/AI_PROVIDERS.md) before sharing anything externally.

## Development

```bash
ruff format --check src tests scripts
ruff check src tests scripts
mypy src
pytest tests/ -v
```

Never add a user's VIN, adapter serial number, observed DTCs, raw frames, or live values
to fixtures, docs, issues, commits, or pull requests. Examples must be invented and
labeled synthetic. Contributions are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md).

MIT licensed. Diagnostic output is informational, not professional mechanical advice.
Consult a qualified mechanic before safety-critical repairs.
