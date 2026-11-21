"""Logging setup: structlog on top of the stdlib logging module.

Everything, including log records from paho-mqtt, goes through one handler on
stderr, rendered either for humans ("console") or as one JSON object per line
("json", for log collectors).
"""

import logging
import sys

import structlog


def _level(name, default):
    level = logging.getLevelName(str(name).upper())
    return level if isinstance(level, int) else default


def setup(level="INFO", fmt="console", paho_level="WARNING"):
    level = _level(level, logging.INFO)

    shared = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]
    if fmt == "json":
        renderer = structlog.processors.JSONRenderer()
        shared.append(structlog.processors.format_exc_info)
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    structlog.configure(
        processors=shared
        + [
            structlog.stdlib.filter_by_level,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared,  # for stdlib records, e.g. from paho-mqtt
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                renderer,
            ],
        )
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # paho-mqtt logs every packet it sends at DEBUG; keep it quiet by default
    logging.getLogger("paho").setLevel(_level(paho_level, logging.WARNING))


def get(name):
    return structlog.stdlib.get_logger(name)
