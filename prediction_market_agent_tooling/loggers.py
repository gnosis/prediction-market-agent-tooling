import builtins
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


class LogLevel(str, Enum):
    CRITICAL = "CRITICAL"
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"
    DEBUG = "DEBUG"


class LogConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    LOG_FORMAT: LogFormat = LogFormat.DEFAULT
    LOG_LEVEL: LogLevel = LogLevel.DEBUG


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
        print_logging = print_using_loguru_info

    elif config.LOG_FORMAT == LogFormat.DEFAULT:
        format_loguru, format_logging, datefmt_logging = None, None, None
        print_logging = None

    else:
        raise ValueError(f"Unknown log format: {config.LOG_FORMAT}")

    # Change built-in logging.
    if format_logging is not None:
        logging.basicConfig(
            level=config.LOG_LEVEL.value, format=format_logging, datefmt=datefmt_logging
        )

    # Change loguru.
    if format_loguru is not None:
        logger.remove()
        logger.add(
            sys.stdout,
            format=format_loguru,
            level=config.LOG_LEVEL.value,
            colorize=True,
        )

    # Change warning formatting to a simpler one (no source code in a new line).
    warnings.formatwarning = simple_warning_format
    # Use logging module for warnings.
    logging.captureWarnings(True)

    # Use loguru for prints.
    if print_logging is not None:
        builtins.print = print_logging  # type: ignore[assignment] # Monkey patching, it's messy but it works.

    logger.info(f"Patched logger for {config.LOG_FORMAT.value} format.")


def print_using_loguru_info(
    *values: object,
    sep: str = " ",
    end: str = "\n",
    **kwargs: t.Any,
) -> None:
    message = sep.join(map(str, values)) + end
    message = message.strip().replace(
        "\n", "\\n"
    )  # Escape new lines, because otherwise logs will be broken.
    logger.info(message)


def simple_warning_format(message, category, filename, lineno, line=None):  # type: ignore[no-untyped-def] # Not typed in the standard library neither.
    return f"{category.__name__}: {message}".strip().replace(
        "\n", "\\n"
    )  # Escape new lines, because otherwise logs will be broken.


if not getattr(logger, "_patched", False):
    patch_logger()
    logger._patched = True  # type: ignore[attr-defined] # Hacky way to store a flag on the logger object, to not patch it multiple times.
