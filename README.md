# BLE Presence Scanner for Home Assistant

Lightweight Python script that continuously scans for BLE devices on a Raspberry Pi and publishes their presence to **Home Assistant** via MQTT discovery. Supports any number of devices.

## Features

- Continuous BLE scanning using [bleak](https://github.com/hbldh/bleak)
- Multiple devices in a single scan pass
- Automatic Home Assistant MQTT discovery (appears as `device_tracker` entities)
- Publishes `home` / `not_home` state + JSON attributes (RSSI, last seen, MAC)
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
scan_duration = 2.0       # BLE scan window in seconds (lower = faster, min ~1.0)
expiry_time = 60          # seconds without detection before marking as not_home

[devices]
# mac = nickname  (nickname used in MQTT topic and HA entity name)
AA:BB:CC:DD:EE:FF = tracker1_bob
AA:BB:CC:DD:EE:FF = tracker2_roger

[mqtt]
host = 192.169.x.x
port = 1883
user = mqtt
password = changeme
# $(hostname) is expanded at runtime; default is homeassistant/$(hostname)
topic = homeassistant/$(hostname)
```

| Key              | Section    | Description                                   |
|------------------|------------|-----------------------------------------------|
| `scan_duration`  | bluetooth  | BLE scan window in seconds                    |
| `expiry_time`    | bluetooth  | Seconds without detection before marking as `not_home` (default: 60) |
| `mac = nickname` | devices    | One entry per device; nickname used in MQTT topic and HA entity name |
| `host`           | mqtt       | MQTT broker IP or hostname                    |
| `port`           | mqtt       | MQTT broker port                              |
| `user`           | mqtt       | MQTT username                                 |
| `password`       | mqtt       | MQTT password                                 |
| `topic`          | mqtt       | MQTT topic base; `$(hostname)` is expanded at runtime (default: `homeassistant/$(hostname)`) |

## MQTT Topics

Topics are namespaced by hostname and device nickname:

| Topic | Description |
|-------|-------------|
| `homeassistant/<host>/<nickname>/state` | `home` or `not_home` |
| `homeassistant/<host>/<nickname>/attributes` | JSON: `rssi`, `last_seen`, `mac` |
| `homeassistant/device_tracker/<host>_<nickname>/config` | HA discovery payload (retained) |

## Run manually

```bash
sudo python3 ble_scanner.py
```

Root is required for BLE scanning on Linux.

## Systemd service

A ready-made unit file is provided: `ble_scanner.service`.

### Install

```bash
# Copy script and config to a permanent location
sudo mkdir -p /opt/ble_scanner
sudo cp ble_scanner.py ble_scanner.conf /opt/ble_scanner/
# Edit config before starting
sudo nano /opt/ble_scanner/ble_scanner.conf

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

- **Faster detection:** lower `scan_duration` to `1.0` — minimum reliable value depends on the BT adapter
- **Reduce false away:** raise `expiry_time` (e.g. `120`) to wait longer before going `not_home`
- **Debug logging:** change `logging.basicConfig(level=logging.INFO, ...)` to `level=logging.DEBUG`
