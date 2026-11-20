from paho.mqtt import client as mqtt_client


def _new_client(id):
    # paho-mqtt 2.x requires an explicit callback API version; 1.x has no such arg.
    # The callbacks below accept both the 1.x and the 2.x (VERSION2) signatures.
    if hasattr(mqtt_client, "CallbackAPIVersion"):
        return mqtt_client.Client(mqtt_client.CallbackAPIVersion.VERSION2, id)
    return mqtt_client.Client(id)


def connect(broker, port, id, user, passw, discovery=None, will_topic=None):
    """Connect to the broker. If `discovery` is given, its on_connect/on_message
    hooks run on every (re)connect / incoming message."""

    def on_connect(client, userdata, flags, rc, properties=None):
        # rc is an int on 1.x and a ReasonCode (which compares equal to ints) on 2.x
        if rc == 0:
            print("Connected to MQTT Broker!")
            if discovery:
                discovery.on_connect()
        else:
            print(f"Failed to connect, return code {rc}")

    def on_message(client, userdata, msg):
        if discovery:
            discovery.on_message(msg)

    mqtt = _new_client(id)
    if user:
        mqtt.username_pw_set(user, passw)
    if will_topic:
        mqtt.will_set(will_topic, "offline", qos=1, retain=True)
    mqtt.on_connect = on_connect
    mqtt.on_message = on_message
    mqtt.connect(broker, port)
    return mqtt
