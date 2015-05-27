# -*- coding: utf-8 -*-
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Product tests for presto-admin connector support.
"""
from time import sleep
import json
import os

from prestoadmin.util import constants
from tests.product.base_product_case import BaseProductTestCase, \
    LOCAL_RESOURCES_DIR


CONNECTOR_CHECK_TIMEOUT = 120
CONNECTOR_CHECK_INTERVAL = 5


class PrestoError(Exception):
    pass


class TestConnectors(BaseProductTestCase):
    def test_basic_connector_add_remove(self):
        self.install_default_presto()
        self.run_prestoadmin('server start')
        for host in self.all_hosts():
            self.assert_has_default_connector(host)

        self._assert_connectors_loaded([['system'], ['tpch']])

        self.run_prestoadmin('connector remove tpch')
        self.run_prestoadmin('server restart')
        self.assert_path_removed(self.master,
                                 os.path.join(constants.CONNECTORS_DIR,
                                              'tpch.properties'))
        self._assert_connectors_loaded([['system']])
        for host in self.all_hosts():
            self.assert_path_removed(host,
                                     os.path.join(constants.REMOTE_CATALOG_DIR,
                                                  'tcph.properties'))

        self.write_content_to_master('connector.name=tpch',
                                     os.path.join(constants.CONNECTORS_DIR,
                                                  'tpch.properties'))
        self.run_prestoadmin('connector add')
        self.run_prestoadmin('server restart')
        for host in self.all_hosts():
            self.assert_has_default_connector(host)
        self._assert_connectors_loaded([['system'], ['tpch']])

    def test_connector_add(self):
        self.install_default_presto()

        # test add connector without read permissions on file
        script = 'chmod 600 /etc/opt/prestoadmin/connectors/tpch.properties;' \
                 ' su app-admin -c "./presto-admin connector add tpch"'
        output = self.run_prestoadmin_script(script)
        with open(os.path.join(LOCAL_RESOURCES_DIR,
                               'connector_permissions_warning.txt'), 'r') as f:
            expected = f.read()

        self.assertEqualIgnoringOrder(expected, output)

        # test add connector directory without read permissions on directory
        script = 'chmod 600 /etc/opt/prestoadmin/connectors; ' \
                 'su app-admin -c "./presto-admin connector add"'
        output = self.run_prestoadmin_script(script)
        permission_error = '\nWarning: [slave3] Permission denied\n\n\n' \
                           'Warning: [slave2] Permission denied\n\n\n' \
                           'Warning: [slave1] Permission denied\n\n\n' \
                           'Warning: [master] Permission denied\n\n'
        self.assertEqualIgnoringOrder(output, permission_error)

        # test add connector by file without read permissions on directory
        script = 'chmod 600 /etc/opt/prestoadmin/connectors; ' \
                 'su app-admin -c "./presto-admin connector add tpch"'
        output = self.run_prestoadmin_script(script)
        self.assert_parallel_execution_failure(self.all_hosts(),
                                               'connector.add',
                                               'Configuration for connector'
                                               ' tpch not found', output)

        # test add a connector that does not exist
        self.run_prestoadmin('connector remove tpch')
        output = self.run_prestoadmin('connector add tpch')
        self.assert_parallel_execution_failure(
            self.all_hosts(), 'connector.add',
            'Configuration for connector tpch not found', output)

        # test add all connectors when the directory does not exist
        self.exec_create_start(self.master,
                               'rmdir /etc/opt/prestoadmin/connectors')
        output = self.run_prestoadmin('connector add')
        self.assert_parallel_execution_failure(
            self.all_hosts(), 'connector.add',
            'Cannot add connectors because directory '
            '/etc/opt/prestoadmin/connectors does not exist', output)

        # test add connector by name when it exists
        self.write_content_to_master('connector.name=tpch',
                                     os.path.join(constants.CONNECTORS_DIR,
                                                  'tpch.properties'))
        self.run_prestoadmin('connector add tpch')
        self.run_prestoadmin('server start')
        for host in self.all_hosts():
            self.assert_has_default_connector(host)
        self._assert_connectors_loaded([['system'], ['tpch']])

        self.run_prestoadmin('connector remove tpch')
        self.run_prestoadmin('server restart')

        # test add connectors where directory is empty
        output = self.run_prestoadmin('connector add')
        expected = """
Warning: [slave3] Directory /etc/opt/prestoadmin/connectors is empty. \
No connectors will be deployed


Warning: [slave2] Directory /etc/opt/prestoadmin/connectors is empty. \
No connectors will be deployed


Warning: [slave1] Directory /etc/opt/prestoadmin/connectors is empty. \
No connectors will be deployed


Warning: [master] Directory /etc/opt/prestoadmin/connectors is empty. \
No connectors will be deployed

