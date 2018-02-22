import yaml
import imp
import pkg_resources
import uuid
import datetime
import sys
import os
import logging
import pwd
from cerberus import Validator

logger = logging.getLogger(__name__)



class ValidationError(Exception):
    pass


def load_yaml_schema(path):
    # DEFAULT_FILENAME = 'schema.yaml'
    with open(path, 'r') as f:
        return yaml.load(f)

def load_py_schema(path):
    schema_module = imp.load_source('schema', path)
    return schema_module.SCHEMA

def load_schema(directory, filename=None):
    try:
        return load_yaml_schema(directory)
    except IOError:
        try:
            return load_py_schema(directory)
        except ImportError:
            raise IOError('Neither .yaml nor .py schema found in %s' % directory)


class VoltaConfig(object):
    DYNAMIC_OPTIONS = {
        'pid': lambda: os.getpid(),
        'cmdline': lambda: ' '.join(sys.argv),
        'test_id': lambda: "{date}_{uuid}".format(
            date=datetime.datetime.now().strftime("%Y-%m-%d"),
            uuid=str(uuid.uuid4())
        ),
        'key_date': lambda: datetime.datetime.now().strftime("%Y-%m-%d"),
        'operator': lambda: pwd.getpwuid(os.geteuid())[0]
    }

    def __init__(self, config, with_dynamic_options=True, core_section='core'):
        self.BASE_SCHEMA = load_yaml_schema(pkg_resources.resource_filename('volta.core', 'config/schema.yaml'))
        self._validated = None
        self.META_LOCATION = core_section
        try:
            config[self.META_LOCATION]
        except:
            config[self.META_LOCATION] = {}
        self.__raw_config_dict = config
        self.with_dynamic_options = with_dynamic_options

    def get_option(self, section, option, default=False):
        if default:
            return default
        return self.validated[section][option]

    def get_enabled_sections(self):
        return [
            section_name for section_name, section_config in self.__raw_config_dict.iteritems()
            if section_config.get('enabled', False)
        ]

    def has_option(self, section, option):
        return self.validated

    @property
    def validated(self):
        if not self._validated:
            self._validated = self.__validate()
        return self._validated

    def save(self, filename):
        with open(filename, 'w') as f:
            yaml.dump(self.validated, f)

    def __validate(self):
        return self.__validate_core()

    def __validate_core(self):
        v = Validator(self.BASE_SCHEMA)
        result = v.validate(self.__raw_config_dict, self.BASE_SCHEMA)
        if not result:
            raise ValidationError(v.errors)
        normalized = v.normalized(self.__raw_config_dict)
        return self.__set_core_dynamic_options(normalized) if self.with_dynamic_options else normalized

    def __set_core_dynamic_options(self, config):
        for option, setter in self.DYNAMIC_OPTIONS.items():
            config[self.META_LOCATION][option] = setter()
        return config