#!/usr/bin/env python3
# ██╗███╗   ██╗███████╗██████╗  █████╗     ███████╗███╗   ███╗ ██████╗ ██╗  ██╗███████╗    ████████╗███████╗███████╗████████╗
# ██║████╗  ██║██╔════╝██╔══██╗██╔══██╗    ██╔════╝████╗ ████║██╔═══██╗██║ ██╔╝██╔════╝    ╚══██╔══╝██╔════╝██╔════╝╚══██╔══╝
# ██║██╔██╗ ██║█████╗  ██████╔╝███████║    ███████╗██╔████╔██║██║   ██║█████╔╝ █████╗         ██║   █████╗  ███████╗   ██║
# ██║██║╚██╗██║██╔══╝  ██╔══██╗██╔══██║    ╚════██║██║╚██╔╝██║██║   ██║██╔═██╗ ██╔══╝         ██║   ██╔══╝  ╚════██║   ██║
# ██║██║ ╚████║██║     ██║  ██║██║  ██║    ███████║██║ ╚═╝ ██║╚██████╔╝██║  ██╗███████╗       ██║   ███████╗███████║   ██║
# ╚═╝╚═╝  ╚═══╝╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝    ╚══════╝╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚══════╝       ╚═╝   ╚══════╝╚══════╝   ╚═╝
# DISCLAIMER: Please abstain from smoking before/during/after test execution.
# How to launch:
# 1. Navigate to the current file directory
# 2. $ pipenv --python 3.8
# 3. $ pipenv shell
# 4. $ pip install -r requirements.txt
# 5. $ python infra_smoke_test.py
# Runbook:
#     - Step: Health check request to farm.dfinity.systems: HEAD farm.dfinity.systems/dc (get data centers)
#     - Step: generating ssh_keys
#     - Step: generating VM config image file
#     - Step: getting active data centers from Farm (Farm API call)
#     - Step: creating group_name in Farm (Farm API call)
#     - Step: uploading image file to Farm (Farm API call)
#     - Step: creating VMs in Farm (Farm API call)
#     - Step: verifying that VMs are distributed across DCs
#     - Step: booting all VMs (Farm API call)
#     - Step: verifying current host can reach all VMs
#     - Step: generating inter-VMs networking matrices
#         - ssh into each VM
#             - check VM can download 1M file from each VM
#     - Cleanup: delete Farm group (and all VMs)
import argparse
import collections
import datetime
import json
import logging
import os
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
import traceback
from contextlib import contextmanager
from copy import deepcopy
from io import TextIOWrapper
from pathlib import Path
from typing import Callable
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

import paramiko
import requests


UNIVERSAL_VM_IMG_SHA256 = "f1880ad66ead02031264cb6da004f07468b0e6f07ba22bf44c42239eb6819fa5"
IMAGE_URL = f"http://download.proxy-global.dfinity.network:8080/farm/universal-vm/{UNIVERSAL_VM_IMG_SHA256}/x86_64-linux/universal-vm.img.zst"
CREATE_VM_IMAGE_SCRIPT_PATH = "../create-universal-vm-config-image.sh"
VM_NAME_BASE = "universal-vm-"
FARM_GROUP_PREFIX = "smoke_test"
FARM_HOSTNAME = "farm.dfinity.systems"
FARM_BASE_URL = f"https://{FARM_HOSTNAME}"
FARM_GROUP_TTL_SEC = 500  # TTL for the Farm group
HTTP_WITH_RETRIES_TIMEOUT_SEC = 60  # default timeout for http_with_retries()
HTTP_RETRY_DELAY_SEC = 10  # default retry interval for http_with_retries()
VM_BOOT_READINESS_TIMEOUT_SEC = 150  # max polling time for checking that VM is ready after boot
FILE_DOWNLOAD_TIMEOUT_SEC = 15  # used for downloading (CURLing) files between VMs
STDERR_NBYTES = 1024 * 1024
# Defines CI or local run.
CI_JOB_URL = os.getenv("CI_JOB_URL", default=None)
CI_COMMIT_SHA = os.getenv("CI_COMMIT_SHA", default="master")
file_full_path = os.path.realpath(__file__)
root_index = file_full_path.find("/rs/")
GITLAB_LINK = f"https://gitlab.com/dfinity-lab/public/ic/-/blob/{CI_COMMIT_SHA}{file_full_path[root_index:]}"
TMP_DIR_PREFIX = "smoke_test_artifacts_"
SLACK_ALERTS_FILE = "slack_alerts.json"
PFOPS_SLACK_CHANNEL = "#pfops-test-alerts"

