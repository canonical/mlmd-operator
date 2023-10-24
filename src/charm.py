#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

from charmed_kubeflow_chisme.exceptions import ErrorWithStatus, GenericCharmRuntimeError
from charms.data_platform_libs.v0.data_interfaces import DatabaseRequires
from oci_image import OCIImageResource, OCIImageResourceError
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from serialized_data_interface import NoCompatibleVersions, NoVersionsListed, get_interfaces


class Operator(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)

        self.log = logging.getLogger()

        self.image = OCIImageResource(self, "oci-image")

        for event in [
            self.on.config_changed,
            self.on.install,
            self.on.upgrade_charm,
            self.on["relational-db"].relation_changed,
            self.on["relational-db"].relation_joined,
            self.on["relational-db"].relation_departed,
            self.on["relational-db"].relation_broken,
            self.on["grpc"].relation_changed,
        ]:
            self.framework.observe(event, self.main)

        # Name from upstream pipeline-install-config configMap
        self._database_name = "metadb"

        self.database = DatabaseRequires(
            self, relation_name="relational-db", database_name=self._database_name
        )

    def main(self, event):
        try:
            self._check_leader()

            interfaces = self._get_interfaces()

            image_details = self._check_image_details()

            self._check_db_relation()

            db_data = self._get_relational_db_data(interfaces)

        except ErrorWithStatus as check_failed:
            self.model.unit.status = check_failed.status
            return

        self._send_info(interfaces)

        config = self.model.config
        args = [
            f"--grpc_port={config['port']}",
            f"--mysql_config_database={db_data['name']}",
            f"--mysql_config_host={db_data['host']}",
            f"--mysql_config_port={db_data['port']}",
            f"--mysql_config_user={db_data['username']}",
            f"--mysql_config_password={db_data['password']}",
            "--enable_database_upgrade=true",
        ]
        volumes = []

        self.model.unit.status = MaintenanceStatus("Setting pod spec")
        self.model.pod.set_spec(
            {
                "version": 3,
                "containers": [
                    {
                        "name": "mlmd",
                        "command": ["/bin/metadata_store_server"],
                        "args": args,
                        "imageDetails": image_details,
                        "ports": [
                            {
                                "name": "grpc-api",
                                "containerPort": int(self.model.config["port"]),
                            },
                        ],
                        "volumeConfig": volumes,
                        "kubernetes": {
                            "livenessProbe": {
                                "tcpSocket": {"port": "grpc-api"},
                                "initialDelaySeconds": 3,
                                "periodSeconds": 5,
                                "timeoutSeconds": 2,
                            },
                            "readinessProbe": {
                                "tcpSocket": {"port": "grpc-api"},
                                "initialDelaySeconds": 3,
                                "periodSeconds": 5,
                                "timeoutSeconds": 2,
                            },
                        },
                    }
                ],
            },
            k8s_resources={
                "kubernetesResources": {
                    "services": [
                        {
                            "name": "metadata-grpc-service",
                            "spec": {
                                "selector": {"app.kubernetes.io/name": self.model.app.name},
                                "ports": [
                                    {
                                        "name": "grpc-api",
                                        "port": int(config["port"]),
                                        "protocol": "TCP",
                                        "targetPort": int(config["port"]),
                                    },
                                ],
                            },
                        }
                    ]
                }
            },
        )
        self.model.unit.status = ActiveStatus()

    def _send_info(self, interfaces):
        if interfaces["grpc"]:
            interfaces["grpc"].send_data(
                {
                    "service": "metadata-grpc-service",
                    "port": self.model.config["port"],
                }
            )

    def _check_leader(self):
        if not self.unit.is_leader():
            self.log.info("Not a leader, skipping set_pod_spec")
            raise ErrorWithStatus("", ActiveStatus)

    def _get_interfaces(self):
        try:
            interfaces = get_interfaces(self)
        except NoVersionsListed as err:
            raise ErrorWithStatus(err, WaitingStatus)
        except NoCompatibleVersions as err:
            raise ErrorWithStatus(err, BlockedStatus)
        return interfaces

    def _check_image_details(self):
        try:
            image_details = self.image.fetch()
        except OCIImageResourceError as e:
            raise ErrorWithStatus(f"{e.status.message}", e.status_type)
        return image_details

    def _check_db_relation(self):
        """Retrieve relational-db relation

        Returns relation, if it is established, and raises error otherwise.
        """
        relation = self.model.get_relation("relational-db")

        if not relation:
            self.log.warning("No relational-db relation was found")
            raise ErrorWithStatus(
                "Please add required database relation: relational-db", BlockedStatus
            )

        return relation

    def _get_relational_db_data(self, rel_id: int) -> dict:
        """Check relational-db relation, retrieve and return data, if available."""
        db_data = {}
        relation_data = {}

        relation_data = self.database.fetch_relation_data()

        # Parse data in relation
        # this also validates expected data by means of KeyError exception
        for val in relation_data.values():
            if not val:
                continue
            try:
                db_data["name"] = val["database"]
                db_data["password"] = val["password"]
                db_data["username"] = val["username"]
                host, port = val["endpoints"].split(":")
                db_data["host"] = host
                db_data["port"] = port
            except KeyError as err:
                self.log.error(f"Missing attribute {err} in relational-db relation data")
                # incorrect/incomplete data can be found in relational-db relation which can be
                # resolved: use WaitingStatus
                raise ErrorWithStatus(
                    "Incorrect/incomplete data found in relation relational-db. See logs",
                    WaitingStatus,
                )
        if not db_data:
            self.log.warning("Found empty relation data for relational-db relation.")
            raise ErrorWithStatus("Waiting for relational-db data", WaitingStatus)

        return db_data


if __name__ == "__main__":
    main(Operator)
