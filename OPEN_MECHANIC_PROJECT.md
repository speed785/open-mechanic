# open-mechanic — Project Context

> **For AI agents / opencode**: This file summarizes the full context of this project so you can pick up exactly where we left off without needing the original chat history. Read this before doing anything.

---

## What This Project Is

**open-mechanic** is an open-source, AI-powered car diagnostics platform. The core idea:

1. Plug an OBD-II USB adapter into the car's OBD-II port
2. Connect the adapter to a Linux computer via USB
3. Read live sensor data + fault/DTC codes using `python-obd`
4. Feed that data to an AI model (Claude API) with vehicle context
5. Return plain-English diagnosis, severity rating, repair steps, and estimated cost
6. Eventually: web UI, community repair database, optional paid SaaS tier

**Target users**: Car owners who want visibility into their vehicle without paying dealer diagnostic fees.

---

## Hardware Decision

**Adapter chosen: OBDLink EX** (~$35 on Amazon)

- Uses FTDI chip → works on Linux out of the box, shows up as `/dev/ttyUSB0`
- Designed for FORScan (Windows), but the underlying serial protocol works everywhere
- Supports Ford MS-CAN + HS-CAN (deep Ford/Lincoln/Mercury/Mazda access)
- Also works as a standard OBD-II adapter for all 1996+ vehicles
- 20x faster throughput than generic toggle-switch adapters
- More reliable than cheap ELM327 clones

**Generic ELM327 USB adapters** also work for standard OBD-II data if you don't need Ford extended PIDs.

---

## Key Technical Facts

### Linux Connection
```bash
# After plugging in OBDLink EX, confirm it's detected:
dmesg | grep ttyUSB
# Should show: FTDI USB Serial Device converter now attached to ttyUSB0

# Add your user to the dialout group if needed:
sudo usermod -a -G dialout $USER
```

### Python OBD Library
```python
pip install obd

import obd

# Connect (auto-detects port and baud rate)
connection = obd.OBD()  # or obd.OBD("/dev/ttyUSB0")

# Read a specific sensor
response = connection.query(obd.commands.RPM)
print(response.value)  # e.g. 750 RPM

# Read all supported commands
for cmd in connection.supportedCommands:
    response = connection.query(cmd)
    print(cmd.name, response.value)

# Read DTC fault codes
dtcs = connection.query(obd.commands.GET_DTC)
print(dtcs.value)  # [('P0420', 'Catalyst System Efficiency Below Threshold')]

# Clear DTC codes (use carefully)
connection.query(obd.commands.CLEAR_DTC)
```

### Manufacturer Lock-In Reality
- **Standard OBD-II** (1996+ all cars): DTC codes, RPM, coolant temp, O2 sensors, fuel trim, speed, emissions readiness
- **Ford extended PIDs**: Need OBDLink EX + community-documented PIDs (ForScan has reverse-engineered these)
- **Other manufacturers**: VW/Audi → VCDS documented PIDs; BMW → INPA/E-Sys; GM → some open PIDs
- **Start with standard OBD-II** — covers 80% of real-world diagnostic needs on day one

---

## Competitive Landscape

| Tool        | Open Source | AI Diagnostics | Repair Guides | Linux | Self-Hostable |
|-------------|-------------|----------------|---------------|-------|---------------|
| Torque Pro   | ❌          | ❌             | ❌            | ❌    | ❌            |
| OBD Fusion   | ❌          | ❌             | Partial       | ❌    | ❌            |
| Car Scanner  | ❌          | ❌             | ❌            | ❌    | ❌            |
| **open-mechanic** | ✅       | ✅             | ✅            | ✅    | ✅            |

---

## Project Phases

### Phase 1 — Foundation (Week 1–2)
**Goal**: Prove the hardware→software connection works end-to-end

- [ ] Buy OBDLink EX, plug into car via Linux, confirm `/dev/ttyUSB0` appears
- [ ] Install `python-obd`, write a script that reads live sensor data
- [ ] Pull and decode DTC fault codes from the car
- [ ] Log sensor data to SQLite with timestamps
- [ ] Create the GitHub repo (MIT license, README, basic structure)

**Deliverables**:
- `src/connection.py` — OBD connection management
- `src/reader.py` — live data polling
- `src/dtc.py` — DTC code reading + decoding
- `data/sessions.db` — SQLite schema

### Phase 2 — AI Diagnostics Layer (Week 3–4)
**Goal**: Turn raw DTC codes into useful, plain-English guidance

- [ ] Set up Claude API integration
- [ ] Build prompt template that includes: make/model/year/mileage + DTC codes + live sensor snapshot
- [ ] Return structured JSON: `{ severity, diagnosis, likely_cause, repair_steps[], estimated_cost, diy_feasible }`
- [ ] Add severity classification: info / warning / critical / don't-drive
- [ ] Build DTC local cache (avoid API calls for known codes)

**Prompt template skeleton**:
```python
DIAGNOSTIC_PROMPT = """
You are an expert automotive technician. Analyze the following vehicle data and provide a diagnosis.

Vehicle: {year} {make} {model} ({mileage} miles)
DTC Fault Codes: {dtc_codes}
Live Sensor Data: {sensor_snapshot}

Respond ONLY with valid JSON matching this schema:
{
  "severity": "info|warning|critical|do_not_drive",
  "summary": "one sentence plain-English summary",
  "likely_causes": ["cause 1", "cause 2"],
  "repair_steps": ["step 1", "step 2", "step 3"],
  "estimated_cost_usd": {"low": 0, "high": 0},
  "diy_feasible": true|false,
  "diy_difficulty": "easy|moderate|hard|professional_only",
  "urgency": "immediate|soon|next_service|monitor"
}
"""
```

