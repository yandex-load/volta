import logging
import queue as q
import time
import pkg_resources
import threading

from netort.validated_config import ValidatedConfig as VoltaConfig

from netort import data_manager

from volta.core.config.dynamic_options import DYNAMIC_OPTIONS
from volta.providers import boxes
from volta.providers import phones
from volta.listeners.sync.sync import SyncFinder
from volta.listeners.console import ConsoleListener


logger = logging.getLogger(__name__)


class Factory(object):
    """ Finds appropriate class for Volta and Phone

    Attributes:
        voltas (dict): binds config volta types to appropriate VoltaBox classes
        phones (dict): binds config phone types to appropriate Phone classes
    """
    def __init__(self):
        """ find VoltaBox and Phone """
        self.voltas = {
            '500hz': boxes.VoltaBox500Hz,
            'binary': boxes.VoltaBoxBinary,
            'stm32': boxes.VoltaBoxStm32,

        }
        self.phones = {
            'android': phones.AndroidPhone,
            'android_old': phones.AndroidOldPhone,
            'iphone': phones.iPhone,
            'nexus4': phones.Nexus4,
        }

    def detect_volta(self, config, core):
        """
        Args:
            config (VoltaConfig): type of VoltaBox
            core (Core): Core object

        Returns:
            appropriate VoltaBox class for config.type
        """
        type_ = config.get_option('volta', 'type')
        if not type_:
            raise RuntimeError('Mandatory option volta.type not specified')
        type_ = type_.lower()
        if type_ in self.voltas:
            logger.debug('Volta type detected: %s', type_)
            return self.voltas[type_](config, core)
        else:
            raise RuntimeError('Unknown VoltaBox type: %s', type_)

    def detect_phone(self, config, core):
        """
        Args:
            config (VoltaConfig): type of Phone

        Returns:
            appropriate Phone class for config.type
        """
        type_ = config.get_option('phone', 'type')
        if not type_:
            raise RuntimeError('Mandatory option phone.type not specified')
        type_ = type_.lower()
        if type_ in self.phones:
            logger.debug('Phone type detected: %s', type_)
            return self.phones[type_](config, core)
        else:
            raise RuntimeError('Unknown Phone type: %s', type_)


