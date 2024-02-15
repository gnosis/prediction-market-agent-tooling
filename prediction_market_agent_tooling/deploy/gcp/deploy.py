import os
import shutil
import subprocess
import tempfile
import typing as t

import requests
from cron_validator import CronValidator

from prediction_market_agent_tooling.deploy.gcp.utils import (
    gcloud_create_topic_cmd,
    gcloud_delete_function_cmd,
    gcloud_delete_topic_cmd,
    gcloud_deploy_cmd,
    gcloud_schedule_cmd,
    get_gcloud_function_uri,
    get_gcloud_id_token,
)
from prediction_market_agent_tooling.tools.utils import export_requirements_from_toml


def deploy_to_gcp(
    gcp_fname: str,
    function_file: str,
    requirements_file: t.Optional[str],
    extra_deps: list[str],
    labels: dict[str, str] | None,
    env_vars: dict[str, str] | None,
    secrets: dict[str, str] | None,
    memory: int,  # in MB
) -> str:
    if requirements_file and not os.path.exists(requirements_file):
        raise ValueError(f"File {requirements_file} does not exist")

    if not os.path.exists(function_file):
        raise ValueError(f"File {function_file} does not exist")

    # Make a tempdir to store the requirements file and the function
    with tempfile.TemporaryDirectory() as tempdir:
        # Copy function_file to tempdir/main.py
        shutil.copy(function_file, f"{tempdir}/main.py")

        # If the file is a .toml file, convert it to a requirements.txt file
        if requirements_file is None:
            # Just create an empty file.
            with open(f"{tempdir}/requirements.txt", "w"):
                pass
        elif requirements_file.endswith(".toml"):
            export_requirements_from_toml(output_dir=tempdir)
        else:
            shutil.copy(requirements_file, f"{tempdir}/requirements.txt")

        if extra_deps:
            with open(f"{tempdir}/requirements.txt", "a") as f:
                for dep in extra_deps:
                    f.write(f"{dep}\n")

        # Create the topic used to trigger the function. Note we use the
        # convention that the topic name is the same as the function name
        subprocess.run(gcloud_create_topic_cmd(gcp_fname), shell=True)

        # Deploy the function
        cmd = gcloud_deploy_cmd(
            gcp_function_name=gcp_fname,
            source=tempdir,
            entry_point="main",  # TODO check this function exists in main.py
            labels=labels,
            env_vars=env_vars,
            secrets=secrets,
            memory=memory,
        )
        subprocess.run(cmd, shell=True)
        # TODO test the depolyment without placing a bet

    return gcp_fname


def schedule_deployed_gcp_function(function_name: str, cron_schedule: str) -> None:
    # Validate the cron schedule
    if not CronValidator().parse(cron_schedule):
        raise ValueError(f"Invalid cron schedule {cron_schedule}")

    cmd = gcloud_schedule_cmd(function_name=function_name, cron_schedule=cron_schedule)
    subprocess.run(cmd, shell=True)


def run_deployed_gcp_function(function_name: str) -> requests.Response:
    uri = get_gcloud_function_uri(function_name)
    header = {"Authorization": f"Bearer {get_gcloud_id_token()}"}
    return requests.post(uri, headers=header)


def remove_deployed_gcp_function(function_name: str) -> None:
    subprocess.run(gcloud_delete_function_cmd(function_name), shell=True)
    subprocess.run(gcloud_delete_topic_cmd(function_name), shell=True)
