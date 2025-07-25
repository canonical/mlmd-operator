import pytest
from interface_tester.plugin import InterfaceTester

from charm import Operator


@pytest.fixture
def interface_tester(interface_tester: InterfaceTester):
    interface_tester.configure(charm_type=Operator)
    yield interface_tester
