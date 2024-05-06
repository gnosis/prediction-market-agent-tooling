import logging
import sys
import typing as t
import warnings
from enum import Enum

from loguru import logger
from pydantic_settings import BaseSettings, SettingsConfigDict


class LogFormat(str, Enum):
    DEFAULT = "default"
    GCP = "gcp"


class LogConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    LOG_FORMAT: LogFormat = LogFormat.DEFAULT


GCP_LOG_LOGURU_FORMAT = (
    "{level:<.1}{time:MMDD HH:mm:ss} {process} {name}:{line}] {message}"
)
GCP_LOG_LOGGING_FORMAT, GCP_LOG_FORMAT_LOGGING_DATEFMT = (
    "%(levelname).1s%(asctime)s %(process)d %(name)s:%(lineno)d] %(message)s"
), "%m%d %H:%M:%S"


def patch_logger() -> None:
    config = LogConfig()

    if config.LOG_FORMAT == LogFormat.GCP:
        format_loguru = GCP_LOG_LOGURU_FORMAT
        format_logging = GCP_LOG_LOGGING_FORMAT
        datefmt_logging = GCP_LOG_FORMAT_LOGGING_DATEFMT

    elif config.LOG_FORMAT == LogFormat.DEFAULT:
        format_loguru, format_logging, datefmt_logging = None, None, None

    else:
        raise ValueError(f"Unknown log format: {config.LOG_FORMAT}")

    # Use logging module for warnings.
    logging.captureWarnings(True)
    # Change warning formatting to a simpler one (no source code in a new line).
    warnings.formatwarning = simple_warning_format

    # Change built-in logging.
    if format_logging is not None:
        logging.basicConfig(
            level=logging.DEBUG, format=format_logging, datefmt=datefmt_logging
        )

    # Change loguru.
    if format_loguru is not None:
        logger.remove()
        logger.add(
            sys.stdout,
            format=format_loguru,
            level="DEBUG",  # Can be the lowest level, higher ones will use by default this one.
            colorize=True,
        )

    logger.info(f"Patched logger for {config.LOG_FORMAT.value} format.")


def simple_warning_format(message, category, filename, lineno, line=None):  # type: ignore[no-untyped-def] # Not typed in the standard library neither.
    return f"{category.__name__}: {message}\n"


if not getattr(logger, "_patched", False):
    patch_logger()
    logger._patched = True  # type: ignore[attr-defined] # Hacky way to store a flag on the logger object, to not patch it multiple times.