### Phase 3 — Interface & Repair Guides (Month 2)
**Goal**: Make it usable by non-technical car owners

- [ ] Rich CLI output with color-coded severity (using `rich` library)
- [ ] FastAPI backend with REST endpoints
- [ ] React frontend: dashboard, DTC history, repair guide viewer
- [ ] Maintenance timeline tracker (oil, brakes, tires, fluids per vehicle profile)
- [ ] PDF/markdown repair guide export

**API endpoints**:
```
GET  /api/vehicle          — get/set vehicle profile
GET  /api/live             — live sensor data stream (SSE)
GET  /api/dtc              — current fault codes
POST /api/diagnose         — trigger AI diagnosis
GET  /api/history          — past sessions
GET  /api/guides/{dtc}     — repair guide for a specific code
```

### Phase 4 — Community & Scale (Month 3–6)
**Goal**: Build the community layer and explore monetization

- [ ] Public GitHub release with CONTRIBUTING.md
- [ ] Community DTC database (crowdsourced repair success stories)
- [ ] Manufacturer-specific modules (Ford extended PIDs first, then VW, BMW)
- [ ] Optional SaaS hosted tier ($9.99/mo)
- [ ] Hardware bundle (branded OBDLink EX + pre-configured software)

---

## Tech Stack

| Layer       | Technology                              |
|-------------|----------------------------------------|
| Hardware    | OBDLink EX USB adapter                 |
| OBD Reading | `python-obd`, `pyserial`               |
| AI/LLM      | Claude API (claude-sonnet model)       |
| Backend     | Python + FastAPI                       |
| Frontend    | React + TailwindCSS                    |
| Database    | SQLite (dev) → PostgreSQL (prod)       |
| CLI         | Python + `rich` for pretty output      |
| Hosting     | Self-hostable Docker or GitHub Pages   |
| CI/CD       | GitHub Actions                         |

---

## Repo Structure (Proposed)

```
open-mechanic/
├── README.md
├── CONTRIBUTING.md
├── LICENSE (MIT)
├── pyproject.toml
├── docker-compose.yml
│
├── src/
│   ├── open-mechanic/
│   │   ├── __init__.py
│   │   ├── connection.py      # OBD-II connection management
│   │   ├── reader.py          # Live data polling
│   │   ├── dtc.py             # DTC code reading + decoding
│   │   ├── ai/
│   │   │   ├── __init__.py
│   │   │   ├── diagnose.py    # Claude API integration
│   │   │   └── prompts.py     # Prompt templates
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   └── routes.py      # FastAPI routes
│   │   └── db/
│   │       ├── __init__.py
│   │       └── models.py      # SQLAlchemy models
│
├── frontend/                  # React app (Phase 3)
│   ├── src/
│   └── package.json
│
├── scripts/
│   ├── test_connection.py     # Quick adapter test
│   └── seed_dtc_db.py        # Populate local DTC database
│
├── data/
│   └── dtc_codes.json        # Offline DTC reference database
│
└── docs/
    ├── HARDWARE.md            # Adapter setup guide
    ├── LINUX_SETUP.md         # Linux driver notes
    └── API.md                 # REST API reference
```

---

## Business Model Summary

### Open Core (always free)
- OBD-II data reading + logging
- Standard DTC code lookup (offline)
- Basic CLI diagnostics
- Self-hosted deployment

### Hardware Bundle (~$60–80 retail)
- Pre-configured OBDLink EX adapter
- open-mechanic software pre-installed
- 1-year AI diagnostics subscription included

### SaaS / Cloud Tier ($9.99/mo or $79/yr)
- Unlimited AI diagnostics
- Full repair guide database
- Maintenance reminders + alerts
- Community repair insights
- Multi-vehicle household plan

---

## Important Caveats

- **Liability**: All diagnostic output is informational only, not professional mechanical advice. Add clear disclaimers to the UI and README.
- **EV support**: Hybrid/electric vehicles don't expose the same OBD-II data. Treat as a separate future module.
- **Ford extended PIDs**: OBDLink EX can access Ford-specific modules, but this requires documented community PIDs — FORScan's forum has a wealth of this data.
- **DO NOT** let users clear DTC codes without understanding the implications. Gate this behind a confirmation step.

---

## How to Resume This Project in opencode

If you're an AI agent reading this: the human wants to build this project from scratch. Start by:

1. Creating the GitHub repo structure outlined above
2. Writing `src/open-mechanic/connection.py` and `src/open-mechanic/reader.py` first
3. Building a simple `scripts/test_connection.py` the user can run immediately with their OBDLink EX
4. Then moving to the AI diagnostics layer in `src/open-mechanic/ai/diagnose.py`

The human is technically proficient (works with AI agent orchestration, GitHub workflows, Python). Assume developer-level knowledge. Skip basic explanations.

---

## Chat Origin

This project context was generated from a planning conversation with Claude (claude.ai) on March 16, 2026. The conversation covered: project viability, OBD-II adapter selection (OBDLink EX chosen), Linux compatibility confirmation, competitive analysis, business model options, and phase planning.
