# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import os
import subprocess
from pathlib import Path

import pytest
import tenacity
import yaml
from charmed_kubeflow_chisme.testing import (
    GRAFANA_AGENT_APP,
    assert_logging,
    assert_security_context,
    deploy_and_assert_grafana_agent,
    generate_container_securitycontext_map,
    get_pod_names,
)
from lightkube import Client
from pytest_operator.plugin import OpsTest

log = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
CONTAINERS_SECURITY_CONTEXT_MAP = generate_container_securitycontext_map(METADATA)


@pytest.fixture(scope="session")
def lightkube_client() -> Client:
    """Returns lightkube Kubernetes client"""
    client = Client(field_manager=f"{APP_NAME}")
    return client


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest):
    built_charm_path = await ops_test.build_charm(".")
    log.info(f"Built charm {built_charm_path}")

    image_path = METADATA["resources"]["oci-image"]["upstream-source"]
    resources = {"oci-image": image_path}

    await ops_test.model.deploy(
        entity_url=built_charm_path,
        resources=resources,
        trust=True,
    )
    await ops_test.model.wait_for_idle(timeout=60 * 60)

    # Deploying grafana-agent-k8s and add all relations
    await deploy_and_assert_grafana_agent(
        ops_test.model, APP_NAME, metrics=False, dashboard=False, logging=True
    )


async def test_logging(ops_test: OpsTest):
    """Test logging is defined in relation data bag."""
    app = ops_test.model.applications[GRAFANA_AGENT_APP]
    await assert_logging(app)


@tenacity.retry(
    wait=tenacity.wait_exponential(multiplier=1, min=1, max=15),
    stop=tenacity.stop_after_delay(30),
    reraise=True,
)
async def test_using_charm(ops_test: OpsTest, tmp_path: Path):
    """
    Test mlmd through basic interactions
    """
    script_abs_path = Path("tests/integration/data/interact_with_mlmd.sh").absolute()

    logging.info(f"Using temporary directory {tmp_path}")
    logging.info(f"cwd = {os.getcwd()}")
    logging.info(f"script_abs_path = {script_abs_path}")

    subprocess.run([script_abs_path, ops_test.model_name], cwd=tmp_path, check=True)


@pytest.mark.parametrize("container_name", list(CONTAINERS_SECURITY_CONTEXT_MAP.keys()))
async def test_container_security_context(
    ops_test: OpsTest,
    lightkube_client: Client,
    container_name: str,
):
    """Test container security context is correctly set.

    Verify that container spec defines the security context with correct
    user ID and group ID.
    """
    pod_name = get_pod_names(ops_test.model.name, APP_NAME)[0]
    assert_security_context(
        lightkube_client,
        pod_name,
        container_name,
        CONTAINERS_SECURITY_CONTEXT_MAP,
        ops_test.model.name,
    )