RED = "\x1b[31m"
GREEN = "\x1b[32m"
YELLOW = "\x1b[33m"
BLUE = "\x1b[34m"
BOLD = "\x1b[1m"
MAGENTA = "\x1b[35m"
NC = "\x1b[0m"


class CustomFormatter(logging.Formatter):
    def __init__(self, fmt):
        super().__init__()
        self.FORMATS = {
            logging.DEBUG: GREEN + fmt + NC,
            logging.INFO: BOLD + BLUE + fmt + NC,
            logging.WARNING: BOLD + YELLOW + fmt + NC,
            logging.ERROR: BOLD + RED + fmt + NC,
        }

    def format(self, record):
        formatter = logging.Formatter(self.FORMATS.get(record.levelno))
        return formatter.format(record)


# Define format for logs
fmt = "%(asctime)s | %(levelname)8s | %(message)s"

# Create custom logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Create stdout handler for logging to the console
stdout_handler = logging.StreamHandler()
stdout_handler.setLevel(logging.DEBUG)
stdout_handler.setFormatter(CustomFormatter(fmt))


def add_file_logger(output_dir: str):
    today = datetime.date.today()
    file_handler = logging.FileHandler(f"{output_dir}/smoke_test_{today.strftime('%Y_%m_%d')}.log")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(fmt))
    logger.addHandler(file_handler)


logger.addHandler(stdout_handler)


@contextmanager
def step_span(step_name: str, step_idx: int):
    logger.info(f"Step {step_idx}: {step_name}")
    start = datetime.datetime.now()
    try:
        yield step_idx + 1
        duration = datetime.datetime.now() - start
        logger.info(f"Finished Step {step_idx} successfully in {str(duration)}.")
    except Exception as exception:
        duration = datetime.datetime.now() - start
        logger.error(f"Finished Step {step_idx} erroneously in {str(duration)}.")
        raise exception


class VM:
    def __init__(self, name: str, hostname: str, ipv6: str) -> None:
        self.name = name
        self.ipv6 = ipv6
        self.hostname = hostname


