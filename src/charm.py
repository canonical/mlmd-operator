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
from charms.mlops_libs.v0.k8s_service_info import KubernetesServiceInfoProvider
from lightkube.resources.core_v1 import Service
from ops.charm import CharmBase
from ops.main import main

from components.pebble_components import MlmdPebbleService

logger = logging.getLogger()

GRPC_SVC_NAME = "metadata-grpc-service"
K8S_RESOURCE_FILES = ["src/templates/ml-pipeline-service.yaml.j2"]
RELATION_NAME = "k8s-svc-info"
SQLITE_CONFIG_PROTO_DESTINATION = "/config/config.proto"
SQLITE_CONFIG_PROTO = 'connection_config: {sqlite: {filename_uri: "file:/data/mlmd.db"}}'


class Operator(CharmBase):
    """Charm for the ML Metadata GRPC Server."""

    def __init__(self, *args):
        super().__init__(*args)

        # KubernetesServiceInfoProvider for broadcasting the GRPC service information
        self._svc_port = self.config["grpc-port"]
        self._k8s_svc_info_provider = KubernetesServiceInfoProvider(
            charm=self, relation_name=RELATION_NAME, name=GRPC_SVC_NAME, port=self._svc_port
        )

        # Charm logic
        self.charm_reconciler = CharmReconciler(self)

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
                    "grpc_port": self._svc_port,
                },
                lightkube_client=lightkube.Client(),
            ),
            depends_on=[self.leadership_gate],
        )

        self.mlmd_container = self.charm_reconciler.add(
            component=MlmdPebbleService(
                charm=self,
                name="mlmd-grpc-service",
                container_name="mlmd-grpc-server",
                service_name="mlmd",
                grpc_port=self.config["grpc-port"],
                files_to_push=[
                    LazyContainerFileTemplate(
                        destination_path=SQLITE_CONFIG_PROTO_DESTINATION,
                        source_template=SQLITE_CONFIG_PROTO,
                    )
                ],
            ),
            depends_on=[self.leadership_gate],
        )

        self.charm_reconciler.install_default_event_handlers()


if __name__ == "__main__":
    main(Operator)
