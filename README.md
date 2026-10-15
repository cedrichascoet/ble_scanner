# BLE Presence Scanner for Home Assistant

Lightweight Python script that continuously scans for BLE devices on a Raspberry Pi and publishes their presence to **Home Assistant** via MQTT discovery. Supports any number of devices.

## Features

- Persistent BLE scanning using [bleak](https://github.com/hbldh/bleak) — adapter stays open continuously, no start/stop overhead per cycle
- Instant detection via advertisement callback — devices are seen as soon as they advertise, not at the end of a fixed scan window
- Multiple devices tracked in a single scanner
- Automatic Home Assistant MQTT discovery (appears as `device_tracker` entities)
- Publishes `home` / `not_home` state + JSON attributes (RSSI, last seen, MAC) — attributes only sent when device is present, at most every `attr_interval` seconds
- Availability via MQTT last will: if the Pi crashes or drops off the network, Home Assistant shows the trackers as unavailable instead of a stale state
- No flapping on restart: devices get the full `expiry_time` after startup before being marked `not_home`
- Runs as an unprivileged, sandboxed system user (no root needed)
- Time-based expiry: marks a device away only after it has not been seen for a configurable duration
- Graceful shutdown on SIGINT / SIGTERM

## Requirements

- Raspberry Pi with Bluetooth (any model with built-in BT or USB dongle)
- Debian-based OS (Raspberry Pi OS, etc.)
- Python 3.10+

```bash
sudo apt install python3-bleak python3-paho-mqtt
```

## Configuration

All tunable parameters live in `ble_scanner.conf` (INI format). A template is provided as `ble_scanner.conf.sample` — copy and edit it before running:

```bash
cp ble_scanner.conf.sample ble_scanner.conf
nano ble_scanner.conf
```

The script searches for the config in this order:

1. Same directory as the script (`/opt/ble_scanner/ble_scanner.conf`)
2. `/etc/ble_scanner.conf`

```ini
[bluetooth]
# Check interval in seconds (how often expiry is evaluated)
scan_duration = 2.0
# Seconds without detection before marking as not_home
expiry_time = 60
# Minimum seconds between attribute updates while present
attr_interval = 30

[devices]
# mac = nickname  (nickname used in MQTT topic and HA entity name)
AA:BB:CC:DD:EE:FF = tracker1_bob
AA:BB:CC:DD:EE:FF = tracker2_roger

[mqtt]
host = 192.168.x.x
port = 1883
user = mqtt
password = changeme
# $(hostname) is expanded at runtime; default is homeassistant/$(hostname)
topic = homeassistant/$(hostname)

[logging]
# DEBUG, INFO, WARNING or ERROR
level = INFO
```

Comments must be on their own line: `key = value  # comment` makes the comment part of the value.

| Key              | Section    | Description                                   |
|------------------|------------|-----------------------------------------------|
| `scan_duration`  | bluetooth  | How often (in seconds) the expiry check runs; scanning itself is continuous |
| `expiry_time`    | bluetooth  | Seconds without detection before marking as `not_home` (default: 60) |
| `attr_interval`  | bluetooth  | Minimum seconds between attribute updates while a device is present (default: 30); `home` itself is always published at once |
| `mac = nickname` | devices    | One entry per device; nickname used in MQTT topic and HA entity name |
| `host`           | mqtt       | MQTT broker IP or hostname                    |
| `port`           | mqtt       | MQTT broker port                              |
| `user`           | mqtt       | MQTT username                                 |
| `password`       | mqtt       | MQTT password                                 |
| `topic`          | mqtt       | MQTT topic base; `$(hostname)` is expanded at runtime (default: `homeassistant/$(hostname)`) |
| `level`          | logging    | Log level: `DEBUG`, `INFO`, `WARNING` or `ERROR` (default: `INFO`) |

## MQTT Topics

Topics are namespaced by hostname and device nickname:

| Topic | Description |
|-------|-------------|
| `homeassistant/<host>/<nickname>/state` | `home` or `not_home` |
| `homeassistant/<host>/<nickname>/attributes` | JSON: `rssi`, `last_seen`, `mac` |
| `homeassistant/<host>/availability` | `online` / `offline` (retained; `offline` is also the MQTT last will) |
| `homeassistant/device_tracker/<host>_<nickname>/config` | HA discovery payload (retained) |

## Run manually

```bash
python3 ble_scanner.py
```

Root is not required: bleak scans through BlueZ over D-Bus, which Debian opens to the `bluetooth` group. Your user must be in it (`sudo usermod -aG bluetooth $USER`, then log in again).

## Systemd service

A ready-made unit file is provided: `ble_scanner.service`.

The service runs as the unprivileged `ble_scanner` user, sandboxed by systemd: read-only system, no home, no capabilities, network limited to D-Bus and IP.

### Install

```bash
# Dedicated system user, allowed to talk to BlueZ
sudo useradd --system --no-create-home --shell /usr/sbin/nologin -G bluetooth ble_scanner

# Copy the script to a permanent location
sudo mkdir -p /opt/ble_scanner
sudo cp ble_scanner.py /opt/ble_scanner/

# Config holds the MQTT password: readable by root and the service only
sudo install -m 0640 -o root -g ble_scanner ble_scanner.conf /etc/ble_scanner.conf
sudo nano /etc/ble_scanner.conf

# Install the unit file
sudo cp ble_scanner.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ble_scanner
```

### Manage

```bash
sudo systemctl status ble_scanner   # check status
sudo systemctl restart ble_scanner  # restart
sudo systemctl stop ble_scanner     # stop
sudo journalctl -u ble_scanner -f   # follow logs
```

## Home Assistant

Devices are registered automatically via MQTT discovery. No manual HA configuration needed — just ensure the **MQTT integration** is set up in HA and the broker is reachable.

Each device appears as:
- **Entity type:** `device_tracker`
- **Name:** `<nickname> <MAC>` (e.g. `tracker1_bob AA:BB:CC:DD:EE:FF`)
- **States:** `home` / `not_home`

## Tuning

- **Faster state updates:** lower `scan_duration` to `1.0` to reduce the delay between a device being detected and its state being published — detection itself is immediate regardless of this value
- **Reduce false away:** raise `expiry_time` (e.g. `120`) to wait longer before going `not_home`
- **Less MQTT / HA recorder traffic:** raise `attr_interval`; `home` / `not_home` changes are never delayed by it
- **Debug logging:** set `level = DEBUG` in the `[logging]` section
