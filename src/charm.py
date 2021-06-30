#!/usr/bin/env python3

import logging

from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus

from oci_image import OCIImageResource, OCIImageResourceError
from serialized_data_interface import (
    NoCompatibleVersions,
    NoVersionsListed,
    get_interfaces,
)


class Operator(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)

        self.log = logging.getLogger()

        if not self.model.unit.is_leader():
            self.log.info("Not a leader, skipping set_pod_spec")
            self.model.unit.status = ActiveStatus()
            return

        self.image = OCIImageResource(self, "oci-image")

        try:
            self.interfaces = get_interfaces(self)
        except NoVersionsListed as err:
            self.model.unit.status = WaitingStatus(str(err))
            return
        except NoCompatibleVersions as err:
            self.model.unit.status = BlockedStatus(str(err))
            return
        else:
            self.model.unit.status = ActiveStatus()

        self.framework.observe(self.on.install, self.set_pod_spec)
        self.framework.observe(self.on.upgrade_charm, self.set_pod_spec)
        self.framework.observe(self.on.config_changed, self.set_pod_spec)
        self.framework.observe(self.on["mysql"].relation_changed, self.set_pod_spec)

        self.framework.observe(self.on["grpc"].relation_changed, self.send_info)

    def send_info(self, event):
        if self.interfaces["grpc"]:
            self.interfaces["grpc"].send_data(
                {
                    "service": self.model.app.name,
                    "port": self.model.config["port"],
                }
            )

    def set_pod_spec(self, event):
        try:
            image_details = self.image.fetch()
        except OCIImageResourceError as e:
            self.model.unit.status = e.status
            self.log.info(e)
            return

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
            config_proto = (
                'connection_config: {sqlite: {filename_uri: "file:/data/mlmd.db"}}'
            )
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
                                "selector": {
                                    "app.kubernetes.io/name": self.model.app.name
                                },
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


if __name__ == "__main__":
    main(Operator)
