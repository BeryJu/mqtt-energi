import socket
import selectors
import struct
from modules import constants
from modules import promisc
from modules.packet_decoder import decode_packet
from modules import mqtt_handler
from modules import configuration
from modules import ha_discovery

import atexit
import signal
import sys

settings = configuration.read()

# Turn SIGTERM (e.g. `docker stop`) into a normal exit so atexit handlers run.
signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))


def exit_handler():
    promisc.set(
        settings["NETWORK"]["NIC"], False
    )  # Kick NIC back out of promisc mode on exit


atexit.register(exit_handler)


def main():
    base_topic = settings["MQTT"]["TOPIC"]
    discovery = None
    if settings.getboolean("HOMEASSISTANT", "Enabled", fallback=False):
        # Discovery needs the client, the client needs discovery's callbacks:
        # create it first, attach the client right after connecting.
        discovery = ha_discovery.Discovery(
            None,
            base_topic,
            prefix=settings.get(
                "HOMEASSISTANT", "Discovery_Prefix", fallback="homeassistant"
            ),
            model=settings.get("HOMEASSISTANT", "Model", fallback="Eddi"),
            expire_after=settings.getint("HOMEASSISTANT", "Expire_After", fallback=120),
        )
    mqtt = mqtt_handler.connect(
        settings["MQTT"]["BROKER"],
        int(settings["MQTT"]["PORT"]),
        settings["MQTT"]["ID"],
        settings["MQTT"]["User"],
        settings["MQTT"]["pass"],
        discovery=discovery,
        will_topic=discovery.availability_topic if discovery else None,
    )
    if discovery:
        discovery.mqtt = mqtt
    mqtt.loop_start()
    debug = settings.getboolean("DEBUG", "Enabled")
    print(f"Debug: {debug}")
    with socket.socket(
        socket.AF_PACKET, socket.SOCK_RAW, socket.htons(constants.PKT_TYPE)
    ) as server_socket:  # Recieve Raw Frames
        server_socket.bind((settings["NETWORK"]["NIC"], 0))
        promisc.set(settings["NETWORK"]["NIC"], True)  # set NIC to promiscuous mode
        with selectors.DefaultSelector() as selector:
            selector.register(server_socket.fileno(), selectors.EVENT_READ)
            while True:  # Loop Forever
                ready = selector.select()
                if ready:
                    frame = server_socket.recv(
                        constants.ETH_FRAME_LEN
                    )  # get ethernet frame
                    header = frame[: constants.ETH_HLEN]  # split header from frame
                    dest, source, protocol = struct.unpack(
                        "!6s6sH", header
                    )  # unpack header
                    payload = frame[constants.ETH_HLEN :]  # unpack payload
                    if protocol == constants.PKT_TYPE:
                        start = struct.unpack("4B", payload[:4])
                        if start == constants.DATA_HEADER:
                            data = decode_packet(payload, debug)
                            if data:
                                print(data)
                                if discovery:
                                    discovery.announce(data["serial"], data.keys())
                            for key in data:
                                mqtt.publish(
                                    base_topic + "/" + str(data["serial"]) + "/" + key,
                                    data[key],
                                )


if __name__ == "__main__":
    main()