class NetworkingException(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class HttpWithRetriesException(Exception):
    def __init__(self, url: str, retries: int, status_code: int, last_error_message: str):
        self.url = url
        self.retries = retries
        self.status_code = status_code
        self.last_error_message = last_error_message
        super().__init__(
            f"Request to {self.url} failed {self.retries} times. Last failure code={status_code}, message={last_error_message}."
        )


def send_slack_alert(webhook_url: str, channel: str, message: str) -> requests.Response:
    response = requests.post(
        url=webhook_url,
        json={"text": message, "channel": channel},
        headers={"content-type": "application/json"},
    )
    if response.status_code == 200:
        logger.debug(f"Successfully sent slack message to channel={channel}.")
    else:
        logger.error(
            f"Failed to send slack message to channel={channel}, status_code={response.status_code}, error_message={response.text}."
        )
    return response


def send_slack_alerts_from_file(webhook_url: str, filename: str):
    with open(filename) as json_file:
        data = json.load(json_file)
    for channel in data["channels"]:
        send_slack_alert(webhook_url=webhook_url, channel=channel, message=data["message"])


def save_slack_error_to_file(filename: str, exception: Exception, slack_channels: List[str]):
    job_log_info = f". <{CI_JOB_URL}|log>" if CI_JOB_URL is not None else " during *manual* run"
    message = f":smoking_pipe-1959: <{GITLAB_LINK}|*Infra smoke test*> *failed* :x:{job_log_info}.\nException: ```{exception.__class__.__name__}('{exception}')```"
    json_string = {"channels": slack_channels, "message": message}
    with open(filename, "w") as outfile:
        json.dump(json_string, outfile)


@contextmanager
def farm_group():
    group_name = generate_default_group()
    http_with_retries(func=farm_create_group, expected_code=200, group_name=group_name)
    try:
        yield group_name
    finally:
        logger.debug(f"Deleting group_name={group_name} from Farm.")
        try:
            response = farm_delete_group(group_name)
            logger.debug(f"Group {group_name} deletion status {response.status_code}.")
        except Exception as e:
            logger.error(f"Failed to delete group {group_name}, err={e}")


@contextmanager
def artifacts_directory(keep_artifacts_dir: bool, output_dir: Optional[str]):
    # Create a tmp artifacts directory with a prefixed name.
    dir = tempfile.mkdtemp(prefix=TMP_DIR_PREFIX, dir=output_dir)
    try:
        yield dir
    finally:
        if not keep_artifacts_dir:
            try:
                shutil.rmtree(dir)
                logger.debug(f"Successfully deleted test artifacts {dir}.")
            except Exception:
                logger.error(f"Could not delete test artifacts {dir}.")
        else:
            logger.debug(f"Test artifacts are saved in {dir}.")


def http_with_retries(
    func: Callable[..., requests.Response], expected_code: int, timeout=HTTP_WITH_RETRIES_TIMEOUT_SEC, **kwargs
) -> requests.Response:
    start = datetime.datetime.now()
    retries = 0
    response = None
    last_exception = None
    while (datetime.datetime.now() - start).total_seconds() <= timeout:
        try:
            response = func(**kwargs)
            if response.status_code == expected_code:
                return response
            else:
                logger.debug(
                    f"Request to {response.url} failed with {response.status_code}: {response.text}. Retrying in {HTTP_RETRY_DELAY_SEC} sec ..."
                )
        except Exception as exception:
            # If e.g. connection can't be established, we keep retrying...
            logger.debug(f"Request failed with err={str(exception)}. Retrying in {HTTP_RETRY_DELAY_SEC} sec ...")
            last_exception = exception
        time.sleep(HTTP_RETRY_DELAY_SEC)
        retries += 1
    if response is None:
        raise Exception(f"Request failed after {retries} attempts, last err={str(last_exception)}")
    elif response.status_code != expected_code:
        raise HttpWithRetriesException(
            url=response.url,
            retries=retries - 1,
            status_code=response.status_code,
            last_error_message=response.text,
        )
    return response


def pretty_matrix(matrix_name: str, matrix: List[List[int]], vms: List[VM], is_colored: bool) -> str:
    def to_colored_digit(x: int):
        return f"{BOLD + GREEN}{x}{NC}" if x == 1 else f"{BOLD + RED}{x}{NC}"

    abbreviations = [vm.hostname[:3] for vm in vms]
    matrix_copy = deepcopy(matrix)
    table = []
    if is_colored:
        table.append(f"{NC}")
    table.extend([matrix_name, "   " + " ".join(abbreviations)])
    for i, x in enumerate(matrix_copy):
        if is_colored:
            table.extend([abbreviations[i] + " " + "   ".join([to_colored_digit(y) for y in x])])
        else:
            table.extend([abbreviations[i] + " " + "   ".join([str(y) for y in x])])
    for i in range(len(vms)):
        table.extend([f"{abbreviations[i]}: {vms[i].hostname}, {vms[i].ipv6}"])
    if is_colored:
        table.extend([f"{GREEN}1{NC} - success"])
        table.extend([f"{RED}0{NC} - failure"])
    else:
        table.extend(["1 - success"])
        table.extend(["0 - failure"])
    return "\n".join(table)


def generate_default_group() -> str:
    return f"{FARM_GROUP_PREFIX}-{socket.gethostname()}-{int(time.time())}"


def head_request_to_url(url: str) -> requests.Response:
    return requests.head(url)


def farm_get_data_centers() -> requests.Response:
    url = f"{FARM_BASE_URL}/dc"
    return requests.get(url)


def farm_get_groups() -> requests.Response:
    url = f"{FARM_BASE_URL}/group"
    return requests.get(url)


def farm_get_vms(group_name: str) -> requests.Response:
    url = f"{FARM_BASE_URL}/group/{group_name}/vm"
    return requests.get(url)


def farm_get_vm(group_name: str, vm_name: str) -> requests.Response:
    url = f"{FARM_BASE_URL}/group/{group_name}/vm/{vm_name}"
    return requests.get(url)


def farm_create_group(group_name: str) -> requests.Response:
    url = f"{FARM_BASE_URL}/group/{group_name}"
    body = {"spec": {"vmAllocation": "distributeAcrossDcs"}, "ttl": FARM_GROUP_TTL_SEC}
    return requests.post(url, json=body)


def farm_delete_group(group_name: str):
    url = f"{FARM_BASE_URL}/group/{group_name}"
    return requests.delete(url)


def farm_create_vm(group_name: str, vm_name: str) -> requests.Response:
    url = f"{FARM_BASE_URL}/group/{group_name}/vm/{vm_name}"
    body = {
        "type": "production",
        "vCPUs": 2,
        "memoryKiB": 25165824,
        "primaryImage": {
            "_tag": "imageViaUrl",
            "url": IMAGE_URL,
            "sha256": UNIVERSAL_VM_IMG_SHA256,
        },
        "hasIPv4": True,  # can be dropped when switch to fetching the nginx container from our docker registry
    }
    return requests.post(url, json=body)


def farm_upload_file(group_name: str, files: TextIOWrapper) -> requests.Response:
    url = f"{FARM_BASE_URL}/group/{group_name}/file"
    return requests.post(url, files=files)


def farm_mount_usb_drives(group_name: str, vm_name: str, images: List[Dict]) -> requests.Response:
    url = f"{FARM_BASE_URL}/group/{group_name}/vm/{vm_name}/drive-templates/usb-storage"
    body = {"drives": images}
    return requests.put(url, json=body)


def farm_start_vm(group_name: str, vm_name: str) -> requests.Response:
    url = f"{FARM_BASE_URL}/group/{group_name}/vm/{vm_name}/start"
    return requests.put(url)


def print_console_link(group_name: str, vm_name: str):
    logger.debug(f"{BOLD + MAGENTA}https://farm.dfinity.systems/group/{group_name}/vm/{vm_name}/console{NC}")


def is_vms_across_dc_distribution(vms: List[VM], dcs: collections.abc.KeysView) -> bool:
    def get_dc_from_hostname(hostname: str):
        return hostname.rsplit(sep=".")[1]

    found_dcs = set([get_dc_from_hostname(vm.hostname) for vm in vms])
    missing = set(dcs).difference(found_dcs)
    if missing:
        logger.error(f"No VMs were allocated to DCs: {missing}")
        return False
    return True


def prepare_config_image_file(config_dir: str) -> str:
    # Create activate file
    script = """#!/bin/sh
set -e
mkdir /tmp/web-root/
dd if=/dev/urandom of=/tmp/web-root/random bs=1024 count=1024
cd /tmp/web-root
sha256sum random > /tmp/web-root/SHA256SUMS
docker run \\
  -it --rm -d \\
  -p 80:80 \\
  --name web \\
  -v /tmp/web-root/:/usr/share/nginx/html \\
  registry.gitlab.com/dfinity-lab/open/public-docker-registry/nginx"""
    file_activate = f"{config_dir}/activate"
    with open(file_activate, "w") as f:
        f.write(script)
    st = os.stat(file_activate)
    os.chmod(file_activate, st.st_mode | stat.S_IEXEC)
    file_name = f"{config_dir}/image_output"
    command = [CREATE_VM_IMAGE_SCRIPT_PATH, "--input", config_dir, "--output", file_name]
    process = subprocess.run(command)
    if process.returncode != 0:
        raise Exception(f"Create image script {CREATE_VM_IMAGE_SCRIPT_PATH} failed with code={process.returncode}.")
    return file_name


def generate_config_and_ssh_keys(artifacts_dir: str) -> Tuple[str, str]:
    config_dir = f"{artifacts_dir}/config_dir"
    ssh_dir = f"{artifacts_dir}/ssh_keys"
    os.makedirs(config_dir, exist_ok=False)
    os.makedirs(ssh_dir, exist_ok=False)
    gen_key_command = ["ssh-keygen", "-t", "ed25519", "-N", "", "-f", f"{ssh_dir}/admin"]
    process = subprocess.run(gen_key_command)
    if process.returncode != 0:
        raise Exception(f"Generation of ssh keys failed with code={process.returncode}")
    os.makedirs(f"{config_dir}/ssh-authorized-keys", exist_ok=False)
    os.rename(f"{ssh_dir}/admin.pub", f"{config_dir}/ssh-authorized-keys/admin")
    return config_dir, ssh_dir


def boot_vm(group_name: str, vm_name: str, image_id: str) -> requests.Response:
    response = http_with_retries(
        func=farm_mount_usb_drives,
        expected_code=200,
        group_name=group_name,
        vm_name=vm_name,
        images=[{"_tag": "imageViaId", "id": image_id}],
    )
    logger.debug(f"Mount image response {response.status_code}.")
    response = http_with_retries(func=farm_start_vm, expected_code=200, group_name=group_name, vm_name=vm_name)
    logger.debug(f"Start VM response {response.status_code}")
    print_console_link(group_name, vm_name)
    return response


def generate_connectivity_matrices(VMs: List[VM], key_filename: str) -> List[List[int]]:
    N = len(VMs)
    # 1: success, 0: failure.
    file_download_matrix = [[0 for _ in range(N)] for _ in range(N)]
    for row in range(N):
        logger.debug(f"Running iteration {row+1} of {N} ...")
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(VMs[row].ipv6, username="admin", key_filename=key_filename)
        for col in range(N):
            # Get 1M file download result.
            channel = client.get_transport().open_session()
            channel.exec_command(
                f"curl --no-progress-meter --verbose --max-time {FILE_DOWNLOAD_TIMEOUT_SEC} http://[{VMs[col].ipv6}]/random -o random --fail && "
                f"curl --no-progress-meter --verbose --max-time {FILE_DOWNLOAD_TIMEOUT_SEC} http://[{VMs[col].ipv6}]/SHA256SUMS -o SHA256SUMS --fail && "
                f"sha256sum -c SHA256SUMS"
            )
            exit_status = channel.recv_exit_status()
            if exit_status != 0:
                logger.error(
                    f"Failure: curl from {VMs[row].ipv6} ({VMs[row].hostname[:3]}) to {VMs[col].ipv6} ({VMs[col].hostname[:3]}) (timeout {FILE_DOWNLOAD_TIMEOUT_SEC}) failed with code={exit_status}, stderr={channel.recv_stderr(STDERR_NBYTES).decode('utf-8')}"
                )
            file_download_matrix[row][col] = int(exit_status == 0)
        client.close()
    return file_download_matrix


def exception_handler(func):
    def test(keep_artifacts_dir: bool, output_dir: Optional[str], **kwargs):
        test_exit_code = 1  # initially set to failed.
        # Use context for cleanup: optionally remove artifacts_dir after execution.
        with artifacts_directory(keep_artifacts_dir, output_dir) as artifacts_dir:
            logger.debug(f"Test output artifacts will be stored in {artifacts_dir}")
            # Log file is stored in the artifacts_dir.
            add_file_logger(artifacts_dir)
            try:
                test_exit_code = func(artifacts_dir)
            except Exception as exc:
                # Log exception with a stack trace.
                logger.error(traceback.format_exc())
                # Save slack failure message in artifacts_dir.
                save_slack_error_to_file(
                    filename=f"{artifacts_dir}/{SLACK_ALERTS_FILE}", exception=exc, slack_channels=[PFOPS_SLACK_CHANNEL]
                )
                if kwargs["with_slack_alerts"]:
                    send_slack_alerts_from_file(
                        webhook_url=kwargs["slack_webhook_url"], filename=f"{artifacts_dir}/{SLACK_ALERTS_FILE}"
                    )
        return test_exit_code

    return test


def test_with_farm_group(group_name: str, artifacts_dir: str, step_idx: int) -> int:
    with step_span("generating ssh_keys", step_idx) as step_idx:
        config_dir, ssh_dir = generate_config_and_ssh_keys(artifacts_dir)

    with step_span("generating VM config image file", step_idx) as step_idx:
        image_file = prepare_config_image_file(config_dir)

    with step_span("getting active data centers from Farm", step_idx) as step_idx:
        response = http_with_retries(func=farm_get_data_centers, expected_code=200)
        dc_names = response.json().keys()
        logger.info(f"Found active data centers: {dc_names}.")

    with step_span("uploading image file to Farm", step_idx) as step_idx:
        with open(image_file, "rb") as image:
            response = http_with_retries(
                func=farm_upload_file, expected_code=200, group_name=group_name, files={"image": image}
            )
        image_id = response.json()["fileIds"]["image"]

    with step_span(f"checking existing groups in Farm with {FARM_GROUP_PREFIX} prefix", step_idx) as step_idx:
        response = http_with_retries(func=farm_get_groups, expected_code=200)
        groups = response.json()
        for g in groups:
            if g["name"] == group_name:
                logger.debug(f"Newly created group: {g['name']} expires_at: {g['expiresAt']}")
            elif FARM_GROUP_PREFIX in g["name"]:
                logger.debug(f"Existing {FARM_GROUP_PREFIX} groups: {g['name']} expires_at: {g['expiresAt']}")

    with step_span("creating VMs in Farm", step_idx) as step_idx:
        VMs = []
        for idx in range(len(dc_names)):
            vm_name = f"{VM_NAME_BASE}{idx}"
            response = http_with_retries(func=farm_create_vm, expected_code=200, group_name=group_name, vm_name=vm_name)
            resp_body = response.json()
            VMs.append(VM(vm_name, resp_body["hostname"], resp_body["ipv6"]))
            logger.debug(
                f"VM name={VMs[-1].name}, hostname={VMs[-1].hostname}, ipv6={VMs[-1].ipv6} created successfully."
            )
        # Sort VMs by hostname, so that networking matrices computed below always have the same ordering.
        VMs.sort(key=lambda x: x.hostname)
        logger.info(f"All {len(VMs)} VMs created successfully.")

    with step_span("verifying VMs across DCs distribution", step_idx) as step_idx:
        is_vm_per_dc = is_vms_across_dc_distribution(vms=VMs, dcs=dc_names)
        if not is_vm_per_dc:
            raise Exception("VMs are not distributed among all DCs.")
        logger.info(f"All {len(dc_names)} DCs contain a VM.")

    with step_span("booting all VMs", step_idx) as step_idx:
        for vm in VMs:
            boot_vm(group_name, vm.name, image_id)
        logger.info(f"All {len(VMs)} VMs were booted successfully.")

    with step_span(f"verifying {socket.gethostname()} can reach all VMs", step_idx) as step_idx:
        for vm in VMs:
            try:
                http_with_retries(
                    func=head_request_to_url,
                    expected_code=200,
                    timeout=VM_BOOT_READINESS_TIMEOUT_SEC,
                    url=f"http://[{vm.ipv6}]/random",
                )
            except Exception:
                raise NetworkingException(
                    f"VM name={vm.name}, hostname={vm.hostname} can't be reached from the host {socket.gethostname()} after booting."
                )
            logger.debug(f"vm={vm.name} ipv6 is reachable.")
            logger.debug(f"ssh admin@{vm.ipv6} -i {ssh_dir}/admin")

    with step_span("generating inter-vms networking matrices", step_idx) as step_idx:
        # Check VMs can download 1M file from each other.
        file_download_matrix = generate_connectivity_matrices(VMs, f"{ssh_dir}/admin")
        logger.debug(pretty_matrix("Inter-VMs file download matrix:", file_download_matrix, VMs, True))
        all_vms_file_download_success = all(all(x) for x in file_download_matrix)
        if not all_vms_file_download_success:
            slack_matrix = pretty_matrix("Inter-VMs file download matrix:", file_download_matrix, VMs, False)
            raise NetworkingException(f"Not all VMs can download files from each other.\n{slack_matrix}")
        logger.info("All VMs can download files from each other.")
    return 0


@exception_handler
def smoke_test(artifacts_dir: str) -> int:
    step_idx = 1

    with step_span(f"Execute Farm health check request: HEAD {FARM_BASE_URL}/dc", step_idx) as step_idx:
        try:
            http_with_retries(func=head_request_to_url, expected_code=200, url=f"{FARM_BASE_URL}/dc")
        except Exception:
            raise NetworkingException(f"HEAD request to {FARM_BASE_URL}/dc failed, Farm is unreachable.")

    with farm_group() as group_name:
        return test_with_farm_group(group_name, artifacts_dir, step_idx)


if __name__ == "__main__":
    # Set path to the current script path (in case script is launched from non-parent dir).
    current_path = Path(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(current_path.absolute())
    # Get slack token from the env variable.
    slack_webhook_url = os.environ.get("SLACK_WEBHOOK_URL", None)
    # Parse command line arguments.
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--keep_artifacts_dir",
        action="store_true",
        help="Keep dir containing: log file/s, ssh keys, alert messages, etc.",
    )
    parser.add_argument("--with_slack_alerts", action="store_true", help="Send slack alerts in case of test failure.")
    parser.add_argument("--output_dir", type=str, help="Artifacts output directory.")
    args = parser.parse_args()
    output_dir = os.getenv("TMPDIR", None)
    if args.output_dir:
        output_dir = args.output_dir
    if not args.with_slack_alerts:
        logger.warning("Slack alerts are turned off. Use --with_slack_alerts flag to send alerts.")
    elif slack_webhook_url is None:
        raise Exception("No slack webhook url defined, alerts can't be sent.")
    if not args.keep_artifacts_dir:
        logger.warning(
            "All test artifacts will be deleted after test execution. Use --keep_artifacts_dir to keep them."
        )
    # Start the test.
    start = datetime.datetime.now()
    test_exit_code = smoke_test(
        output_dir=output_dir,
        keep_artifacts_dir=args.keep_artifacts_dir,
        with_slack_alerts=args.with_slack_alerts,
        slack_webhook_url=slack_webhook_url,
    )
    test_duration = datetime.datetime.now() - start
    if test_exit_code == 0:
        logger.info(f"Smoke test succeeded after {str(test_duration)}.")
    else:
        logger.error(f"Smoke test failed after {str(test_duration)}.")
    sys.exit(test_exit_code)
