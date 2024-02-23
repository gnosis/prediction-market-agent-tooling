import subprocess
import sys

from google.cloud.functions_v2.services.function_service.client import (
    FunctionServiceClient,
)
from google.cloud.functions_v2.types.functions import Function


def gcloud_deploy_cmd(
    gcp_function_name: str,
    source: str,
    entry_point: str,
    labels: dict[str, str] | None,
    env_vars: dict[str, str] | None,
    secrets: dict[str, str] | None,
    memory: int,  # in MB
    timeout: int = 180,
    retry_on_failure: bool = False,
) -> str:
    cmd = (
        f"gcloud functions deploy {gcp_function_name} "
        f"--runtime {get_gcloud_python_runtime_str()} "
        f"--trigger-topic {gcp_function_name} "
        f"--gen2 "
        f"--region {get_gcloud_region()} "
        f"--source {source} "
        f"--entry-point {entry_point} "
        f"--memory {memory}MB "
        f"--no-allow-unauthenticated "
        f"--timeout {timeout}s "
        # Explicitly set no concurrency, min instances to 0 (agent is executed only once in a while) and max instances to 1 (parallel agents aren't allowed).
        "--concurrency 1 "
        "--min-instances 0 "
        "--max-instances 1 "
    )
    if retry_on_failure:
        cmd += "--retry "
    if labels:
        for k, v in labels.items():
            cmd += f"--update-labels {k}={v} "
    if env_vars:
        for k, v in env_vars.items():
            cmd += f"--set-env-vars {k}={v} "
    if secrets:
        for k, v in secrets.items():
            cmd += f"--set-secrets {k}={v} "

    return cmd


def gcloud_schedule_cmd(function_name: str, cron_schedule: str) -> str:
    return (
        f"gcloud scheduler jobs create pubsub {function_name} "
        f"--schedule '{cron_schedule}' "
        f"--topic {function_name} "
        f"--location {get_gcloud_region()} "
        "--message-body '{}' "
    )


def gcloud_delete_function_cmd(fname: str) -> str:
    return f"gcloud functions delete {fname} --region={get_gcloud_region()} --quiet"


def gcloud_create_topic_cmd(topic_name: str) -> str:
    return f"gcloud pubsub topics create {topic_name}"


def gcloud_delete_topic_cmd(topic_name: str) -> str:
    return f"gcloud pubsub topics delete {topic_name}"


def get_gcloud_project_id() -> str:
    return (
        subprocess.run(
            "gcloud config get-value project",
            shell=True,
            capture_output=True,
            check=True,
        )
        .stdout.decode()
        .strip()
    )


def get_gcloud_parent() -> str:
    return f"projects/{get_gcloud_project_id()}/locations/{get_gcloud_region()}"


def get_gcloud_id_token() -> str:
    return (
        subprocess.run(
            "gcloud auth print-identity-token",
            shell=True,
            capture_output=True,
            check=True,
        )
        .stdout.decode()
        .strip()
    )


def get_gcloud_region() -> str:
    return "europe-west2"  # London


def get_gcloud_python_runtime_str() -> str:
    return f"python{sys.version_info.major}{sys.version_info.minor}"


def get_gcloud_function_uri(function_name: str) -> str:
    return (
        subprocess.run(
            f"gcloud functions describe {function_name} --region {get_gcloud_region()} --format='value(url)'",
            shell=True,
            capture_output=True,
            check=True,
        )
        .stdout.decode()
        .strip()
    )


def api_keys_to_str(api_keys: dict[str, str]) -> str:
    return " ".join([f"{k}={v}" for k, v in api_keys.items()])


def get_gcp_function(fname: str) -> Function:
    client = FunctionServiceClient()
    response = client.list_functions(parent=get_gcloud_parent())
    for function in response:
        if function.name.split("/")[-1] == fname:
            return function

    fnames = [f.name.split("/")[-1] for f in response]
    raise ValueError(f"Function {fname} not found in function list {fnames}")


def gcp_function_is_active(fname: str) -> bool:
    return get_gcp_function(fname).state == Function.State.ACTIVE
