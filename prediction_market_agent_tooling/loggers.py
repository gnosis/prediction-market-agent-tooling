import builtins
import logging
import sys
import typing as t
from enum import Enum

import typer.main
from loguru import logger
from pydantic_settings import BaseSettings, SettingsConfigDict
from pythonjsonlogger import jsonlogger
from tenacity import RetryError

UNPATCHED_PRINT_FN = builtins.print


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


class _CustomJsonFormatter(jsonlogger.JsonFormatter):
    MAX_MESSAGE_LENGTH = 50_000

    def add_fields(
        self,
        log_record: dict[str, t.Any],
        record: logging.LogRecord,
        message_dict: dict[str, t.Any],
    ) -> None:
        super().add_fields(log_record, record, message_dict)
        # Include "level" and "severity" with the same value as "levelname" to be friendly with log aggregators.
        if log_record.get("levelname"):
            log_record["level"] = log_record["levelname"]
            log_record["severity"] = log_record["levelname"]

        message = str(log_record.get("message", ""))
        if message and len(message) > self.MAX_MESSAGE_LENGTH:
            log_record["message"] = (
                message[: self.MAX_MESSAGE_LENGTH] + " . . . TRUNCATED . . ."
            )

    @staticmethod
    def get_handler() -> logging.StreamHandler:  # type: ignore # Seems correct, but mypy doesn't like it.
        logHandler = logging.StreamHandler()
        formatter = _CustomJsonFormatter("%(asctime)s %(levelname)s %(message)s")
        logHandler.setFormatter(formatter)
        return logHandler


def _handle_exception(
    exc_type: type[BaseException], exc_value: BaseException, exc_traceback: t.Any
) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    exp_details: BaseException | None = exc_value
    if isinstance(exc_value, RetryError):
        # In case of RetryError from tenacity, add last attempt's exp to the log, otherwise we won't see the exception's message in the logs.
        exp_details = exc_value.last_attempt.exception()

    logger.error(
        # Do not use f-string here, loguru internally calls `message.format(*args, **kwargs)` and in case you put {} into the message (for example, dict-formatted exception from evm),
        # it would throw an error.
        "Uncaught exception: {exp_details}",
        exp_details=exp_details,
        exc_info=(exc_type, exc_value, exc_traceback),
    )


def patch_logger(force_patch: bool = False) -> None:
    """
    Function to patch loggers according to the deployed environment.
    Patches Loguru's logger, Python's default logger, warnings library and also monkey-patch print function as many libraries just use it.
    """
    if force_patch or not getattr(logger, "_patched", False):
        logger._patched = True  # type: ignore[attr-defined] # Hacky way to store a flag on the logger object, to not patch it multiple times.
    else:
        return

    config = LogConfig()

    if config.LOG_FORMAT == LogFormat.GCP:
        handler = _CustomJsonFormatter.get_handler()
        print_logging = print_using_logger_info

        # Patch raised exceptions.
        sys.excepthook = _handle_exception
        typer.main.except_hook = _handle_exception  # type: ignore # Monkey patching, it's messy but it works.

    elif config.LOG_FORMAT == LogFormat.DEFAULT:
        handler = None
        print_logging = None

    else:
        raise ValueError(f"Unknown log format: {config.LOG_FORMAT}")

    # Change built-in logging.
    if handler is not None:
        logging.basicConfig(
            level=config.LOG_LEVEL.value,
            handlers=[handler],
        )
        # Configure all existing loggers
        for logger_name in logging.root.manager.loggerDict:
            existing_logger = logging.getLogger(logger_name)
            existing_logger.setLevel(config.LOG_LEVEL.value)
            # Remove existing handlers
            if existing_logger.hasHandlers():
                existing_logger.handlers.clear()
            # And add ours only
            existing_logger.addHandler(handler)
            existing_logger.propagate = False

    # Change loguru.
    if handler is not None:
        logger.remove()
        logger.add(
            handler,
            level=config.LOG_LEVEL.value,
            colorize=False,
            catch=False,
        )

    # Use logging module for warnings.
    logging.captureWarnings(True)

    # Use loguru for prints.
    if print_logging is not None:
        builtins.print = print_logging  # type: ignore[assignment] # Monkey patching, it's messy but it works.

    logger.info(f"Patched logger for {config.LOG_FORMAT.value} format.")


def print_using_logger_info(
    *values: object,
    sep: str = " ",
    end: str = "\n",
    **kwargs: t.Any,
) -> None:
    # If `logger.exception` is used, loguru+traceback somehow uses `print` statement to format the error stack,
    # if that happens, without this if condition, it errors out because of deadlock and/or recursion errors.
    # This is hacky, but that's exactly how loguru is checking for it internally..
    if getattr(logger._core.handlers[1]._lock_acquired, "acquired", False):  # type: ignore # They use stubs and didn't type this.
        UNPATCHED_PRINT_FN(*values, sep=sep, end=end, **kwargs)
    else:
        logger.info(sep.join(map(str, values)) + end)


patch_logger()
