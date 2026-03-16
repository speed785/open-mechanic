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

**You must log out and log back in** (or reboot) for the group change to take effect.

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

# Optional — leave blank to auto-detect /dev/ttyUSB0
OBD_PORT=
OBD_BAUDRATE=
```

Get a Claude API key at: https://console.anthropic.com/

---

## Test the OBD Connection

With your adapter plugged into the car's OBD-II port and the car's ignition on (key to "on" position, engine not required):

```bash
python scripts/test_connection.py
```

Expected output:

```
Connecting to OBD adapter...
Connected: True
Protocol: ELM327 v1.5 / ISO 15765-4 (CAN 11/500)
RPM: 0 rpm
Coolant Temp: 85 °C
Vehicle Speed: 0 kph
...
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
