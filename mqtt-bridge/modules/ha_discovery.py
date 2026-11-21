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

from modules import log

logger = log.get("discovery")

# Decoded data keys that Home Assistant should know about. Keys not listed here
# (e.g. the raw 0x36/v1 debug fields) are still published, just not announced.
# "models" limits an entity to those devices (default: Eddi only).
ENTITIES = {
    "voltage": {
        "models": ("Eddi", "Zappi"),
        "component": "sensor",
        "name": "Supply voltage",
        "device_class": "voltage",
        "unit_of_measurement": "V",
        "state_class": "measurement",
    },
    "frequency": {
        "models": ("Eddi", "Zappi"),
        "component": "sensor",
        "name": "Supply frequency",
        "device_class": "frequency",
        "unit_of_measurement": "Hz",
        "state_class": "measurement",
    },
    "diverted_kWh": {
        # Resets daily; total_increasing treats the drop to 0 as a new cycle.
        "component": "sensor",
        "name": "Diverted energy today (excludes boost)",
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
    "heater_max_pwr_w": {
        # V^2 / element resistance: what the heater draws at full output
        "component": "sensor",
        "name": "Heater max power",
        "device_class": "power",
        "unit_of_measurement": "W",
        "state_class": "measurement",
    },
    "firmware": {
        "component": "sensor",
        "name": "Firmware",
        "icon": "mdi:chip",
        "entity_category": "diagnostic",
    },
    "heater_pwr_1m_w": {
        # From the per-minute 0x36 records, so updates about once a minute.
        "component": "sensor",
        "name": "Heater power (1 min average)",
        "device_class": "power",
        "unit_of_measurement": "W",
        "state_class": "measurement",
        "expire_after": 300,
    },
    "heater_kWh": {
        # Diverted and boost heating, unlike diverted_kWh. Counts from 0 when the bridge
        # starts; total_increasing treats that as a new cycle.
        "component": "sensor",
        "name": "Heater energy",
        "device_class": "energy",
        "unit_of_measurement": "kWh",
        "state_class": "total_increasing",
    },
    "grid_pwr_1m_w": {
        # From the per-minute 0x36 records, so updates about once a minute.
        "component": "sensor",
        "name": "Grid import (1 min average)",
        "device_class": "power",
        "unit_of_measurement": "W",
        "state_class": "measurement",
        "expire_after": 300,
    },
    "heatsink_temp_c": {
        "component": "sensor",
        "name": "Heatsink temperature",
        "device_class": "temperature",
        "unit_of_measurement": "°C",
        "state_class": "measurement",
        "entity_category": "diagnostic",
        "expire_after": 300,
    },
    "grid_pwr_w": {
        # Live grid CT reading from the Zappi, about once a second
        "models": ("Zappi",),
        "component": "sensor",
        "name": "Grid power",
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


def _applies(spec, model):
    return model in spec.get("models", ("Eddi",))


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
        self._models = {}  # serial -> model name
        # announce() runs on the capture loop, reannounce() on the MQTT thread
        self._lock = threading.RLock()

    def _topic(self, serial, key, spec):
        object_id = spec.get("id", key)
        return f"{self.prefix}/{spec['component']}/myenergi_{serial}/{object_id}/config"

    def _config(self, serial, key, spec):
        model = self._models.get(serial, self.model)
        uid = f"myenergi_{serial}_{spec.get('id', key)}"
        cfg = {
            "name": spec["name"],
            "unique_id": uid,
            "object_id": uid,
            "state_topic": f"{self.base_topic}/{serial}/{key}",
            "availability_topic": self.availability_topic,
            "device": {
                "identifiers": [f"myenergi_{serial}"],
                "name": f"{model} {serial}",
                "manufacturer": "myenergi",
                "model": model,
                "serial_number": str(serial),
            },
            "origin": {"name": "mqtt-energi"},
        }
        for opt in (
            "device_class",
            "unit_of_measurement",
            "state_class",
            "icon",
            "entity_category",
        ):
            if opt in spec:
                cfg[opt] = spec[opt]
        if spec["component"] == "binary_sensor":
            cfg["payload_on"] = "1"
            cfg["payload_off"] = "0"
        expire_after = spec.get("expire_after", self.expire_after)
        if self.expire_after and expire_after:
            cfg["expire_after"] = max(expire_after, self.expire_after)
        return cfg

    def _clear_foreign(self, serial, model):
        """Remove retained configs of entities this device type does not have.

        Older versions announced every device as an Eddi, so e.g. a Zappi could
        show up with heater and boost entities.
        """
        for key, spec in ENTITIES.items():
            if not _applies(spec, model):
                self.mqtt.publish(
                    self._topic(serial, key, spec), "", qos=1, retain=True
                )

    def announce(self, serial, keys, model=None):
        """Publish discovery configs for any keys of `serial` not yet announced."""
        with self._lock:
            model = model or self._models.get(serial) or self.model
            if serial not in self._models:
                self._models[serial] = model
                self._clear_foreign(serial, model)
            done = self._announced.setdefault(serial, set())
            announced = 0
            for key in keys:
                spec = ENTITIES.get(key)
                if spec is None or key in done or not _applies(spec, model):
                    continue
                topic = self._topic(serial, key, spec)
                self.mqtt.publish(
                    topic,
                    json.dumps(self._config(serial, key, spec)),
                    qos=1,
                    retain=True,
                )
                logger.debug("announced entity", serial=serial, key=key, topic=topic)
                done.add(key)
                announced += 1
            if announced:
                logger.info(
                    "announced to Home Assistant",
                    serial=serial,
                    model=model,
                    entities=announced,
                )

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
        if msg.topic == self.status_topic:
            logger.info(
                "Home Assistant status", status=msg.payload.decode(errors="replace")
            )
            if msg.payload == b"online":
                self.reannounce()
