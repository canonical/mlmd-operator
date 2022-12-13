#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

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
            self.on["mysql"].relation_changed,
            self.on["grpc"].relation_changed,
        ]:
            self.framework.observe(event, self.main)

    def main(self, event):

        try:

            self._check_leader()

            interfaces = self._get_interfaces()

            image_details = self._check_image_details()

        except CheckFailed as check_failed:
            self.model.unit.status = check_failed.status
            return

        self._send_info(interfaces)

        mysql = self.model.relations["mysql"]

        if len(mysql) > 1:
            self.model.unit.status = BlockedStatus("Too many mysql relations")
            return

        try:
            mysql = mysql[0]
            unit = list(mysql.units)[0]
            mysql = mysql.data[unit]
            mysql["database"]
            db_args = [
                f"--mysql_config_database={mysql['database']}",
                f"--mysql_config_host={mysql['host']}",
                f"--mysql_config_port={mysql['port']}",
                f"--mysql_config_user={mysql['user']}",
                f"--mysql_config_password={mysql['password']}",
            ]
            volumes = []
        except (IndexError, KeyError):
            db_args = ["--metadata_store_server_config_file=/config/config.proto"]
            config_proto = 'connection_config: {sqlite: {filename_uri: "file:/data/mlmd.db"}}'
            volumes = [
                {
                    "name": "config",
                    "mountPath": "/config",
                    "files": [{"path": "config.proto", "content": config_proto}],
                }
            ]

        config = self.model.config

        args = db_args + [
            f"--grpc_port={config['port']}",
            "--enable_database_upgrade=true",
        ]

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
                    "service": self.model.app.name,
                    "port": self.model.config["port"],
                }
            )

    def _check_leader(self):
        if not self.unit.is_leader():
            self.log.info("Not a leader, skipping set_pod_spec")
            raise CheckFailed("", ActiveStatus)

    def _get_interfaces(self):
        try:
            interfaces = get_interfaces(self)
        except NoVersionsListed as err:
            raise CheckFailed(err, WaitingStatus)
        except NoCompatibleVersions as err:
            raise CheckFailed(err, BlockedStatus)
        return interfaces

    def _check_image_details(self):
        try:
            image_details = self.image.fetch()
        except OCIImageResourceError as e:
            raise CheckFailed(f"{e.status.message}", e.status_type)
        return image_details


class CheckFailed(Exception):
    """Raise this exception if one of the checks in main fails."""

    def __init__(self, msg: str, status_type=None):
        super().__init__()

        self.msg = str(msg)
        self.status_type = status_type
        self.status = status_type(self.msg)


if __name__ == "__main__":
    main(Operator)
