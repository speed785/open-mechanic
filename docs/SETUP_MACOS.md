# Setup Guide — macOS

This guide covers setting up open-mechanic on macOS with an OBDLink EX USB adapter.

---

## Prerequisites

- Python 3.11 or newer (Homebrew recommended)
- pip
- An OBDLink EX USB adapter (or any ELM327-compatible USB OBD-II adapter)

### Install Python via Homebrew (recommended)

```bash
# Install Homebrew if you don't have it
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python 3.11
brew install python@3.11
```

Check your version:

```bash
python3 --version
# Should show Python 3.11.x or newer
```

---

## FTDI Driver

The OBDLink EX uses an FTDI chip. Driver requirements depend on your macOS version:

| macOS Version | Driver Needed |
|---------------|---------------|
| macOS 12 Ventura and newer | Usually works natively — try without driver first |
| macOS 11 Big Sur and older | Install FTDI VCP driver from ftdichip.com |

### Installing the FTDI VCP Driver (if needed)

1. Go to: https://ftdichip.com/drivers/vcp-drivers/
2. Download the macOS VCP driver (`.dmg` file)
3. Open the `.dmg` and run the installer
4. Restart your Mac
5. If macOS blocks the driver: **System Preferences → Security & Privacy → General** → click "Allow" next to the blocked driver message

---

## Detecting the OBD Adapter

After plugging in the adapter, check for the device:

```bash
ls /dev/cu.usbserial-*
```

Expected output:

```
/dev/cu.usbserial-A50285BI
```

The exact suffix (e.g., `A50285BI`) varies by adapter. Use `cu.*` (call-up) rather than `tty.*` for outgoing connections.

If nothing appears:
- Try unplugging and replugging the adapter
- Check if the FTDI driver is loaded: `kextstat | grep FTDI`
- On macOS 12+, try: `ls /dev/cu.*` to see all serial devices

---

## Install

Clone the repo and install in editable mode with dev dependencies:

```bash
git clone https://github.com/speed785/open-mechanic
cd open-mechanic
pip install -e ".[dev]"
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

# Optional — leave blank to auto-detect /dev/cu.usbserial-*
# Set explicitly if auto-detection fails:
# OBD_PORT=/dev/cu.usbserial-A50285BI
OBD_PORT=
OBD_BAUDRATE=
```

Get a Claude API key at: https://console.anthropic.com/

---

## Test the OBD Connection

With your adapter plugged into the car's OBD-II port and the car's ignition on:

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
...
```

---

## Troubleshooting

### Port not appearing (`/dev/cu.usbserial-*` doesn't exist)

1. Unplug and replug the adapter
2. Check if the FTDI driver is loaded:
   ```bash
   kextstat | grep -i ftdi
   ```
3. On macOS 12+, the driver may be built-in. Try:
   ```bash
   ls /dev/cu.*
   ```
4. If still nothing, install the FTDI VCP driver from ftdichip.com and restart

### Driver blocked by macOS (System Integrity Protection)

macOS may block third-party kernel extensions. After installing the FTDI driver:

1. Go to **System Preferences → Security & Privacy → General**
2. Look for a message about a blocked system extension from FTDI
3. Click **Allow** and restart

On macOS 13+ (Ventura), this is under **System Settings → Privacy & Security**.

### Auto-detection fails but port exists

If `python scripts/test_connection.py` can't find the adapter but `ls /dev/cu.usbserial-*` shows it, set the port explicitly in `.env`:

```bash
OBD_PORT=/dev/cu.usbserial-A50285BI
```

### No data / adapter connects but no PIDs respond

- Make sure the car's ignition is in the "on" position
- Some PIDs are not supported by all vehicles — this is normal
- Try: `python -c "import obd; c = obd.OBD(); print(c.query(obd.commands.ELM_VERSION))"`
