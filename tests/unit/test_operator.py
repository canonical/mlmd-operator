# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock, patch

import pytest
from ops.model import ActiveStatus, WaitingStatus
from ops.testing import Harness

from charm import GRPC_SVC_NAME, RELATION_NAME, Operator

CONTAINER_NAME = "mlmd-grpc-server"
MOCK_GRPC_DATA = {"service": "service-name", "port": "1234"}
SERVICE_NAME = "mlmd"


@patch("charm.KubernetesServicePatch", lambda *_, **__: None)
def test_not_leader(
    harness,
    mocked_lightkube_client,
):
    """Test that charm waits for leadership."""
    harness.begin_with_initial_hooks()
    assert harness.charm.model.unit.status == WaitingStatus(
        "[leadership-gate] Waiting for leadership"
    )


@patch("charm.KubernetesServicePatch", lambda *_, **__: None)
def test_grpc_relation_with_data(harness, mocked_lightkube_client):
    harness.set_leader(True)
    harness.begin()

    rel_id = harness.add_relation(RELATION_NAME, "app")
    rel_data = harness.model.get_relation(RELATION_NAME, rel_id).data[harness.model.app]

    # The GRPC port from the default config and the GRPC_SVC_NAME set in the charm code
    # are the expected values of this test case
    expected = {"port": harness.model.config["port"], "name": GRPC_SVC_NAME}
    assert rel_data["port"] == expected["port"]
    assert rel_data["name"] == expected["name"]


@patch("charm.KubernetesServicePatch", lambda *_, **__: None)
def test_kubernetes_component_created(harness, mocked_lightkube_client):
    """Test that Kubernetes component is created when we have leadership."""
    # Needed because the kubernetes component will only apply to k8s if we are the leader
    harness.set_leader(True)
    harness.begin()

    # Need to mock the leadership-gate to be active, and the kubernetes auth component so that it
    # sees the expected resources when calling _get_missing_kubernetes_resources
    kubernetes_resources = harness.charm.kubernetes_resources
    kubernetes_resources.component._get_missing_kubernetes_resources = MagicMock(return_value=[])

    harness.charm.on.install.emit()

    assert isinstance(harness.charm.kubernetes_resources.status, ActiveStatus)

    # Assert that expected amount of apply calls were made
    # This simulates the Kubernetes resources being created
    assert mocked_lightkube_client.apply.call_count == 1


@patch("charm.KubernetesServicePatch", lambda *_, **__: None)
def test_pebble_service_container_running(harness, mocked_lightkube_client):
    """Test that the pebble service of the charm's mlmd-grpc-server container is running."""
    harness.set_leader(True)
    harness.begin()
    harness.set_can_connect(CONTAINER_NAME, True)

    harness.charm.kubernetes_resources.get_status = MagicMock(return_value=ActiveStatus())

    harness.charm.on.install.emit()

    assert isinstance(harness.charm.unit.status, ActiveStatus)

    container = harness.charm.unit.get_container(CONTAINER_NAME)
    # Assert that sidecar container is up and its service is running
    assert container.get_service(SERVICE_NAME).is_running()


@patch("charm.KubernetesServicePatch", lambda *_, **__: None)
def test_install_before_pebble_service_container(harness, mocked_lightkube_client):
    """Test that charm waits when install event happens before pebble-service-container is ready."""
    harness.set_leader(True)
    harness.begin()

    harness.charm.kubernetes_resources.get_status = MagicMock(return_value=ActiveStatus())

    harness.charm.on.install.emit()

    # Assert charm is waiting on PebbleComponent
    assert harness.charm.model.unit.status == WaitingStatus(
        "[mlmd-grpc-service] Waiting for Pebble to be ready."
    )


@pytest.fixture
def harness():
    return Harness(Operator)


@pytest.fixture()
def mocked_lightkube_client(mocker):
    """Mocks the Lightkube Client in charm.py, returning a mock instead."""
    mocked_lightkube_client = MagicMock()
    mocker.patch("charm.lightkube.Client", return_value=mocked_lightkube_client)
    yield mocked_lightkube_client
