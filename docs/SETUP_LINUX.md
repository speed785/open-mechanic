# Setup Guide — Linux

This guide covers setting up open-mechanic on Linux with an OBDLink EX USB adapter.

---

## Prerequisites

- Python 3.11 or newer
- pip (usually bundled with Python)
- An OBDLink EX USB adapter (or any ELM327-compatible USB OBD-II adapter)

Check your Python version:

```bash
python3 --version
# Should show Python 3.11.x or newer
```

---

## Install

Clone the repo and install in editable mode with dev dependencies:

```bash
git clone https://github.com/speed785/open-mechanic
cd open-mechanic
pip install -e ".[dev]"
```

---

## OBDLink EX Detection

The OBDLink EX uses an FTDI chip, which Linux supports natively — no extra drivers needed.

Plug in the adapter, then check it was detected:

```bash
dmesg | grep ttyUSB
```

> **Note**: On some systems `dmesg` requires sudo. If you get "Operation not permitted", use `ls -la /dev/ttyUSB0` instead to confirm the adapter is detected.

Expected output:

```
usb 1-1.2: FTDI USB Serial Device converter now attached to ttyUSB0
```

Verify the device node exists:

```bash
ls -la /dev/ttyUSB0
# crw-rw---- 1 root dialout 188, 0 ...
```

---

## Serial Port Permissions

By default, `/dev/ttyUSB0` is owned by the `dialout` group. Add your user to that group:

```bash
sudo usermod -a -G dialout $USER
```

**You must log out and log back in** for the group change to take effect.

**Shortcut** — to apply immediately in the current terminal without logging out:

```bash
newgrp dialout
```

Then run the test script in that same terminal window.

Verify you're in the group after re-login:

```bash
groups | grep dialout
```

---

## Environment Setup

Copy the example env file and add your Claude API key:

```bash
cp .env.example .env
```

Edit `.env`:

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...your-key-here...

# OBD adapter settings
OBD_PORT=                  # leave blank to auto-detect /dev/ttyUSB0
OBD_BAUDRATE=              # leave blank (auto-detected as 115200 for OBDLink EX)
OBD_PROTOCOL=6             # 6 = ISO 15765-4 CAN 11/500 (most 2008+ cars)
                           # Remove or leave blank to auto-detect (slower, ~30s)
```

> **Why `OBD_PROTOCOL=6`?** Auto-detection tries every OBD protocol sequentially and can take 30+ seconds or time out entirely. Protocol 6 (ISO 15765-4 CAN 11/500) covers the vast majority of cars made after 2008. If your car is older or doesn't respond, remove this line to fall back to auto-detection.

Get a Claude API key at: https://console.anthropic.com/

---

## Test the OBD Connection

With your adapter plugged into the car's OBD-II port and the engine running:

```bash
# With engine running and adapter plugged into OBD-II port:
python scripts/test_connection.py
```

Expected output:

```
╭─────────────────────────────────────────────────╮
│  open-mechanic — OBD-II Adapter Test            │
│  Version 0.1.0  •  2026-03-18 19:16:35         │
╰─────────────────────────────────────────────────╯

✓ Connected  ISO 15765-4 (CAN 11/500)  on /dev/ttyUSB0

Adapter supports 110 commands

┌─────────────────────────┬────────┬────────────────────────┬───────────┐
│ Sensor                  │  Value │ Unit                   │ Supported │
├─────────────────────────┼────────┼────────────────────────┼───────────┤
│ Engine RPM              │ 754.75 │ revolutions_per_minute │     ✓     │
│ Vehicle Speed           │   0.00 │ kilometer_per_hour     │     ✓     │
│ Coolant Temp            │  98.00 │ degree_Celsius         │     ✓     │
│ Throttle Position       │   9.80 │ percent                │     ✓     │
│ Engine Load             │  26.67 │ percent                │     ✓     │
│ Control Module Voltage  │  14.83 │ volt                   │     ✓     │
└─────────────────────────┴────────┴────────────────────────┴───────────┘

✓ No fault codes

Completed in 2.55s
```

---

## Troubleshooting

### Port not found (`/dev/ttyUSB0` doesn't exist)

1. Check the adapter is physically plugged in
2. Run `dmesg | tail -20` immediately after plugging in — look for FTDI messages
3. Try `ls /dev/ttyUSB*` — the port number may be `ttyUSB1` or higher if other USB serial devices are connected
4. Set the correct port in `.env`: `OBD_PORT=/dev/ttyUSB1`

### Permission denied

```
serial.serialutil.SerialException: [Errno 13] Permission denied: '/dev/ttyUSB0'
```

You haven't been added to the `dialout` group yet, or haven't re-logged in. Run:

```bash
sudo usermod -a -G dialout $USER
# Then log out and back in
```

Alternatively, for a quick test only (not recommended permanently):

```bash
sudo chmod a+rw /dev/ttyUSB0
```

### No data / adapter connects but no PIDs respond

- Make sure the car's ignition is in the "on" position (not just accessory)
- Some PIDs are not supported by all vehicles — this is normal
- Try a different OBD-II command: `python -c "import obd; c = obd.OBD(); print(c.query(obd.commands.ELM_VERSION))"`

### Multiple USB serial devices

If you have other USB serial devices (Arduino, GPS, etc.), the OBDLink may appear as `ttyUSB1` or `ttyUSB2`. Set `OBD_PORT=/dev/ttyUSBX` in `.env` to pin it.

### Connection hangs or times out (never shows "Connected")

The most common cause is OBD protocol auto-detection timing out. Fix:

1. Add `OBD_PROTOCOL=6` to your `.env` file (covers most 2008+ cars)
2. Make sure the **engine is running** — ignition-only is sometimes not enough
3. Try: `python scripts/test_connection.py --protocol 6`

If protocol 6 doesn't work, try protocols 3–9 (different CAN variants). See the
[python-obd protocol list](https://python-obd.readthedocs.io/en/latest/Connections/) for details.
