# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Define Interface tests fixtures."""

import pytest
from interface_tester.plugin import InterfaceTester

from charm import Operator


@pytest.fixture(autouse=True)
def patch_kubernetes_service_patch(mocker):
    """Patch KubernetesServicePatch to avoid actual Kubernetes interactions."""
    mocker.patch("charm.KubernetesServicePatch")


@pytest.fixture
def interface_tester(interface_tester: InterfaceTester):
    """Fixture to configure the interface tester for Operator charms."""
    interface_tester.configure(charm_type=Operator)
    yield interface_tester
