import socket
import selectors
import struct
import collections
import time
from modules import constants
from modules import promisc
from modules.packet_decoder import decode_packet
from modules import mqtt_handler
from modules import configuration
from modules import ha_discovery
from modules import log

import atexit
import signal
import sys

settings = configuration.read()
log.setup(
    level=settings.get("LOGGING", "Level", fallback="INFO"),
    fmt=settings.get("LOGGING", "Format", fallback="console"),
    paho_level=settings.get("LOGGING", "Paho_Level", fallback="WARNING"),
)
logger = log.get("bridge")

# How often to log a summary of received frames and published values
STATS_INTERVAL = 300


def _shutdown(signum, frame):
    logger.info("stopping", signal=signal.Signals(signum).name)
    sys.exit(0)


# Turn SIGTERM (e.g. `docker stop`) into a normal exit so atexit handlers run.
signal.signal(signal.SIGTERM, _shutdown)


def exit_handler():
    promisc.set(
        settings["NETWORK"]["NIC"], False
    )  # Kick NIC back out of promisc mode on exit


def _mac(raw):
    return ":".join(f"{b:02x}" for b in raw)


def main():
    nic = settings["NETWORK"]["NIC"]
    base_topic = settings["MQTT"]["TOPIC"]
    debug = settings.getboolean("DEBUG", "Enabled")
    ha_enabled = settings.getboolean("HOMEASSISTANT", "Enabled", fallback=False)
    logger.info(
        "starting",
        nic=nic,
        broker=settings["MQTT"]["BROKER"],
        port=int(settings["MQTT"]["PORT"]),
        topic=base_topic,
        client_id=settings["MQTT"]["ID"],
        debug_fields=debug,
        homeassistant=ha_enabled,
    )

    discovery = None
    if ha_enabled:
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

    frames = collections.Counter()  # packet type -> frames received
    published = 0
    errors = 0
    senders = set()
    last_stats = time.monotonic()

    with socket.socket(
        socket.AF_PACKET, socket.SOCK_RAW, socket.htons(constants.PKT_TYPE)
    ) as server_socket:  # Recieve Raw Frames
        server_socket.bind((nic, 0))
        promisc.set(nic, True)  # set NIC to promiscuous mode
        atexit.register(exit_handler)
        logger.info("listening for myenergi frames", nic=nic)
        with selectors.DefaultSelector() as selector:
            selector.register(server_socket.fileno(), selectors.EVENT_READ)
            while True:  # Loop Forever
                ready = selector.select(timeout=STATS_INTERVAL)
                if time.monotonic() - last_stats >= STATS_INTERVAL:
                    logger.info(
                        "stats",
                        interval_s=STATS_INTERVAL,
                        frames={f"0x{t:02X}": n for t, n in sorted(frames.items())},
                        published=published,
                        decode_errors=errors,
                        mqtt_connected=mqtt.is_connected(),
                    )
                    if not frames:
                        logger.warning(
                            "no myenergi frames received; is the NIC on the same "
                            "network segment as the device?",
                            nic=nic,
                        )
                    frames.clear()
                    published = errors = 0
                    last_stats = time.monotonic()
                if not ready:
                    continue
                frame = server_socket.recv(
                    constants.ETH_FRAME_LEN
                )  # get ethernet frame
                header = frame[: constants.ETH_HLEN]  # split header from frame
                dest, source, protocol = struct.unpack(
                    "!6s6sH", header
                )  # unpack header
                payload = frame[constants.ETH_HLEN :]  # unpack payload
                if protocol != constants.PKT_TYPE or len(payload) <= 0x19:
                    continue
                if struct.unpack("4B", payload[:4]) != constants.DATA_HEADER:
                    continue
                packet_type = payload[0x18]
                frames[packet_type] += 1
                if source not in senders:
                    senders.add(source)
                    logger.info(
                        "new sender",
                        mac=_mac(source),
                        device_id=f"0x{payload[0x19]:02X}",
                    )
                try:
                    data = decode_packet(payload, debug)
                except Exception:
                    errors += 1
                    logger.exception(
                        "failed to decode frame",
                        packet_type=f"0x{packet_type:02X}",
                        payload=payload.hex(),
                    )
                    continue
                if not data:
                    continue
                logger.debug(
                    "decoded",
                    packet_type=f"0x{packet_type:02X}",
                    sender=_mac(source),
                    **data,
                )
                if discovery:
                    discovery.announce(data["serial"], data.keys())
                for key in data:
                    result = mqtt.publish(
                        base_topic + "/" + str(data["serial"]) + "/" + key,
                        data[key],
                    )
                    if result.rc == 0:
                        published += 1
                    else:
                        logger.debug("publish failed", key=key, rc=result.rc)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("stopping", signal="SIGINT")
