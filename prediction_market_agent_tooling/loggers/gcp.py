import typing as t

from google.cloud import logging as gcp_logging
from loguru import logger

if t.TYPE_CHECKING:
    from loguru import Message

GCP_LOGGING_CLIENT = gcp_logging.Client()
GCP_LOGGER = GCP_LOGGING_CLIENT.logger("gcp-logger")


def log_to_gcp(message: "Message") -> None:
    GCP_LOGGER.log_text(
        message.record["message"], severity=message.record["level"].name
    )


if not getattr(logger, "_patched_for_gcp", False):
    logger.add(log_to_gcp)
    logger._patched_for_gcp = True  # type: ignore[attr-defined] # Hacky way to store a flag on the logger object, to not patch it multiple times.
