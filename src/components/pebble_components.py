# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

from charmed_kubeflow_chisme.components.pebble_component import PebbleServiceComponent
from ops.pebble import Layer

logger = logging.getLogger(__name__)


class MlmdPebbleService(PebbleServiceComponent):
    def __init__(self, *args, grpc_port: str, metadata_store_server_config_file: str, **kwargs):
        """Pebble service component that configures the Pebble layer."""
        super().__init__(*args, **kwargs)
        self._grpc_port = grpc_port
        self._metadata_store_server_config_file = metadata_store_server_config_file

    def get_layer(self) -> Layer:
        """Pebble configuration layer for MLMD GRPC Server"""
        command = (
            "bin/metadata_store_server"
            f" --metadata_store_server_config_file={self._metadata_store_server_config_file}"
            f" --grpc_port={self._grpc_port}"
            " --enable_database_upgrade=true"
        )
        layer = Layer(
            {
                "services": {
                    self.service_name: {
                        "override": "replace",
                        "summary": "entry point for MLMD GRPC Service",
                        "command": command,  # Must be a string
                        "startup": "enabled",
                        "user": "_daemon_",
                    }
                },
            }
        )

        return layer
