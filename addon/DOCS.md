# mqtt-energi

Sniffs the frames an Eddi V2.1 sends to Wi-Fi on your local network, decodes them and publishes the values to MQTT. With discovery enabled the Eddi shows up in Home Assistant as a device with its sensors.

## Requirements

- An MQTT broker. With the Mosquitto broker add-on and the MQTT integration set up, the add-on finds it automatically; otherwise set **MQTT broker** and its credentials.
- The Home Assistant host must be on the same network segment as the Eddi (the frames are not routed).

## Configuration

Every option is described in the add-on's configuration tab. Usually nothing needs changing: the network interface defaults to the one with the default route.

The add-on uses host networking and the `NET_RAW` and `NET_ADMIN` capabilities to receive raw frames and switch the interface to promiscuous mode. It switches promiscuous mode off again when it stops.

## Energy dashboard

Add **Heater energy** under *Individual devices*. It includes boost; **Diverted energy today** only counts surplus diversion.

More details: https://github.com/BeryJu/mqtt-energi
