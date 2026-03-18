# open-mechanic

> Open-source AI-powered car diagnostics. Plug in an OBD-II USB adapter, read live sensor data and fault codes, get plain-English diagnosis and step-by-step repair guides — on Linux, macOS, or Windows.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Phase 1+2: Complete](https://img.shields.io/badge/phase%201%2B2-complete-brightgreen.svg)]()

---

## What It Does

1. Plug an OBD-II USB adapter into your car's OBD-II port
2. Connect the adapter to your computer via USB (Linux, macOS, or Windows)
3. `open-mechanic` reads live sensor data + fault codes using `python-obd`
4. Feeds that data to an AI model of your choice with your vehicle's context
5. Returns plain-English diagnosis, severity rating, repair steps, and estimated cost

**Target users**: Car owners who want real visibility into their vehicle without paying dealer diagnostic fees.

---

## Why open-mechanic?

| Tool | Open Source | AI Diagnostics | Repair Guides | Linux | Self-Hostable |
|------|-------------|----------------|---------------|-------|---------------|
| Torque Pro | ❌ | ❌ | ❌ | ❌ | ❌ |
| OBD Fusion | ❌ | ❌ | Partial | ❌ | ❌ |
| Car Scanner | ❌ | ❌ | ❌ | ❌ | ❌ |
| **open-mechanic** | ✅ | ✅ | ✅ | ✅ | ✅ |

---

## Hardware

**Recommended: [OBDLink EX USB](https://www.obdlink.com/products/obdlink-ex/)** (~$35)

- FTDI chip → works on Linux out of the box (`/dev/ttyUSB0`), macOS (`/dev/cu.usbserial-*`), and Windows (`COM3`) — see [platform setup docs](docs/)
- Supports Ford MS-CAN + HS-CAN for deep Ford/Lincoln/Mercury/Mazda access
- 20× faster throughput than generic ELM327 clones
- Works as standard OBD-II adapter for **all 1996+ vehicles**

Generic ELM327 USB adapters also work for standard OBD-II data.

```bash
# Confirm adapter is detected after plugging in:
dmesg | grep ttyUSB
# → FTDI USB Serial Device converter now attached to ttyUSB0

# Add yourself to the dialout group if needed:
sudo usermod -a -G dialout $USER
```

---

## Quick Start

```bash
# Clone and install
git clone https://github.com/yourusername/open-mechanic
cd open-mechanic
pip install -e ".[dev]"

# Set your AI API key
cp .env.example .env
# Edit .env and add: ANTHROPIC_API_KEY=your_key_here

# Test your OBD adapter (engine running, adapter plugged into OBD-II port)
python scripts/test_connection.py
# Tip: if connection hangs, your car likely uses CAN — add OBD_PROTOCOL=6 to .env

# AI diagnosis (Phase 3 CLI — coming soon)
# For now, use the Python API directly — see docs/
```

---

## AI Diagnostic Output

```json
{
  "severity": "warning",
  "summary": "Catalytic converter efficiency below threshold on bank 1",
  "likely_causes": [
    "Aged catalytic converter",
    "Rich fuel mixture causing catalyst damage",
    "Upstream O2 sensor fault skewing readings"
  ],
  "repair_steps": [
    "Inspect upstream and downstream O2 sensors for correct waveform",
    "Check for exhaust leaks before the catalytic converter",
    "Test catalytic converter efficiency with a scan tool",
    "Replace catalytic converter if efficiency confirmed below spec"
  ],
  "estimated_cost_usd": { "low": 150, "high": 1200 },
  "diy_feasible": false,
  "diy_difficulty": "hard",
  "urgency": "soon"
}
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Hardware | OBDLink EX USB adapter |
| OBD Reading | `python-obd`, `pyserial` |
| AI/LLM | Pluggable AI backend (Claude, OpenAI, and more) |
| Backend | Python + FastAPI |
| Frontend | React + TailwindCSS *(Phase 3)* |
| Database | SQLite → PostgreSQL |
| CLI | Python + `rich` |
| Hosting | Self-hostable Docker |
| CI/CD | GitHub Actions |

---

## Roadmap

### ✅ Phase 1 — Foundation *(Week 1–2)*
OBD-II connection management · Live sensor polling · DTC fault code reading + decoding · SQLite session logging

### ✅ Phase 2 — AI Diagnostics *(Week 3–4)*
AI API integration · Structured JSON diagnostic output · Local DTC code cache

### 📋 Phase 3 — Interface *(Month 2)*
Rich CLI with color-coded severity · FastAPI REST backend · React dashboard + repair guide viewer · Maintenance timeline tracker

### 🌐 Phase 4 — Community *(Month 3–6)*
Public open-source release · Community DTC database · Manufacturer-specific modules (Ford, VW, BMW) · Optional SaaS hosted tier

---

## API Endpoints *(Phase 3)*

```
GET  /api/vehicle          — get/set vehicle profile
GET  /api/live             — live sensor data stream (SSE)
GET  /api/dtc              — current fault codes
POST /api/diagnose         — trigger AI diagnosis
GET  /api/history          — past diagnostic sessions
GET  /api/guides/{dtc}     — repair guide for a specific DTC code
```

---

## OBD-II Coverage

**Standard OBD-II** (all 1996+ vehicles): DTC codes, RPM, coolant temp, O2 sensors, fuel trim, vehicle speed, emissions readiness monitors, MAF, throttle position, battery voltage.

**Ford extended PIDs** *(future)*: Requires OBDLink EX + community-documented PIDs from FORScan forums. Covers transmission temp, TPMS, ABS, body modules.

**EV/Hybrid note**: Hybrid and electric vehicles don't expose the same OBD-II data. Treated as a separate future module.

---

## Contributing

Contributions welcome — bug reports, DTC database additions, manufacturer PID documentation, and code all appreciated. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## License

MIT — see [LICENSE](LICENSE)

---

## ⚠️ Disclaimer

All diagnostic output from open-mechanic is **informational only** and does not constitute professional mechanical advice. Always consult a qualified mechanic before making safety-critical repairs. The authors accept no liability for vehicle damage or personal injury resulting from use of this software.