"""
        self.assertEqualIgnoringOrder(expected, output)

        # test add connectors from directory with more than one connector
        self.write_content_to_master('connector.name=tpch',
                                     os.path.join(constants.CONNECTORS_DIR,
                                                  'tpch.properties'))
        self.write_content_to_master('connector.name=jmx',
                                     os.path.join(constants.CONNECTORS_DIR,
                                                  'jmx.properties'))
        self.run_prestoadmin('connector add')
        self.run_prestoadmin('server restart')
        for host in self.all_hosts():
            self.assert_has_default_connector(host)
            self.assert_file_content(host,
                                     '/etc/presto/catalog/jmx.properties',
                                     'connector.name=jmx')
        self._assert_connectors_loaded([['system'], ['jmx'], ['tpch']])

    def test_connector_add_lost_host(self):
        self.install_presto_admin()
        self.upload_topology()
        self.server_install()
        self.run_prestoadmin('connector remove tpch')

        self.stop_and_wait(self.slaves[0])
        self.write_content_to_master('connector.name=tpch',
                                     os.path.join(constants.CONNECTORS_DIR,
                                                  'tpch.properties'))
        output = self.run_prestoadmin('connector add tpch')
        for host in self.all_hosts():
            deploying_message = 'Deploying tpch.properties connector ' \
                                'configurations on: %s'
            self.assertTrue(deploying_message % host in output,
                            'expected %s \n actual %s'
                            % (deploying_message % host, output))
        self.assert_parallel_execution_failure([self.slaves[0]],
                                               'connector.add',
                                               self.down_node_connection_error
                                               % {'host': self.slaves[0]},
                                               output)
        self.run_prestoadmin('server start')

        for host in [self.master, self.slaves[1], self.slaves[2]]:
            self.assert_has_default_connector(host)
        self._assert_connectors_loaded([['system'], ['tpch']])

    def test_connector_remove(self):
        self.install_default_presto()
        for host in self.all_hosts():
            self.assert_has_default_connector(host)

        missing_connector_message = """
Warning: [slave1] Could not remove connector '%(name)s'. No such file \
'/etc/presto/catalog/%(name)s.properties'


Warning: [master] Could not remove connector '%(name)s'. No such file \
'/etc/presto/catalog/%(name)s.properties'


Warning: [slave3] Could not remove connector '%(name)s'. No such file \
'/etc/presto/catalog/%(name)s.properties'


Warning: [slave2] Could not remove connector '%(name)s'. No such file \
'/etc/presto/catalog/%(name)s.properties'

"""

        success_message = """[master] Connector removed. Restart the server \
for the change to take effect
[slave1] Connector removed. Restart the server for the change to take effect
[slave2] Connector removed. Restart the server for the change to take effect
[slave3] Connector removed. Restart the server for the change to take effect"""

        # test remove connector does not exist
        output = self.run_prestoadmin('connector remove jmx')
        self.assertEqualIgnoringOrder(
            missing_connector_message % {'name': 'jmx'},
            output)

        # test remove connector not in directory, but in presto
        self.exec_create_start(self.master,
                               'rm /etc/opt/prestoadmin/connectors/'
                               'tpch.properties')

        output = self.run_prestoadmin('connector remove tpch')
        self.assertEqualIgnoringOrder(success_message, output)

        # test remove connector in directory but not in presto
        self.write_content_to_master('connector.name=tpch',
                                     os.path.join(constants.CONNECTORS_DIR,
                                                  'tpch.properties'))
        output = self.run_prestoadmin('connector remove tpch')
        self.assertEqualIgnoringOrder(
            missing_connector_message % {'name': 'tpch'},
            output)

    def get_connector_info(self):
        output = self.exec_create_start(
            self.master,
            "curl --silent -X POST http://localhost:8080/v1/statement -H "
            "'X-Presto-User:$USER' -H 'X-Presto-Schema:metadata' -H "
            "'X-Presto-Catalog:system' -d 'select catalog_name from catalogs'")

        data = self.get_key_value(output, 'data')
        next_uri = self.get_key_value(output, 'nextUri')
        while not data and next_uri:
            output = self.exec_create_start(self.master,
                                            'curl --silent %s'
                                            % self.get_key_value(output,
                                                                 'nextUri'))
            data = self.get_key_value(output, 'data')
            next_uri = self.get_key_value(output, 'nextUri')

        if not data:
            raise PrestoError('Could not get catalogs from json output')

        return data

    def get_key_value(self, text, key):
        try:
            return json.loads(text)[key]
        except KeyError:
            return ''
        except ValueError as e:
            raise ValueError(e.message + '\n' + text)

    # Presto will be 'query-able' before it has loaded all of its
    # connectors. When presto-admin restarts presto it returns when it
    # can query the server but that doesn't mean that all connectors
    # have been loaded. Thus in order to verify that connectors get
    # correctly added we check continuously within a timeout.
    def _assert_connectors_loaded(self, expected_connectors):
        time_spent_waiting = 0
        while time_spent_waiting <= CONNECTOR_CHECK_TIMEOUT:
            try:
                self.assertEqual(self.get_connector_info(),
                                 expected_connectors)
                # no exception thrown, the correct connectors were
                # were loaded
                return
            except AssertionError:
                pass  # not all connectors loaded
            sleep(CONNECTOR_CHECK_INTERVAL)
            time_spent_waiting += CONNECTOR_CHECK_INTERVAL
        self.assertEqual(self.get_connector_info(), expected_connectors)