#!/usr/bin/env python3

import shlex
import logging

from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus

from serialized_data_interface import (
    NoCompatibleVersions,
    NoVersionsListed,
    get_interfaces,
)

from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch

LOG = logging.getLogger(__name__)


class Operator(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)

        if not self.unit.is_leader():
            LOG.info("Not a leader, skipping configuration")
            self.unit.status = ActiveStatus()
            return

        try:
            self.interfaces = get_interfaces(self)
        except NoVersionsListed as err:
            self.unit.status = WaitingStatus(str(err))
            return
        except NoCompatibleVersions as err:
            self.unit.status = BlockedStatus(str(err))
            return
        else:
            self.unit.status = ActiveStatus()

        self.framework.observe(self.on.install, self.update_container)
        self.framework.observe(self.on.upgrade_charm, self.update_container)
        self.framework.observe(self.on.config_changed, self.update_container)
        self.framework.observe(self.on["mysql"].relation_changed, self.update_container)

        self.framework.observe(self.on["grpc"].relation_changed, self.send_info)

        # run service patcher after the charm hooks have run
        # so that config['port'] is set correctly
        self.service_patcher = KubernetesServicePatch(
            self, [("grpc-api", int(self.config["port"]))]
        )

    def send_info(self, _):
        if self.interfaces["grpc"]:
            self.interfaces["grpc"].send_data(
                {
                    "service": self.model.app.name,
                    "port": self.config["port"],
                }
            )

    def update_container(self, _):
        container = self.unit.get_container("mlmd")
        if not container.can_connect():
            self.unit.status = WaitingStatus("Waiting for pebble")
            return

        # update port in service patcher
        self.service_patcher.service = self.service_patcher._service_object(
            [("grpc-api", int(self.config["port"]))]
        )
        self.service_patcher._patch(None)

        mysql = self.model.relations["mysql"]
        if len(mysql) > 1:
            self.unit.status = BlockedStatus("Too many mysql relations")
            return

        try:
            # pick data from first unit in first mysql relation
            mysql_data = mysql[0].data[list(mysql[0].units)[0]]
            db_args = [
                f"--mysql_config_database={mysql_data['database']}",
                f"--mysql_config_host={mysql_data['host']}",
                f"--mysql_config_port={mysql_data['port']}",
                f"--mysql_config_user={mysql_data['user']}",
                f"--mysql_config_password={mysql_data['password']}",
            ]
        except (IndexError, KeyError):
            db_args = ["--metadata_store_server_config_file=/config/config.proto"]
            config_proto = (
                'connection_config: {sqlite: {filename_uri: "file:/data/mlmd.db"}}'
            )

            container.push("/config/config.proto", config_proto, make_dirs=True)

        args = db_args + [
            f"--grpc_port={self.config['port']}",
            "--enable_database_upgrade=true",
        ]

        layer = {
            "summary": "mlmd-operator",
            "description": "mlmd-operator layer",
            "services": {
                "mlmd": {
                    "override": "replace",
                    "summary": "mlmd",
                    "command": shlex.join(["/bin/metadata_store_server"] + args),
                    "startup": "enabled",
                },
            },
        }

        if container.get_plan().to_dict().get("services", {}) != layer["services"]:
            self.unit.status = MaintenanceStatus("Updating pod")
            container.add_layer("mlmd", layer, combine=True)
            container.restart("mlmd")
            LOG.info("Restarted mlmd")

        self.unit.status = ActiveStatus()


if __name__ == "__main__":
    main(Operator)
