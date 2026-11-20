FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.9 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY mqtt-bridge/ mqtt-bridge/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

# Settings come from environment variables named <SECTION>_<OPTION>
# (e.g. MQTT_BROKER, NETWORK_NIC), or a config.ini mounted at
# /app/mqtt-bridge/config.ini. Needs --network host, NET_RAW and NET_ADMIN.
CMD ["python", "mqtt-bridge/mqtt-energi.py"]
