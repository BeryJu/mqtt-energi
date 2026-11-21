import configparser
import os

# config.ini lives next to mqtt-energi.py, independent of the working directory
CFG_NAME = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.ini"
)

# Used when neither config.ini nor the environment sets a value.
DEFAULTS = {
    "NETWORK": {"nic": "eth0"},
    "MQTT": {
        "broker": "localhost",
        "port": "1883",
        "topic": "myenergi",
        "id": "Myenergi-Bridge-1",
        "user": "",
        "pass": "",
    },
    "DEBUG": {"enabled": "False"},
    "LOGGING": {"level": "INFO", "format": "console", "paho_level": "WARNING"},
    "HOMEASSISTANT": {
        "enabled": "False",
        "discovery_prefix": "homeassistant",
        "model": "Eddi",
        "expire_after": "120",
    },
}


def read(path=CFG_NAME, environ=os.environ):
    """Read settings: built-in defaults < config.ini < environment.

    Any option can be overridden with an environment variable named
    <SECTION>_<OPTION>, e.g. MQTT_BROKER, NETWORK_NIC, HOMEASSISTANT_ENABLED.
    """
    config = configparser.ConfigParser()
    config.read_dict(DEFAULTS)
    config.read(path)
    for section in config.sections():
        prefix = section.upper() + "_"
        for name, value in environ.items():
            if name.upper().startswith(prefix) and len(name) > len(prefix):
                config[section][name[len(prefix) :].lower()] = value
    return config
