#!/usr/bin/env python3
"""
BLE device scanner for Home Assistant via MQTT.
Scans continuously and publishes presence/absence via MQTT discovery.
"""

import asyncio
import configparser
import json
import logging
import os
import socket
import signal
import sys
import time
from datetime import datetime, timezone

from bleak import BleakScanner
import paho.mqtt.client as mqtt

# --- Load configuration ---
_CONF_SEARCH = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "ble_scanner.conf"),
    "/etc/ble_scanner.conf",
]

_cfg = configparser.ConfigParser(delimiters=("=",))
_loaded = _cfg.read(_CONF_SEARCH)
if not _loaded:
    print(f"ERROR: no config file found (searched: {_CONF_SEARCH})", file=sys.stderr)
    sys.exit(1)

SCAN_DURATION = _cfg.getfloat("bluetooth", "scan_duration", fallback=2.0)
EXPIRY_TIME   = _cfg.getfloat("bluetooth", "expiry_time", fallback=60.0)

if not _cfg.has_section("devices") or not _cfg.items("devices"):
    print("ERROR: no [devices] entries in config", file=sys.stderr)
    sys.exit(1)
# {MAC_UPPER: nickname}
DEVICES = {mac.upper(): nick for mac, nick in _cfg.items("devices")}

MQTT_HOST       = _cfg.get("mqtt", "host")
MQTT_PORT       = _cfg.getint("mqtt", "port", fallback=1883)
MQTT_USER       = _cfg.get("mqtt", "user")
MQTT_PASSWORD   = _cfg.get("mqtt", "password")

HOSTNAME        = socket.gethostname()
MQTT_TOPIC_BASE = _cfg.get("mqtt", "topic", fallback=f"homeassistant/{HOSTNAME}").replace("$(hostname)", HOSTNAME)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

def state_topic(nickname: str) -> str:
    return f"{MQTT_TOPIC_BASE}/{nickname}/state"

def attr_topic(nickname: str) -> str:
    return f"{MQTT_TOPIC_BASE}/{nickname}/attributes"

def discovery_topic(nickname: str) -> str:
    return f"homeassistant/device_tracker/{HOSTNAME}_{nickname}/config"

def build_discovery_payload(mac: str, nickname: str) -> dict:
    return {
        "name": f"{nickname} {mac}",
        "unique_id": f"{HOSTNAME}_{nickname}",
        "state_topic": state_topic(nickname),
        "json_attributes_topic": attr_topic(nickname),
        "payload_home": "home",
        "payload_not_home": "not_home",
        "source_type": "bluetooth_le",
        "device": {
            "identifiers": [f"{HOSTNAME}_{nickname}"],
            "name": f"{nickname} {mac}",
            "connections": [["mac", mac]],
        },
    }


def mqtt_connect() -> mqtt.Client:
    client = mqtt.Client(client_id=f"ble_scanner_{HOSTNAME}", clean_session=True)
    client.username_pw_set(MQTT_USER, MQTT_PASSWORD)

    def on_connect(c, userdata, flags, rc):
        if rc == 0:
            log.info("MQTT connected")
            for mac, nick in DEVICES.items():
                c.publish(discovery_topic(nick), json.dumps(build_discovery_payload(mac, nick)), retain=True)
        else:
            log.error("MQTT connect failed, rc=%d", rc)

    def on_disconnect(c, userdata, rc):
        log.warning("MQTT disconnected rc=%d, will reconnect", rc)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_start()
    return client


async def scan_loop(client: mqtt.Client):
    # {mac: last_seen monotonic timestamp}
    last_seen: dict[str, float] = {mac: time.monotonic() for mac in DEVICES}
    last_state: dict[str, str] = {}

    def publish_state(mac: str, nick: str, state: str, rssi: int | None = None):
        if state != last_state.get(mac):
            client.publish(state_topic(nick), state, retain=True)
            log.info("[%s] state -> %s", nick, state)
            last_state[mac] = state
        attrs = {
            "last_seen": datetime.now(timezone.utc).isoformat(),
            "rssi": rssi,
            "mac": mac,
        }
        client.publish(attr_topic(nick), json.dumps(attrs), retain=True)

    log.info("Scanning for %d device(s), expiry=%ss", len(DEVICES), EXPIRY_TIME)

    while True:
        seen_rssi: dict[str, int] = {}
        try:
            discovered = await BleakScanner.discover(timeout=SCAN_DURATION, return_adv=True)
            for addr, (_, adv) in discovered.items():
                if addr.upper() in DEVICES:
                    seen_rssi[addr.upper()] = adv.rssi
        except Exception as exc:
            log.error("Scan error: %s", exc)

        now = time.monotonic()
        for mac, nick in DEVICES.items():
            if mac in seen_rssi:
                last_seen[mac] = now
                publish_state(mac, nick, "home", seen_rssi[mac])
                log.debug("[%s] seen RSSI=%s", nick, seen_rssi[mac])
            else:
                elapsed = now - last_seen[mac]
                log.debug("[%s] not seen (%.0fs ago)", nick, elapsed)
                if elapsed >= EXPIRY_TIME:
                    publish_state(mac, nick, "not_home")


async def main():
    client = mqtt_connect()
    # Give MQTT a moment to connect
    await asyncio.sleep(1)

    loop = asyncio.get_running_loop()
    stop = asyncio.Event()

    def _signal_handler(*_):
        log.info("Shutting down...")
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    scan_task = asyncio.create_task(scan_loop(client))
    await stop.wait()
    scan_task.cancel()
    try:
        await scan_task
    except asyncio.CancelledError:
        pass

    for mac, nick in DEVICES.items():
        client.publish(state_topic(nick), "not_home", retain=True)
    client.loop_stop()
    client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