class Core(object):
    """ Core, test performer

    Attributes:
        config (dict): test config
        event_types (list): currently supported event types
        grabber_listeners (list): list of electrical currents listeners
        event_listeners (list): list of events listeners
        grabber_q (queue.Queue): queue for electrical currents
        phone_q (queue.Queue): queue for phone events
    """
    SECTION = 'core'
    PACKAGE_SCHEMA_PATH = 'volta.core'

    def __init__(self, config):
        """ Configures core, parse config

        Args:
            config (dict): core configuration dict
        """
        try:
            logger.info('Running Volta==%s', pkg_resources.get_distribution("volta").version)
        except AttributeError:
            pass
        self.config = VoltaConfig(config, DYNAMIC_OPTIONS, self.PACKAGE_SCHEMA_PATH)
        self.data_session = data_manager.DataSession(
            {
                'clients': [
                    {
                        'type': 'luna',
                        'api_address': 'https://volta-back-testing.common-int.yandex-team.ru',
                        'user_agent': 'Tank Test',
                    },
                    {
                        'type': 'local_storage',
                    },
                    {
                        'type': 'lunapark_volta',
                        'api_address': self.config.get_option('uploader', 'address'),
                        'task': 'LOAD-272'
                    }
                ],
                # 'artifacts_base_dir': './logs',
                # 'operator': 'operator'
            }
        )
        self.enabled_modules = []
        self.config_enabled = self.config.get_enabled_sections()
        if not self.config:
            raise RuntimeError('Empty config')

        self.factory = Factory()

        self._volta = None
        self._phone = None
        self._sync = None
        self._console = None

        self.grabber_q = q.Queue()
        self.phone_q = q.Queue()

        self.start_time = None

        self._sync_points = {}

        self.finished = None

    @property
    def volta(self):
        if not self._volta:
            self._volta = self.factory.detect_volta(self.config, self)
        return self._volta

    @property
    def phone(self):
        if not self._phone:
            self._phone = self.factory.detect_phone(self.config, self)
        return self._phone

    @property
    def sync(self):
        if not self._sync:
            self._sync = SyncFinder(self.config)
        return self._sync

    @property
    def console(self):
        if not self._console:
            self._console = ConsoleListener(self.config)
        return self._console

    @property
    def sync_points(self):
        if 'sync' not in self.config_enabled:
            return {}
        if not self._sync_points:
            try:
                sync_pts = self.sync.find_sync_points()
            except ValueError:
                logger.warning('Unable to find sync points!', exc_info=True)
            else:
                self._sync_points = sync_pts
        return self._sync_points

    def configure(self):
        """ Configures modules and prepare modules for test """
        if 'phone' in self.config_enabled:
            self.enabled_modules.append(self.phone)
            self.phone.prepare()

        if 'sync' in self.config_enabled:
            self.enabled_modules.append(self.sync)
            self.sync.sample_rate = self.volta.sample_rate

        if 'console' in self.config_enabled:
            self.enabled_modules.append(self.console)

    def start_test(self):
        """ Start test: start grabbers and process data to listeners """
        logger.info('Starting test...')
        self.data_session.start_time = int(time.time() * 10 ** 6)

        if 'volta' in self.config_enabled:
            self.volta.start_test(self.grabber_q)

        if 'phone' in self.config_enabled:
            self.phone.start(self.phone_q)
            logger.info('Starting test apps and waiting for finish...')
            self.phone.run_test()

    def end_test(self):
        """
        Interrupts test: stops grabbers and events parsers
        """
        logger.info('Finishing test...')
        if 'volta' in self.config_enabled:
            self.volta.end_test()
        if 'phone' in self.config_enabled:
            self.phone.end()

    def post_process(self):
        """
        Post-process actions: sync cross correlation, upload meta information

        """
        logger.info('Post process...')
        if 'uploader' in self.config_enabled:
            self.data_session.update_job(
                dict(
                    name=self.config.get_option('uploader', 'name'),
                    dsc=self.config.get_option('uploader', 'dsc'),
                    person=self.config.get_option('core', 'operator'),
                    device_id=self.config.get_option('uploader', 'device_id'),
                    device_model=self.config.get_option('uploader', 'device_model'),
                    device_os=self.config.get_option('uploader', 'device_os'),
                    app=self.config.get_option('uploader', 'app'),
                    ver=self.config.get_option('uploader', 'ver'),
                    meta=self.config.get_option('uploader', 'meta'),
                    task=self.config.get_option('uploader', 'task'),
                    sys_uts_offset=self.sync_points.get('sys_uts_offset', None),
                    log_uts_offset=self.sync_points.get('log_uts_offset', None),
                    sync_sample=self.sync_points.get('sync_sample', None)
                )
            )
        if 'sync' in self.config_enabled:
            self.data_session.update_metric(
                dict(
                    sys_uts_offset=self.sync_points.get('offset', None),
                    log_uts_offset=self.sync_points.get('log_offset', None),
                    sync_sample=self.sync_points.get('sync_sample', None)
                )
            )
        [module_.close() for module_ in self.enabled_modules]
        self.data_session.close()

        logger.info('Threads still running: %s', threading.enumerate())
        if threading.enumerate() > 1:
            logger.info('More than 1 threads still running: %s', threading.enumerate())
            logger.debug('Waiting 10 more seconds till all threads finish their work')
            tries_before_exit = 0
            while len(threading.enumerate()) > 1:
                if tries_before_exit > 10 or len(threading.enumerate()) == 1:
                    break
                logger.debug('More than 1 threads still running: %s', threading.enumerate())
                time.sleep(1)
                tries_before_exit = tries_before_exit + 1
            else:
                logger.info('Finished!')

    def get_current_test_info(self, per_module=False, session_id=None):
        response = {'jobno': self.data_session.job_id, 'session_id': session_id}
        if per_module:
            for module in self.config_enabled:
                try:
                    if module == 'volta':
                        response[module] = self.volta.get_info()
                    elif module == 'phone':
                        response[module] = self.phone.get_info()
                    #elif module == 'uploader':
                    #    response['api_url'] = "{api}/mobile/{jobno}".format(
                    #        api=self.uploader.hostname,
                    #        jobno=self.uploader.jobno
                    #    )
                    #    response['api_jobno'] = "{jobno}".format(jobno=self.uploader.jobno)
                    #    response['uploader_sender_alive'] = self.uploader.worker.isAlive()
                except AttributeError:
                    logger.info('Unable to get per_module %s current test info', per_module, exc_info=True)
                    pass
        return response
