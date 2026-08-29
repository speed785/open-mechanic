# Setup Guide — Linux

This guide covers the supported OBDLink EX path for a **2024 Jeep Wrangler JL 4xe**.
OBDLink EX is the only required diagnostic hardware for this enhanced path.

## Install

Python 3.11 or newer is required.

```bash
git clone https://github.com/speed785/open-mechanic
cd open-mechanic
pip install -e ".[dev,api]"
```

An API key is not required for local diagnostics. Configure `ANTHROPIC_API_KEY` only if
you separately choose to send a diagnosis to Anthropic.

## Detect the adapter and grant serial access

The OBDLink EX uses an FTDI USB serial interface supported by the Linux kernel.

```bash
ls -l /dev/ttyUSB*
```

The device is commonly `/dev/ttyUSB0`, but use the path shown on your system. On
distributions that assign serial ports to `dialout`:

```bash
sudo usermod -a -G dialout "$USER"
```

Log out and back in, then verify:

```bash
groups
ls -l /dev/ttyUSB0
```

Do not run open-mechanic as root and do not make the device world-writable. A udev ACL
or your distribution's serial-device group is the appropriate alternative if
`dialout` is not used.

## Parked module scan

Park in a ventilated location, set the parking brake, and put the ignition in RUN with
the engine off. Connect the OBDLink EX to the vehicle and computer, then run:

```bash
open-mechanic stellantis-scan \
  --vehicle wrangler_jl_4xe_2024 \
  --port /dev/ttyUSB0 \
  --protocol 6 \
  --baudrate 115200 \
  --timeout 1
```

For this vehicle path, protocol 6 and 115200 baud are fixed. The timeout must be
greater than zero and at most 10 seconds. The scan is read-only, contacts only
cataloged module addresses, and ends after one finite pass.

Results are per module. `timed_out`, `negative_response`, `gateway_blocked`, and
`unsupported` can appear as structured partial states; provenance can report
`community_unverified`. Do not treat a missing or unsupported field as zero, and
do not assume an unknown DTC has a manufacturer-specific definition.

## Bounded cruise view

The current public catalog has no verified manufacturer-specific cruise DIDs. This
command therefore reports the cruise group as unsupported/not cataloged without
guessing or probing arbitrary identifiers:

```bash
open-mechanic stellantis-live \
  --vehicle wrangler_jl_4xe_2024 \
  --group cruise \
  --samples 3 \
  --interval 1 \
  --port /dev/ttyUSB0 \
  --protocol 6 \
  --baudrate 115200 \
  --timeout 1
```

`--samples` must be 1–60. `--interval` must be greater than zero and at most 10
seconds. Ctrl-C stops collection and closes the adapter.

Do the parked scan first. If a later diagnostic procedure requires observing the
vehicle while moving, a **passenger or qualified technician** must operate the
computer. The driver must not operate the computer or read changing output.

## Privacy and gateway limits

No diagnostic history is saved by default. These commands create no vehicle profile,
session log, database entry, result cache, or telemetry and make no AI/network request.

AutoAuth and an SGW bypass cable are neither required nor claimed for the supported
public/read-only path. If the security gateway refuses a request, open-mechanic reports
the restriction and stops; it does not unlock or bypass the gateway.

## Troubleshooting

- **Port absent:** reconnect USB, inspect `journalctl -k`, and check whether the device
  became `/dev/ttyUSB1` or another explicit path.
- **Permission denied:** re-check the device group and your post-login group list. Do
  not use `sudo open-mechanic`.
- **Adapter timeout:** verify ignition is in RUN, the explicit port is correct, and the
  OBDLink EX LEDs indicate power. Keep `--protocol 6 --baudrate 115200` fixed.
- **One module unavailable:** retain the other results. Per-module partial failure is
  expected when a module is absent, asleep, protected, or not applicable.
- **Cruise fields unsupported:** this is the expected honest result until acceptable
  public provenance supports specific DIDs; do not sweep addresses or identifiers.
