#!/usr/bin/env python3
# Copyright 2025 Canonical
# See LICENSE file for licensing details.

import logging

from charmed_kubeflow_chisme.components.component import Component
from charmed_kubeflow_chisme.exceptions import ErrorWithStatus
from ops import ActiveStatus, CharmBase, StatusBase, WaitingStatus

logger = logging.getLogger(__name__)


class ChownMountedStorageComponent(Component):
    """A component that ensures mounted storage is owned by the user that runs the service.

    Args:
        charm(CharmBase): this charm
        name(str): name of the component
        storage_path(str): the path where the storage is mounted and is desired to change owners.
        workload_user(str): the user that runs the service (workload).
        workload_container(str): the name of the workload container where the changes must be done.
    """

    def __init__(
        self,
        charm: CharmBase,
        name: str,
        storage_path: str,
        workload_user: str,
        workload_container: str,
    ):
        super().__init__(charm, name)

        self.storage_path = storage_path
        self.workload_user = workload_user
        self.workload_container = workload_container
        self.charm = charm

    def chown_storage_path(self, storage_path, workload_user) -> None:
        container = self.charm.unit.get_container(self.workload_container)
        if not container.can_connect():
            raise ErrorWithStatus("Cannot connect to container mlmd-grpc-server", WaitingStatus)
        container.exec(["chown", f"{workload_user}:{workload_user}", f"{storage_path}"]).wait()

    def get_status(self) -> StatusBase:
        try:
            self.chown_storage_path(self.storage_path, self.workload_user)
        except ErrorWithStatus as e:
            return WaitingStatus(
                "Cannot chown the storage path, waiting for container to be ready", e.status
            )
        return ActiveStatus()
