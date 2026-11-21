# mqtt-energi

Local MQTT bridge for myenergi devices, plus notes on their device-to-device protocol. Not affiliated with myenergi; use at your own risk.

Fork of [PeterTM/mqtt-energi](https://github.com/PeterTM/mqtt-energi). Most of the protocol research and the original bridge come from there; this fork adds Home Assistant discovery, a container image and some further decoding.

An Eddi V2.1 copies the radio packets it sends to Wi-Fi as raw Ethernet frames. The bridge sniffs those on the LAN, decodes them and publishes to MQTT, with Home Assistant discovery. Tested with an Eddi V2.1 on firmware V5.435. V1 devices without network access won't work.

## Quick start

```sh
docker run -d --name mqtt-energi --restart unless-stopped \
  --network host --cap-add NET_RAW --cap-add NET_ADMIN \
  -e NETWORK_NIC=eth0 -e MQTT_BROKER=192.0.2.10 -e HOMEASSISTANT_ENABLED=true \
  ghcr.io/beryju/mqtt-energi:latest
```

Setup, configuration and Home Assistant details: [MQTT Bridge](docs/mqtt_bridge.md).

## Data

* Heater power, live and 1 minute average (W)
* Heater energy (kWh, includes boost)
* Diverted energy today (kWh, surplus diversion only)
* Heater max power (W)
* Boost, stopped and selected heater
* Grid power, 1 minute average (W)
* Supply voltage and frequency
* Heatsink temperature
* Serial number and firmware version
* Live grid and generation power, only from devices that send CT packets

## Docs

* [Communication overview](docs/communication.md)
* [Packet format](docs/data_packets.md)
* [MQTT bridge](docs/mqtt_bridge.md)
