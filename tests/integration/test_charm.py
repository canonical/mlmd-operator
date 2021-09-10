import logging
import os
import subprocess
from pathlib import Path
import pytest
import yaml
from pytest_operator.plugin import OpsTest

log = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest):
    built_charm_path = await ops_test.build_charm(".")
    log.info(f"Built charm {built_charm_path}")

    image_path = METADATA["resources"]["oci-image"]["upstream-source"]
    resources = {"oci-image": image_path}

    await ops_test.model.deploy(
        entity_url=built_charm_path,
        resources=resources,
    )
    await ops_test.model.wait_for_idle(timeout=60 * 60)


async def test_using_charm(ops_test: OpsTest, tmp_path: Path):
    """
    Test mlmd through basic interactions
    """
    script_abs_path = Path("tests/integration/data/interact_with_mlmd.sh").absolute()

    logging.info(f"Using temporary directory {tmp_path}")
    logging.info(f"cwd = {os.getcwd()}")
    logging.info(f"script_abs_path = {script_abs_path}")
    subprocess.run([script_abs_path, ops_test.model_name], cwd=tmp_path, check=True)
