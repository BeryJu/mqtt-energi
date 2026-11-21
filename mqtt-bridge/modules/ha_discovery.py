"""Home Assistant MQTT discovery for the myenergi bridge.

For every device serial seen on the wire, publish one retained discovery config
per known data key to

    {prefix}/{component}/myenergi_{serial}/{key}/config

so the entities appear in Home Assistant grouped under one device. State values
stay on the bridge's existing topics ({topic}/{serial}/{key}).

See https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery
"""

import json
import threading

# Decoded data keys that Home Assistant should know about. Keys not listed here
# (e.g. the raw 0x36/v1 debug fields) are still published, just not announced.
ENTITIES = {
    "voltage": {
        "component": "sensor",
        "name": "Supply voltage",
        "device_class": "voltage",
        "unit_of_measurement": "V",
        "state_class": "measurement",
    },
    "frequency": {
        "component": "sensor",
        "name": "Supply frequency",
        "device_class": "frequency",
        "unit_of_measurement": "Hz",
        "state_class": "measurement",
    },
    "diverted_kWh": {
        # Resets daily; total_increasing treats the drop to 0 as a new cycle.
        "component": "sensor",
        "name": "Diverted energy today",
        "device_class": "energy",
        "unit_of_measurement": "kWh",
        "state_class": "total_increasing",
    },
    "divert_pwr_w": {
        # Published as divert_pwr before; keep its discovery id so the existing
        # Home Assistant entity (and its history) carries over.
        "id": "divert_pwr",
        "component": "sensor",
        "name": "Divert power",
        "device_class": "power",
        "unit_of_measurement": "W",
        "state_class": "measurement",
    },
    "grid_pwr": {
        "component": "sensor",
        "name": "Grid power",
        "device_class": "power",
        "unit_of_measurement": "W",
        "state_class": "measurement",
    },
    "gen_pwr": {
        "component": "sensor",
        "name": "Generation power",
        "device_class": "power",
        "unit_of_measurement": "W",
        "state_class": "measurement",
    },
    "heater1": {
        "component": "binary_sensor",
        "name": "Heater 1 selected",
        "icon": "mdi:water-boiler",
    },
    "heater2": {
        "component": "binary_sensor",
        "name": "Heater 2 selected",
        "icon": "mdi:water-boiler",
    },
    "boost": {
        "component": "binary_sensor",
        "name": "Boost",
        "device_class": "running",
        "icon": "mdi:rocket-launch",
    },
    "stopped": {
        "component": "binary_sensor",
        "name": "Stopped",
        "icon": "mdi:stop-circle-outline",
    },
}


class Discovery:
    def __init__(
        self, mqtt, base_topic, prefix="homeassistant", model="Eddi", expire_after=120
    ):
        self.mqtt = mqtt
        self.base_topic = base_topic
        self.prefix = prefix
        self.model = model
        self.expire_after = expire_after
        self.availability_topic = f"{base_topic}/bridge/status"
        self.status_topic = f"{prefix}/status"  # Home Assistant birth/will
        self._announced = {}  # serial -> set of keys already announced
        # announce() runs on the capture loop, reannounce() on the MQTT thread
        self._lock = threading.RLock()

    def _config(self, serial, key, spec):
        uid = f"myenergi_{serial}_{spec.get('id', key)}"
        cfg = {
            "name": spec["name"],
            "unique_id": uid,
            "object_id": uid,
            "state_topic": f"{self.base_topic}/{serial}/{key}",
            "availability_topic": self.availability_topic,
            "device": {
                "identifiers": [f"myenergi_{serial}"],
                "name": f"{self.model} {serial}",
                "manufacturer": "myenergi",
                "model": self.model,
                "serial_number": str(serial),
            },
            "origin": {"name": "mqtt-energi"},
        }
        for opt in ("device_class", "unit_of_measurement", "state_class", "icon"):
            if opt in spec:
                cfg[opt] = spec[opt]
        if spec["component"] == "binary_sensor":
            cfg["payload_on"] = "1"
            cfg["payload_off"] = "0"
        if self.expire_after:
            cfg["expire_after"] = self.expire_after
        return cfg

    def announce(self, serial, keys):
        """Publish discovery configs for any keys of `serial` not yet announced."""
        with self._lock:
            done = self._announced.setdefault(serial, set())
            for key in keys:
                spec = ENTITIES.get(key)
                if spec is None or key in done:
                    continue
                object_id = spec.get("id", key)
                topic = f"{self.prefix}/{spec['component']}/myenergi_{serial}/{object_id}/config"
                self.mqtt.publish(
                    topic,
                    json.dumps(self._config(serial, key, spec)),
                    qos=1,
                    retain=True,
                )
                done.add(key)

    def reannounce(self):
        """Re-send all configs, e.g. after Home Assistant restarts."""
        with self._lock:
            known = {s: set(k) for s, k in self._announced.items()}
            self._announced.clear()
            for serial, keys in known.items():
                self.announce(serial, keys)

    def on_connect(self):
        self.mqtt.publish(self.availability_topic, "online", qos=1, retain=True)
        self.mqtt.subscribe(self.status_topic)
        self.reannounce()

    def on_message(self, msg):
        if msg.topic == self.status_topic and msg.payload == b"online":
            self.reannounce()
