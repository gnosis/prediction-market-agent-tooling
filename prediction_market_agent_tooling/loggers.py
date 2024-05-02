import sys
from enum import Enum

from loguru import Logger, logger
from pydantic_settings import BaseSettings, SettingsConfigDict


class LogFormat(str, Enum):
    DEFAULT = "default"
    GCP = "gcp"


class LogConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    LOG_FORMAT: LogFormat = LogFormat.DEFAULT


GCP_LOG_FORMAT = "{level:<.1}{time:MMDD HH:mm:ss.SSSSSS} {process} {name}:{line}] {message} | {extra}"


def patch_logger(logger: Logger) -> None:
    config = LogConfig()

    if config.LOG_FORMAT == LogFormat.GCP:
        format_ = GCP_LOG_FORMAT

    elif config.LOG_FORMAT == LogFormat.DEFAULT:
        format_ = None

    else:
        raise ValueError(f"Unknown log format: {config.LOG_FORMAT}")

    if format_ is not None:
        logger.remove()
        logger.add(
            sys.stdout,
            format=format_,
            level="DEBUG",  # Can be the lowest level, higher ones will use by default this one.
            colorize=True,
        )

    logger.info(f"Patched for {config.LOG_FORMAT=}.")


if not getattr(logger, "_patched", False):
    patch_logger(logger)
    logger._patched = True  # type: ignore[attr-defined] # Hacky way to store a flag on the logger object, to not patch it multiple times.
