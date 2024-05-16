from enum import Enum

import streamlit as st
from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from prediction_market_agent_tooling.loggers import logger


class LoggedUser(BaseModel):
    email: str
    password: SecretStr


class LoggingSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )
    free_for_everyone: bool = False
    free_access_codes: list[SecretStr] = []
    users: list[LoggedUser] = []


class LoggedEnum(str, Enum):
    SELF_PAYING = "self_paying"
    FREE_ACCESS = "free_access"
    LOGGED_ACCESS = "logged_access"


def find_logged_user(email: str, password: SecretStr) -> LoggedUser | None:
    logging_settings = LoggingSettings()

    for user in logging_settings.users:
        if (
            user.email == email
            and user.password.get_secret_value() == password.get_secret_value()
        ):
            return user

    return None


def streamlit_login() -> tuple[LoggedEnum, LoggedUser | None]:
    logging_settings = LoggingSettings()
    free_access_code = st.query_params.get("free_access_code")

    if logging_settings.free_for_everyone:
        logger.info("Free access for everyone!")
        return LoggedEnum.FREE_ACCESS, None

    if free_access_code is not None and free_access_code in [
        x.get_secret_value() for x in logging_settings.free_access_codes
    ]:
        logger.info(f"Using free access code: {free_access_code}.")
        return LoggedEnum.FREE_ACCESS, None

    # TODO: Because we are initializing APIKeys (based on environment variables) in random places in the code, the user can not provide their own access keys, such as OPENAI_API_KEY.
    # Doing that would require to change the environment variables in the code, but Streamlit is using 1 thread per session, and the environment variables are shared between threads.
    # So other users would get the secrets provided by the first user!
    # Another option is to refactor the code, such that APIKeys are initialized in a single place, somewhere in the agent's initialisation and then, we can initialize them here based on the user's input and just provide them  to the agent.
    # After that's done, we should also have unique api keys per registered user.
    self_paying = False
    # self_paying = st.checkbox("I will provide my own access keys", value=False)

    if not self_paying:
        email = st.text_input("Email")
        password = SecretStr(st.text_input("Password", type="password"))
        logged_user = find_logged_user(email, password)

        if logged_user is not None:
            logger.info(f"Logged in as {email}.")
            return LoggedEnum.LOGGED_ACCESS, logged_user

        else:
            st.error("Invalid email or password.")
            st.stop()

    else:
        raise NotImplementedError(
            "Should not happen. Self-paying is not implemented yet. See the comment above."
        )
