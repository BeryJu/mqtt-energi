# MQTT Bridge
This is a quick and dirty script that captures the packets matching the ethertype and data header of the myenergi packets. This works by putting the PC's NIC into promiscuous mode and looking for packets that match the profile that we are looking for. Once it has found a packet, its payload is processed by the decoder. If the decoder understands the packet type, it will pull out the data and post it to a MQTT broker

## Compatibility
In its current form, this probably only works on linux based systems due to having to set the NIC mode to allow it to recieve all packets. Windows may work in the future if I get around to working out how. 

This has only been tested recieving the following data from a Eddi V2.1 unit. Other capabilities may follow if the protocol is better understood
* Current Supply Voltage / Frequency
* Current Grid Power / Generation Power / Divert Power
* Grid Power (1 minute average) and Heatsink Temperature
* Heater Max Power and Firmware Version
* Heater Power (1 minute average) and Heater Energy (kWh, includes boost; "Diverted energy today" does not)
* Total Diverted Energy
* Active Heater Channel
* Boost & stopped status



## Setup
Dependencies are managed with [uv](https://docs.astral.sh/uv/). From the repository root:

```sh
uv sync
```

This creates `.venv` with paho-mqtt (and ruff for development).

in file config.ini, you need to set
* your broker IP and port
* the topic you want the data posted to
* a unique client ID
* the user/password for ypur mqtt broker (if needed)

 The data will be posted to 

> {topic}/{serialnumber}/{data}

You also need to set the name of the NIC that you are using to allow it to be bound and set to promisc mode. The script needs to be run with root permissions for the moment as it manipulates the NIC to set it to promiscuous mode. From the repository root:

```sh
sudo .venv/bin/python mqtt-bridge/mqtt-energi.py
```

### Configuration via environment
Every option can also be set with an environment variable named `<SECTION>_<OPTION>`, which overrides `config.ini`. For example `NETWORK_NIC`, `MQTT_BROKER`, `MQTT_PORT`, `MQTT_TOPIC`, `MQTT_ID`, `MQTT_USER`, `MQTT_PASS`, `DEBUG_ENABLED`, `HOMEASSISTANT_ENABLED`, `HOMEASSISTANT_DISCOVERY_PREFIX`, `LOGGING_LEVEL`.

### Logging
Logs go to stderr. Configure them in a `[LOGGING]` section or via environment:

| Option | Environment | Default | |
|---|---|---|---|
| `level` | `LOGGING_LEVEL` | `INFO` | `DEBUG` also logs every decoded packet and discovery message |
| `format` | `LOGGING_FORMAT` | `console` | `json` writes one JSON object per line, for log collectors |
| `paho_level` | `LOGGING_PAHO_LEVEL` | `WARNING` | log level of the MQTT client library; `DEBUG` logs every MQTT packet |

At `INFO` the bridge logs startup settings, MQTT connects and disconnects (with a hint when the connection keeps dropping, usually another client using the same `MQTT_ID`), new senders on the network, unknown packet types (once each), and a summary of received frames every 5 minutes.

## Docker
A container image is built by CI for `linux/amd64` and `linux/arm64` and published to `ghcr.io/beryju/mqtt-energi`. Use `latest` (the main branch), a release version like `1.2.3`, or a specific commit's `sha-<commit>` tag.

The container needs the host's network (to see the myenergi frames) plus the `NET_RAW` and `NET_ADMIN` capabilities (raw socket and promiscuous mode):

```sh
docker run -d --name mqtt-energi --restart unless-stopped \
  --network host --cap-add NET_RAW --cap-add NET_ADMIN \
  -e NETWORK_NIC=eth0 -e MQTT_BROKER=192.0.2.10 -e HOMEASSISTANT_ENABLED=true \
  ghcr.io/beryju/mqtt-energi:latest
```

Or with Docker Compose, using the example `compose.yaml` in the repository root:

```sh
docker compose up -d
```

`config.ini` is not copied into the image; mount one at `/app/mqtt-bridge/config.ini` if you prefer a file. On `docker stop` the bridge takes the NIC back out of promiscuous mode.

To build the image yourself instead, run `docker build -t mqtt-energi .` from the repository root.

## Development
Format the code with ruff:

```sh
uv run ruff format .
```

## Home Assistant
The bridge supports [MQTT discovery](https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery). Enable it in config.ini:

```ini
[HOMEASSISTANT]
enabled = True
discovery_prefix = homeassistant   ; must match Home Assistant's discovery prefix
model = Eddi                       ; shown as the device model
expire_after = 120                 ; seconds without data before entities show unavailable (0 = never)
```

The first time a serial number is seen, a retained config is published for each known value to `{discovery_prefix}/{sensor|binary_sensor}/myenergi_{serial}/{key}/config`. The entities show up under one device per serial. State values stay on the existing `{topic}/{serial}/{data}` topics.

The bridge publishes `online` / `offline` (via MQTT last will) to `{topic}/bridge/status` and republishes all configs when Home Assistant comes back `online` on `{discovery_prefix}/status`.

Debug-only raw fields (e.g. `0x36/v1`) are published but not announced to Home Assistant.
