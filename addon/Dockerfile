# The add-on reuses the bridge image built by CI (linux/amd64 and linux/arm64)
FROM ghcr.io/beryju/mqtt-energi:latest

LABEL io.hass.type="addon"

CMD ["python", "mqtt-bridge/addon.py"]
