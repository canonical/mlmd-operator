# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import pytest
from ops.model import ActiveStatus, BlockedStatus
from ops.testing import Harness

from charm import Operator


@pytest.fixture
def harness():
    return Harness(Operator)


def test_not_leader(harness):
    harness.begin_with_initial_hooks()
    assert harness.charm.model.unit.status == ActiveStatus("")


def test_missing_image(harness):
    harness.set_leader(True)
    harness.begin_with_initial_hooks()
    assert harness.charm.model.unit.status == BlockedStatus("Missing resource: oci-image")


def test_no_relation(harness):
    harness.set_leader(True)
    harness.add_oci_resource(
        "oci-image",
        {
            "registrypath": "ci-test",
            "username": "",
            "password": "",
        },
    )
    harness.begin_with_initial_hooks()

    assert harness.charm.model.unit.status == ActiveStatus("")


def test_one_relation(harness):
    harness.set_leader(True)
    harness.add_oci_resource(
        "oci-image",
        {
            "registrypath": "ci-test",
            "username": "",
            "password": "",
        },
    )
    rel_id = harness.add_relation("mysql", "mysql")
    harness.add_relation_unit(rel_id, "mysql/0")
    harness.update_relation_data(
        rel_id,
        "mysql/0",
        {
            "database": "unit-db",
            "host": "unit-host",
            "port": "unit-port",
            "user": "unit-user",
            "password": "unit-password",
            "root_password": "unit-root",
        },
    )

    harness.begin_with_initial_hooks()

    pod_spec, _ = harness.get_pod_spec()

    assert pod_spec["containers"][0]["args"] == [
        "--mysql_config_database=unit-db",
        "--mysql_config_host=unit-host",
        "--mysql_config_port=unit-port",
        "--mysql_config_user=unit-user",
        "--mysql_config_password=unit-password",
        "--grpc_port=8080",
        "--enable_database_upgrade=true",
    ]

    assert harness.charm.model.unit.status == ActiveStatus("")
