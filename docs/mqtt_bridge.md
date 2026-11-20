# MQTT Bridge
This is a quick and dirty script that captures the packets matching the ethertype and data header of the myenergi packets. This works by putting the PC's NIC into promiscuous mode and looking for packets that match the profile that we are looking for. Once it has found a packet, its payload is processed by the decoder. If the decoder understands the packet type, it will pull out the data and post it to a MQTT broker

## Compatibility
In its current form, this probably only works on linux based systems due to having to set the NIC mode to allow it to recieve all packets. Windows may work in the future if I get around to working out how. 

This has only been tested recieving the following data from a Eddi V2.1 unit. Other capabilities may follow if the protocol is better understood
* Current Supply Voltage / Frequency
* Current Grid Power / Generation Power / Divert Power
* Total Diverted Energy
* Active Heater Channel
* Boost & stopped status



## Setup
Your python installation needs paho.mqtt installed

in file config.ini, you need to set
* your broker IP and port
* the topic you want the data posted to
* a unique client ID
* the user/password for ypur mqtt broker (if needed)

 The data will be posted to 

> {topic}/{serialnumber}/{data}

You also need to set the name of the NIC that you are using to allow it to be bound and set to promisc mode. The script needs to be run with root permissions for the moment as it manipulates the NIC to set it to promiscuous mode. 

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
