#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

import lightkube
from charmed_kubeflow_chisme.components import (
    CharmReconciler,
    LazyContainerFileTemplate,
    LeadershipGateComponent,
)
from charmed_kubeflow_chisme.components.kubernetes_component import KubernetesComponent
from charmed_kubeflow_chisme.kubernetes import create_charm_default_labels
from charms.loki_k8s.v1.loki_push_api import LogForwarder
from charms.mlops_libs.v0.k8s_service_info import KubernetesServiceInfoProvider
from charms.observability_libs.v1.kubernetes_service_patch import KubernetesServicePatch
from charms.velero_libs.v0.velero_backup_config import VeleroBackupRequirer, VeleroBackupSpec
from lightkube.models.core_v1 import ServicePort
from lightkube.resources.core_v1 import Service
from ops import main
from ops.charm import CharmBase

from components.chown_component import ChownMountedStorageComponent
from components.pebble_components import MlmdPebbleService

logger = logging.getLogger()

GRPC_SVC_NAME = "metadata-grpc-service"
K8S_RESOURCE_FILES = ["src/templates/ml-pipeline-service.yaml.j2"]
RELATION_NAME = "grpc"
SQLITE_CONFIG_PROTO_DESTINATION = "/config/config.proto"
SQLITE_CONFIG_PROTO = 'connection_config: {sqlite: {filename_uri: "file:/data/mlmd.db"}}'


class Operator(CharmBase):
    """Charm for the ML Metadata GRPC Server."""

    def __init__(self, *args):
        super().__init__(*args)

        # Charm logic
        self.charm_reconciler = CharmReconciler(self)
        self._svc_grpc_port = self.config["port"]

        self.leadership_gate = self.charm_reconciler.add(
            component=LeadershipGateComponent(
                charm=self,
                name="leadership-gate",
            ),
            depends_on=[],
        )

        self.kubernetes_resources = self.charm_reconciler.add(
            component=KubernetesComponent(
                charm=self,
                name="kubernetes:svc",
                resource_templates=K8S_RESOURCE_FILES,
                krh_resource_types={Service},
                krh_labels=create_charm_default_labels(
                    self.app.name, self.model.name, scope="svc"
                ),
                context_callable=lambda: {
                    "app_name": self.app.name,
                    "namespace": self.model.name,
                    "grpc_port": self._svc_grpc_port,
                },
                lightkube_client=lightkube.Client(),
            ),
            depends_on=[self.leadership_gate],
        )

        # The chown_component ensures the /data directory belongs to
        # the _daemon_ user and group set in the mlmd rock
        # This is added because of https://github.com/juju/juju/issues/19020
        # NOTE: if an oci-image other than the mlmd rock is to be used,
        # please make sure the user that runs the process and owns /data is updated
        self.chown_component = self.charm_reconciler.add(
            component=ChownMountedStorageComponent(
                charm=self,
                name="chown-storage",
                storage_path="/data",
                workload_user="_daemon_",
                workload_container="mlmd-grpc-server",
            ),
            depends_on=[self.leadership_gate],
        )

        self.mlmd_container = self.charm_reconciler.add(
            component=MlmdPebbleService(
                charm=self,
                name="mlmd-grpc-service",
                container_name="mlmd-grpc-server",
                service_name="mlmd",
                grpc_port=self._svc_grpc_port,
                metadata_store_server_config_file=SQLITE_CONFIG_PROTO_DESTINATION,
                files_to_push=[
                    LazyContainerFileTemplate(
                        destination_path=SQLITE_CONFIG_PROTO_DESTINATION,
                        source_template=SQLITE_CONFIG_PROTO,
                    )
                ],
            ),
            depends_on=[self.leadership_gate, self.chown_component],
        )

        self.charm_reconciler.install_default_event_handlers()
        grpc_port = ServicePort(int(self._svc_grpc_port), name="grpc-api")
        self.service_patcher = KubernetesServicePatch(self, [grpc_port])

        # KubernetesServiceInfoProvider for broadcasting the GRPC service information
        self._k8s_svc_info_provider = KubernetesServiceInfoProvider(
            charm=self,
            relation_name=RELATION_NAME,
            name=GRPC_SVC_NAME,
            port=self._svc_grpc_port,
            refresh_event=self.on.config_changed,
        )

        # configure the Velero backup relation
        self.velero_backup_config = VeleroBackupRequirer(
            charm=self,
            app_name=self.app.name,
            relation_name="velero-backup-config",
            spec=VeleroBackupSpec(
                include_namespaces=[self.model.name],
                include_resources=["persistentvolumeclaims"],
                label_selector={
                    "app.kubernetes.io/name": self.app.name,
                },
            ),
        )
        self._logging = LogForwarder(charm=self)


if __name__ == "__main__":
    main(Operator)
