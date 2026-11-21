"""Home Assistant add-on entry point.

Reads the add-on options (/data/options.json), fills in the broker from the
Supervisor's MQTT service when no broker is configured, turns everything into
the <SECTION>_<OPTION> environment variables the bridge understands, and then
runs the bridge in this process.
"""

import json
import os
import runpy
import sys
import urllib.request

OPTIONS_PATH = "/data/options.json"
SUPERVISOR_MQTT = "http://supervisor/services/mqtt"
BRIDGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mqtt-energi.py")


def log(msg):
    # The bridge's own logging is not set up yet at this point
    print(f"[addon] {msg}", file=sys.stderr, flush=True)


def default_route_interface():
    """Name of the interface that carries the IPv4 default route."""
    with open("/proc/net/route") as f:
        next(f)  # header
        for line in f:
            fields = line.split()
            if fields[1] == "00000000" and int(fields[3], 16) & 0x2:  # RTF_GATEWAY
                return fields[0]
    return None


def supervisor_mqtt():
    """Broker details from the Supervisor's MQTT service, or None."""
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        return None
    req = urllib.request.Request(
        SUPERVISOR_MQTT, headers={"Authorization": f"Bearer {token}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.load(resp).get("data") or None
    except (OSError, ValueError) as e:  # no MQTT service, or a bad response
        log(f"no MQTT service from the Supervisor: {e}")
        return None


def build_env(options, mqtt_service):
    env = {}
    nic = options.get("network_interface") or default_route_interface()
    if not nic:
        raise SystemExit("no network_interface set and no default route found")
    env["NETWORK_NIC"] = nic

    if options.get("mqtt_host"):
        env["MQTT_BROKER"] = options["mqtt_host"]
        env["MQTT_PORT"] = str(options.get("mqtt_port") or 1883)
        env["MQTT_USER"] = options.get("mqtt_user") or ""
        env["MQTT_PASS"] = options.get("mqtt_password") or ""
        log(f"using configured broker {env['MQTT_BROKER']}:{env['MQTT_PORT']}")
    elif mqtt_service:
        env["MQTT_BROKER"] = mqtt_service["host"]
        env["MQTT_PORT"] = str(mqtt_service.get("port") or 1883)
        env["MQTT_USER"] = mqtt_service.get("username") or ""
        env["MQTT_PASS"] = mqtt_service.get("password") or ""
        log(f"using Home Assistant's broker {env['MQTT_BROKER']}:{env['MQTT_PORT']}")
    else:
        raise SystemExit(
            "no MQTT broker: install the Mosquitto broker add-on or set mqtt_host"
        )

    env["MQTT_TOPIC"] = options.get("mqtt_topic") or "myenergi"
    env["MQTT_ID"] = options.get("mqtt_client_id") or "mqtt-energi-addon"
    env["HOMEASSISTANT_ENABLED"] = str(options.get("discovery", True))
    env["HOMEASSISTANT_DISCOVERY_PREFIX"] = (
        options.get("discovery_prefix") or "homeassistant"
    )
    env["HOMEASSISTANT_EXPIRE_AFTER"] = str(options.get("expire_after", 120))
    env["DEBUG_ENABLED"] = str(options.get("debug_fields", False))
    env["LOGGING_LEVEL"] = options.get("log_level") or "INFO"
    return env


def main():
    try:
        with open(OPTIONS_PATH) as f:
            options = json.load(f)
    except FileNotFoundError:
        options = {}
    service = None if options.get("mqtt_host") else supervisor_mqtt()
    os.environ.update(build_env(options, service))
    sys.argv = [BRIDGE]
    runpy.run_path(BRIDGE, run_name="__main__")


if __name__ == "__main__":
    main()
