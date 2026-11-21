import collections
import logging
import time

from paho.mqtt import client as mqtt_client

from modules import log

logger = log.get("mqtt")

# Warn about a likely client ID clash after this many drops within this window
FLAPPING_DROPS = 3
FLAPPING_WINDOW = 300


def _new_client(id):
    # paho-mqtt 2.x requires an explicit callback API version; 1.x has no such arg.
    # The callbacks below accept both the 1.x and the 2.x (VERSION2) signatures.
    if hasattr(mqtt_client, "CallbackAPIVersion"):
        return mqtt_client.Client(mqtt_client.CallbackAPIVersion.VERSION2, id)
    return mqtt_client.Client(id)


def connect(broker, port, id, user, passw, discovery=None, will_topic=None):
    """Create a client that connects (and reconnects) in the background once
    loop_start() is called. If `discovery` is given, its on_connect/on_message
    hooks run on every (re)connect / incoming message."""

    def on_connect(client, userdata, flags, rc, properties=None):
        # rc is an int on 1.x and a ReasonCode (which compares equal to ints) on 2.x
        if rc == 0:
            logger.info("connected", broker=broker, port=port, client_id=id)
            if discovery:
                discovery.on_connect()
        else:
            logger.error("connect failed", broker=broker, port=port, reason=str(rc))

    drops = collections.deque(maxlen=FLAPPING_DROPS)
    last_hint = [None]  # monotonic time of the last flapping warning

    def on_disconnect(client, userdata, *args):
        # 1.x: (rc); 2.x: (flags, reason_code, properties)
        rc = args[1] if len(args) >= 2 else args[0]
        if rc == 0:
            logger.info("disconnected")
            return
        logger.warning("connection lost, reconnecting", reason=str(rc))
        drops.append(time.monotonic())
        now = drops[-1]
        flapping = len(drops) == drops.maxlen and now - drops[0] < FLAPPING_WINDOW
        if flapping and (last_hint[0] is None or now - last_hint[0] >= FLAPPING_WINDOW):
            last_hint[0] = now
            logger.warning(
                "connection keeps dropping; is another client using the same "
                "MQTT ID? Set a unique one with MQTT_ID",
                client_id=id,
                drops=len(drops),
                window_s=FLAPPING_WINDOW,
            )

    def on_connect_fail(client, userdata):
        logger.warning(
            "cannot reach broker, retrying", broker=broker, port=port, client_id=id
        )

    def on_message(client, userdata, msg):
        if discovery:
            discovery.on_message(msg)

    mqtt = _new_client(id)
    mqtt.enable_logger(logging.getLogger("paho"))
    if user:
        mqtt.username_pw_set(user, passw)
    if will_topic:
        mqtt.will_set(will_topic, "offline", qos=1, retain=True)
    mqtt.on_connect = on_connect
    mqtt.on_disconnect = on_disconnect
    mqtt.on_connect_fail = on_connect_fail
    mqtt.on_message = on_message
    mqtt.reconnect_delay_set(min_delay=1, max_delay=60)
    logger.info("connecting", broker=broker, port=port, client_id=id, auth=bool(user))
    mqtt.connect_async(broker, port)
    return mqtt
