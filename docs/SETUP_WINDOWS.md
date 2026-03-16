# Setup Guide — Windows

This guide covers setting up open-mechanic on Windows with an OBDLink EX USB adapter.

---

## Prerequisites

- Python 3.11 or newer from python.org
- An OBDLink EX USB adapter (or any ELM327-compatible USB OBD-II adapter)
- FTDI CDM driver (see below)

### Install Python

1. Go to: https://www.python.org/downloads/
2. Download Python 3.11 or newer
3. Run the installer — **check "Add Python to PATH"** before clicking Install
4. Verify in Command Prompt or PowerShell:

```powershell
python --version
# Should show Python 3.11.x or newer
```

---

## FTDI CDM Driver

The OBDLink EX uses an FTDI chip. Windows requires the FTDI CDM (Combined Driver Model) driver.

1. Go to: https://ftdichip.com/drivers/vcp-drivers/
2. Download the Windows CDM driver (`.exe` installer)
3. Run the installer and follow the prompts
4. Restart your computer

---

## Finding Your COM Port

After installing the driver and plugging in the adapter:

1. Open **Device Manager** (right-click Start → Device Manager)
2. Expand **Ports (COM & LPT)**
3. Look for **USB Serial Port (COM3)** or similar — note the COM number

The COM number varies by system. It might be COM3, COM4, COM5, etc.

---

## Setting the COM Port

**Important**: Auto-detection is unreliable on Windows. You must set the port explicitly.

In your `.env` file, set:

```
OBD_PORT=COM3
```

Replace `COM3` with your actual COM number from Device Manager.

---

## Install

Open Command Prompt or PowerShell, navigate to the project directory, and install:

```powershell
git clone https://github.com/speed785/open-mechanic
cd open-mechanic
pip install -e ".[dev]"
```

---

## Environment Setup

Copy the example env file:

```powershell
copy .env.example .env
```

Edit `.env` with Notepad or any text editor:

```
# Required
ANTHROPIC_API_KEY=sk-ant-...your-key-here...

# Required on Windows — set to your COM port from Device Manager
OBD_PORT=COM3

# Optional
OBD_BAUDRATE=
DB_PATH=data/sessions.db
```

Get a Claude API key at: https://console.anthropic.com/

---

## Test the OBD Connection

With your adapter plugged into the car's OBD-II port and the car's ignition on:

```powershell
python scripts\test_connection.py --port COM3
```

Replace `COM3` with your actual COM port.

Expected output:

```
Connecting to OBD adapter on COM3...
Connected: True
Protocol: ELM327 v1.5 / ISO 15765-4 (CAN 11/500)
RPM: 0 rpm
Coolant Temp: 85 °C
...
```

---

## Troubleshooting

### COM port not found in Device Manager

1. Unplug and replug the adapter
2. Check Device Manager again — look under **Other devices** for an unrecognized device
3. If you see a yellow warning icon, the FTDI driver isn't installed — reinstall from ftdichip.com
4. Try a different USB port on your computer

### `python` not found in Command Prompt

Python wasn't added to PATH during installation. Options:

1. Reinstall Python and check "Add Python to PATH"
2. Or use the full path: `C:\Users\YourName\AppData\Local\Programs\Python\Python311\python.exe`
3. Or use the Windows Store Python: `python3`

### Connection refused / port busy

Another application (like a Bluetooth OBD app or another terminal program) may have the COM port open. Close other OBD applications and try again.

### Antivirus blocking serial access

Some antivirus software blocks serial port access. Add an exception for Python or temporarily disable real-time protection to test.

### `pip install` fails with permission error

Run Command Prompt or PowerShell as Administrator, or use:

```powershell
pip install -e ".[dev]" --user
```

### Auto-detection doesn't work

Windows COM port auto-detection via `python-obd` is unreliable. Always set `OBD_PORT=COM3` (or your port) in `.env`. This is expected behavior on Windows.
