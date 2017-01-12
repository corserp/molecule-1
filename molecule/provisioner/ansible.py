#  Copyright (c) 2015-2017 Cisco Systems, Inc.

#  Permission is hereby granted, free of charge, to any person obtaining a copy
#  of this software and associated documentation files (the "Software"), to
#  deal in the Software without restriction, including without limitation the
#  rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
#  sell copies of the Software, and to permit persons to whom the Software is
#  furnished to do so, subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included in
#  all copies or substantial portions of the Software.
#
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
#  FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#  DEALINGS IN THE SOFTWARE.

import collections
import os

import yaml
import yaml.representer
import jinja2

from molecule import ansible_playbook
from molecule import util


class Ansible(object):
    """
    `Ansible`_ is the default provisioner.  No other provisioner will be
    supported.

    Additional options can be passed to `ansible-playbook` through the options
    dict.  Any option set in this section will override the defaults.

    .. code-block:: yaml

        provisioner:
          name: ansible
          options:
            debug: True
    """

    def __init__(self, config):
        """
        A class encapsulating the provisioner.

        :param config: An instance of a Molecule config.
        :return: None
        """
        self._config = config
        self._setup()

    @property
    def default_config_options(self):
        """
        Default options provided to construct ansible.cfg and returns a dict.

        :return: dict
        """
        return {
            'defaults': {
                'ansible_managed':
                'Ansible managed: Do NOT edit this file manually!',
                'retry_files_enabled': False,
                'roles_path': '../../../../:$ANSIBLE_LIBRARY',
                'filter_plugins': '{}:$ANSIBLE_FILTER_PLUGINS'.format(
                    self._get_filter_plugin_directory()),
            }
        }

    @property
    def default_options(self):
        """
        Default CLI arguments provided to `ansible-playbook` and returns a
        dict.

        :return: dict
        """
        d = {}
        if self._config.args.get('debug'):
            d['debug'] = True

        return d

    @property
    def name(self):
        return self._config.config['provisioner']['name']

    @property
    def config_options(self):
        return self._config.merge_dicts(
            self.default_config_options,
            self._config.config['provisioner']['config_options'])

    @property
    def options(self):
        return self._config.merge_dicts(
            self.default_options,
            self._config.config['provisioner']['options'])

    @property
    def inventory(self):
        # ungrouped:
        #   hosts:
        #     instance-1-default:
        #     instance-2-default:
        # $group_name:
        #   hosts:
        #     instance-1-default:
        #       ansible_connection: docker
        #     instance-2-default:
        #       ansible_connection: docker
        dd = self._vivify()
        for platform in self._config.platforms_with_scenario_name:
            for group in platform.get('groups', ['ungrouped']):
                instance_name = platform['name']
                connection_options = self._config.driver.connection_options
                dd[group]['hosts'][instance_name] = connection_options

        return dd

    @property
    def inventory_file(self):
        return os.path.join(self._config.ephemeral_directory,
                            'ansible_inventory.yml')

    @property
    def config_file(self):
        return os.path.join(self._config.ephemeral_directory, 'ansible.cfg')

    def converge(self, playbook, **kwargs):
        """
        Executes `ansible-playbook` and returns a string.

        :param playbook: A string containing an absolute path to a
         provisioner's playbook.
        :param kwargs: Optional keyword arguments.
        :return: str
        """
        pb = self._get_ansible_playbook(playbook, **kwargs)
        return pb.execute()

    def syntax(self, playbook):
        """
        Executes `ansible-playbook` syntax check and returns None.

        :param playbook: A string containing an absolute path to a
         provisioner's playbook.
        :return: None
        """
        pb = self._get_ansible_playbook(playbook)
        pb.add_cli_arg('syntax-check', True)
        pb.execute()

    def check(self, playbook):
        """
        Executes `ansible-playbook` check and returns None.

        :param playbook: A string containing an absolute path to a
         provisioner's playbook.
        :return: None
        """
        pb = self._get_ansible_playbook(playbook)
        pb.add_cli_arg('check', True)
        pb.execute()

    def write_inventory(self):
        """
        Writes the provisioner's inventory file to disk and returns None.

        :return: None
        """
        self._verify_inventory()
        yaml.add_representer(collections.defaultdict,
                             yaml.representer.Representer.represent_dict)

        util.write_file(self.inventory_file, yaml.dump(self.inventory))
        # TODO(retr0h): Move to safe dump
        #  util.write_file(self.inventory_file, util.safe_dump(self.inventory))

    def write_config(self):
        """
        Writes the provisioner's config file to disk and returns None.

        :return: None
        """
        # self._verify_config()

        template = jinja2.Environment()
        template = template.from_string(self._get_config_template())
        template = template.render(config_options=self.config_options)
        util.write_file(self.config_file, template)

    def _get_ansible_playbook(self, playbook, **kwargs):
        """
        Get an instance of AnsiblePlaybook and returns it.

        :param playbook: A string containing an absolute path to a
         provisioner's playbook.
        :param kwargs: Optional keyword arguments.
        :return: object
        """
        return ansible_playbook.AnsiblePlaybook(self.inventory_file, playbook,
                                                self._config, **kwargs)

    def _setup(self):
        """
        Prepare the system for using the provisioner and returns None.

        :return: None
        """
        self.write_inventory()
        self.write_config()

    def _verify_inventory(self):
        """
        Verify the inventory is valid and returns None.

        :return: None
        """
        if not self.inventory:
            msg = ("Instances missing from the 'platform' "
                   "section of molecule.yml.")
            util.print_error(msg)
            util.sysexit()

    def _get_config_template(self):
        """
        Returns a config template string.

        :return: str
        """
        return """
# Molecule managed


{% for section, section_dict in config_options.iteritems() -%}
[{{ section }}]
{% for k, v in section_dict.iteritems() -%}
{{ k }} = {{ v }}
{% endfor -%}
{% endfor -%}
"""

    def _vivify(self):
        """
        Return an autovivification default dict.

        :return: dict
        """
        return collections.defaultdict(self._vivify)

    def _get_plugin_directory(self):
        return os.path.join(
            os.path.dirname(__file__), '..', '..', 'molecule', 'provisioner',
            'ansible', 'plugins')

    def _get_filter_plugin_directory(self):
        return os.path.join(self._get_plugin_directory(), 'filters')