# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock, patch

import pytest
from ops.model import ActiveStatus, WaitingStatus
from ops.testing import Harness

from charm import GRPC_SVC_NAME, RELATION_NAME, Operator

CONTAINER_NAME = "mlmd-grpc-server"
SERVICE_NAME = "mlmd"


def test_log_forwarding(harness, mocked_lightkube_client):
    """Test LogForwarder initialization."""
    with patch("charm.LogForwarder") as mock_logging:
        harness.begin()
        mock_logging.assert_called_once_with(charm=harness.charm)


def test_not_leader(
    harness,
    mocked_lightkube_client,
):
    """Test that charm waits for leadership."""
    harness.begin_with_initial_hooks()
    assert harness.charm.model.unit.status == WaitingStatus(
        "[leadership-gate] Waiting for leadership"
    )


def test_grpc_relation_with_data(harness, mocked_lightkube_client):
    """Test the relation data has values by default as the charm is broadcasting them."""
    harness.set_leader(True)
    harness.begin()

    rel_id = harness.add_relation(RELATION_NAME, "app")
    rel_data = harness.model.get_relation(RELATION_NAME, rel_id).data[harness.model.app]

    # The GRPC port from the default config and the GRPC_SVC_NAME set in the charm code
    # are the expected values of this test case
    expected = {"port": harness.model.config["port"], "name": GRPC_SVC_NAME}
    assert rel_data["port"] == expected["port"]
    assert rel_data["name"] == expected["name"]


def test_grpc_relation_with_data_when_data_changes(
    harness,
    mocked_lightkube_client,
):
    """Test the relation data on config changed events."""
    harness.set_leader(True)
    # Change the configuration option before starting harness so
    # the correct values are passed to the K8sServiceInfo lib
    # FIXME: the correct behaviour should be to change the config
    # at any point in time to trigger config events and check the
    # value gets passed correctly when it changes.
    harness.update_config({"port": "9090"})
    harness.begin()

    # Initialise a k8s-service requirer charm
    harness.charm.leadership_gate.get_status = MagicMock(return_value=ActiveStatus())
    harness.charm.kubernetes_resources.get_status = MagicMock(return_value=ActiveStatus())

    # Add relation between the requirer charm and this charm (mlmd)
    provider_rel_id = harness.add_relation(relation_name=RELATION_NAME, remote_app="other-app")
    provider_rel_data = harness.get_relation_data(
        relation_id=provider_rel_id, app_or_unit=harness.charm.app.name
    )

    # Change the port of the service and check the value changes
    assert provider_rel_data["port"] == harness.model.config["port"]


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


def test_pebble_service_container_running(harness, mocked_lightkube_client):
    """Test that the pebble service of the charm's mlmd-grpc-server container is running."""
    harness.set_leader(True)
    harness.begin()
    harness.set_can_connect(CONTAINER_NAME, True)

    harness.charm.kubernetes_resources.get_status = MagicMock(return_value=ActiveStatus())
    harness.charm.chown_component.get_status = MagicMock(return_value=ActiveStatus())

    harness.charm.on.install.emit()

    assert isinstance(harness.charm.unit.status, ActiveStatus)

    container = harness.charm.unit.get_container(CONTAINER_NAME)
    # Assert that sidecar container is up and its service is running
    assert container.get_service(SERVICE_NAME).is_running()


def test_install_before_pebble_service_container(harness, mocked_lightkube_client):
    """Test that charm waits when install event happens before pebble-service-container is ready."""
    harness.set_leader(True)
    harness.begin()

    harness.charm.kubernetes_resources.get_status = MagicMock(return_value=ActiveStatus())
    harness.charm.chown_component.get_status = MagicMock(return_value=ActiveStatus())

    harness.charm.on.install.emit()

    # Assert charm is waiting on PebbleComponent
    assert harness.charm.model.unit.status == WaitingStatus(
        "[mlmd-grpc-service] Waiting for Pebble to be ready."
    )


@pytest.fixture()
def harness(mocked_kubernetes_service_patch):
    return Harness(Operator)


@pytest.fixture()
def mocked_kubernetes_service_patch(mocker):
    """Mocks the KubernetesServicePatch for the charm."""
    mocked_kubernetes_service_patch = mocker.patch(
        "charm.KubernetesServicePatch", lambda *_, **__: None
    )
    yield mocked_kubernetes_service_patch


@pytest.fixture()
def mocked_lightkube_client(mocker):
    """Mocks the Lightkube Client in charm.py, returning a mock instead."""
    mocked_lightkube_client = MagicMock()
    mocker.patch("charm.lightkube.Client", return_value=mocked_lightkube_client)
    yield mocked_lightkube_client
