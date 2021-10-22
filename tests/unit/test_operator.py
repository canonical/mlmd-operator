from collections import namedtuple

from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from ops.testing import Harness

from charm import Operator

import unittest
from unittest.mock import patch, MagicMock


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(Operator)
        self.addCleanup(self.harness.cleanup)

    def test_not_leader(self):
        self.harness.begin()
        self.assertEqual(self.harness.charm.unit.status, ActiveStatus())

    @patch("charm.KubernetesServicePatch", MagicMock())
    def test_no_relation(self):
        self.harness.set_leader(True)
        with patch("ops.model.Container.push") as _push:
            self.harness.begin_with_initial_hooks()
            _push.assert_called_with(
                "/config/config.proto",
                'connection_config: {sqlite: {filename_uri: "file:/data/mlmd.db"}}',
                make_dirs=True,
            )
        self.assertEqual(self.harness.charm.unit.status, ActiveStatus())

        service = self.harness.model.unit.get_container("mlmd").get_service("mlmd")
        self.assertTrue(service.is_running())

        plan = self.harness.get_container_pebble_plan("mlmd").to_dict()
        self.assertEqual(
            plan["services"]["mlmd"],
            {
                "override": "replace",
                "summary": "mlmd",
                "startup": "enabled",
                "command": "/bin/metadata_store_server"
                " --metadata_store_server_config_file=/config/config.proto"
                " --grpc_port=8080"
                " --enable_database_upgrade=true",
            },
        )

    @patch("charm.KubernetesServicePatch", MagicMock())
    def test_many_relations(self):
        self.harness.set_leader(True)
        self.harness.add_relation("mysql", "mysql")
        self.harness.add_relation("mysql", "mysql2")
        self.harness.begin_with_initial_hooks()

        self.assertEqual(
            self.harness.charm.unit.status, BlockedStatus("Too many mysql relations")
        )

    @patch("charm.KubernetesServicePatch", MagicMock())
    def test_one_relation(self):
        self.harness.set_leader(True)
        rel_id = self.harness.add_relation("mysql", "mysql")
        self.harness.add_relation_unit(rel_id, "mysql/0")
        self.harness.update_relation_data(
            rel_id,
            "mysql/0",
            {
                "database": "unit-db",
                "host": "unit-host",
                "port": "unit-port",
                "user": "unit-user",
                "password": "unit-password",
                "root_password": "unit-root",
            },
        )

        self.harness.begin_with_initial_hooks()
        self.assertEqual(self.harness.charm.unit.status, ActiveStatus())

        service = self.harness.model.unit.get_container("mlmd").get_service("mlmd")
        self.assertTrue(service.is_running())

        plan = self.harness.get_container_pebble_plan("mlmd").to_dict()
        self.assertEqual(
            plan["services"]["mlmd"],
            {
                "override": "replace",
                "summary": "mlmd",
                "startup": "enabled",
                "command": "/bin/metadata_store_server"
                " --mysql_config_database=unit-db"
                " --mysql_config_host=unit-host"
                " --mysql_config_port=unit-port"
                " --mysql_config_user=unit-user"
                " --mysql_config_password=unit-password"
                " --grpc_port=8080"
                " --enable_database_upgrade=true",
            },
        )

    @patch("charm.KubernetesServicePatch", MagicMock())
    def test_pebble_not_ready(self):
        self.harness.set_leader(True)
        with patch("ops.model.Container.can_connect") as _can_connect:
            _can_connect.return_value = False
            self.harness.begin_with_initial_hooks()

        self.assertEqual(
            self.harness.charm.unit.status, WaitingStatus("Waiting for pebble")
        )

    @patch("charm.KubernetesServicePatch", MagicMock())
    @patch("ops.model.Container.push", MagicMock())
    def test_config_port(self):
        self.harness.set_leader(True)
        self.harness.begin_with_initial_hooks()

        self.harness.update_config({"port": 1000})
        plan = self.harness.get_container_pebble_plan("mlmd").to_dict()
        self.assertIn("--grpc_port=1000", plan["services"]["mlmd"]["command"])

    @patch("charm.KubernetesServicePatch", MagicMock())
    @patch("ops.model.Container.push", MagicMock())
    def test_kubernetes_service(self):
        self.harness.set_leader(True)
        self.harness.begin()
        self.harness.update_config({"port": 5000})
        self.harness.charm.service_patcher._service_object.assert_called_once_with(
            [("grpc-api", 5000)]
        )
        self.harness.charm.service_patcher._patch.assert_called_once_with(None)

    @patch("charm.KubernetesServicePatch", MagicMock())
    @patch("ops.model.Container.push", MagicMock())
    def test_grpc_interface(self):
        self.harness.set_leader(True)
        self.harness.begin_with_initial_hooks()

        self.harness.update_config({"port": 5000})
        self.harness.charm.interfaces["grpc"] = MagicMock()

        self.harness.add_relation("grpc", "my-app")
        MockRelation = namedtuple("Relation", ["name", "id"])
        self.harness.charm.on["grpc"].relation_changed.emit(MockRelation("grpc", 0))
        self.harness.charm.interfaces["grpc"].send_data.assert_called_once_with(
            {
                "service": self.harness.model.app.name,
                "port": 5000,
            }
        )
