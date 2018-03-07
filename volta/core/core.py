import logging
import queue as q
import time
import os
import shutil

from netort.data_processing import Tee
from netort.validated_config import ValidatedConfig as VoltaConfig
from config.dynamic_options import DYNAMIC_OPTIONS

from volta.providers import boxes
from volta.providers import phones
from volta.listeners.sync.sync import SyncFinder
from volta.listeners.uploader.uploader import DataUploader
from volta.listeners.report.report import FileListener
from volta.listeners.console import ConsoleListener
from volta.mappers.events.router import EventsRouter


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

    def detect_volta(self, config):
        """
        Args:
            config (VoltaConfig): type of VoltaBox

        Returns:
            appropriate VoltaBox class for config.type
        """
        type_ = config.get_option('volta', 'type')
        if not type_:
            raise RuntimeError('Mandatory option volta.type not specified')
        type_ = type_.lower()
        if type_ in self.voltas:
            logger.debug('Volta type detected: %s', type_)
            return self.voltas[type_](config)
        else:
            raise RuntimeError('Unknown VoltaBox type: %s', type_)

    def detect_phone(self, config):
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
            return self.phones[type_](config)
        else:
            raise RuntimeError('Unknown Phone type: %s', type_)


class Core(object):
    """ Core, test performer

    Attributes:
        config (dict): test config
        test_id (string): local test id
        event_types (list): currently supported event types
        event_fnames (dict): filename for FileListener for each event type
        currents_fname (string): filename for FileListener for electrical currents
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
        self.config = VoltaConfig(config, DYNAMIC_OPTIONS, self.PACKAGE_SCHEMA_PATH)
        self.enabled_modules = self.config.get_enabled_sections()
        self.test_id = self.config.get_option(self.SECTION, 'test_id')
        logger.info('Local test id: %s', self.test_id)
        if not self.config:
            raise RuntimeError('Empty config')
        self.factory = Factory()
        self._volta = None
        self._phone = None
        self._sync = None
        self._uploader = None
        self._console = None
        self.grabber_q = q.Queue()
        self.phone_q = q.Queue()
        self.grabber_listeners = []
        self.start_time = None
        self.artifacts = []
        self._artifacts_dir = None
        self._sync_points = {}
        self.event_types = ['event', 'sync', 'fragment', 'metric', 'unknown']
        self.event_listeners = {key: [] for key in self.event_types}
        self.currents_fname = "{artifacts_dir}/currents.data".format(
            artifacts_dir=self.artifacts_dir
        )
        self.event_fnames = {
            key: "{artifacts_dir}/{data}.data".format(
                artifacts_dir=self.artifacts_dir,
                data=key
            ) for key in self.event_types
        }
        self.process_currents = None
        self.events_parser = None
        self.finished = None

    @property
    def artifacts_dir(self):
        if not self._artifacts_dir:
            dir_name = "{dir}/{id}".format(dir=self.config.get_option(self.SECTION, 'artifacts_dir'), id=self.test_id)
            if not os.path.isdir(dir_name):
                os.makedirs(dir_name)
            os.chmod(dir_name, 0o755)
            self._artifacts_dir = os.path.abspath(dir_name)
        return self._artifacts_dir

    def __test_id_link_to_jobno(self, name):
        link_dir = os.path.join(self.config.get_option(self.SECTION, 'artifacts_dir'), 'lunapark')
        if not os.path.exists(link_dir):
            os.makedirs(link_dir)
        os.symlink(
            os.path.relpath(self.artifacts_dir, link_dir),
            os.path.join(link_dir, str(name))
        )

    @property
    def volta(self):
        if not self._volta:
            self._volta = self.factory.detect_volta(self.config)
        return self._volta

    @property
    def phone(self):
        if not self._phone:
            self._phone = self.factory.detect_phone(self.config)
        return self._phone

    @property
    def sync(self):
        if not self._sync:
            self._sync = SyncFinder(self.config)
        return self._sync

    @property
    def uploader(self):
        if not self._uploader:
            self._uploader = DataUploader(self.config)
        return self._uploader

    @property
    def console(self):
        if not self._console:
            self._console = ConsoleListener(self.config)
        return self._console

    @property
    def sync_points(self):
        if not 'sync' in self.enabled_modules:
            return {}
        if not self._sync_points:
            self._sync_points = self.sync.find_sync_points()
        return self._sync_points

    def add_artifact_file(self, filename):
        if filename:
            logger.debug('Adding %s to artifacts', filename.fname)
            self.artifacts.append(filename)

    def configure(self):
        """ Configures modules and prepare modules for test """
        if 'uploader' in self.enabled_modules:
            self.uploader.create_job()
            for type_, fname in self.event_fnames.items():
                self.event_listeners[type_].append(self.uploader)
            self.grabber_listeners.append(self.uploader)

        if 'phone' in self.enabled_modules:
            self.phone.prepare()

        if 'sync' in self.enabled_modules:
            self.sync.sample_rate = self.volta.sample_rate
            self.grabber_listeners.append(self.sync)
            self.event_listeners['sync'].append(self.sync)

        if 'console' in self.enabled_modules:
            for type_, fname in self.event_fnames.items():
                self.event_listeners[type_].append(self.console)
            self.grabber_listeners.append(self.console)

        self._setup_filelisteners()
        return 0

    def _setup_filelisteners(self):
        logger.debug('Creating file listeners...')
        for type_, fname in self.event_fnames.items():
            listener_config = {'fname': fname}
            f = FileListener(listener_config)
            self.add_artifact_file(f)
            self.event_listeners[type_].append(f)

        listener_config = {'fname': self.currents_fname}
        grabber_f = FileListener(listener_config)
        self.add_artifact_file(grabber_f)
        self.grabber_listeners.append(grabber_f)

    def start_test(self):
        """ Start test: start grabbers and process data to listeners """
        logger.info('Starting test...')
        self.start_time = int(time.time() * 10 ** 6)

        if 'volta' in self.enabled_modules:
            self.volta.start_test(self.grabber_q)
            # process currents thread
            self.process_currents = Tee(
                self.grabber_q,
                self.grabber_listeners,
                'currents'
            )
            self.process_currents.start()

        if 'phone' in self.enabled_modules:
            self.phone.start(self.phone_q)
            logger.info('Starting test apps and waiting for finish...')
            self.phone.run_test()
            # process phone queue thread
            self.events_parser = EventsRouter(self.phone_q, self.event_listeners)
            self.events_parser.start()

    def end_test(self):
        """
        Interrupts test: stops grabbers and events parsers
        """
        logger.info('Finishing test...')
        if 'volta' in self.enabled_modules:
            self.volta.end_test()
            self.process_currents.close()
            self.process_currents.join()
        if 'phone' in self.enabled_modules:
            self.phone.end()
            if self.events_parser:
                self.events_parser.close()
                self.events_parser.join()

    def post_process(self):
        """
        Post-process actions: sync cross correlation, upload meta information

        """
        logger.info('Post process...')

        [artifact.close() for artifact in self.artifacts]
        if 'uploader' in self.enabled_modules:
            update_job_data = {
                'test_id': self.config.get_option('core', 'test_id'),
                'test_start': self.start_time,
                'name': self.config.get_option('uploader', 'name'),
                'dsc': self.config.get_option('uploader', 'dsc'),
                'person': self.config.get_option('core', 'operator'),
                'device_id': self.config.get_option('uploader', 'device_id'),
                'device_model': self.config.get_option('uploader', 'device_model'),
                'device_os': self.config.get_option('uploader', 'device_os'),
                'app': self.config.get_option('uploader', 'app'),
                'ver': self.config.get_option('uploader', 'ver'),
                'meta': self.config.get_option('uploader', 'meta'),
                'task': self.config.get_option('uploader', 'task'),
                'sys_uts_offset': self.sync_points.get('sys_uts_offset', None),
                'log_uts_offset': self.sync_points.get('log_uts_offset', None),
                'sync_sample': self.sync_points.get('sync_sample', None)
            }
            self.uploader.update_job(update_job_data)
            if self.uploader.jobno:
                logger.info('Report url: %s/mobile/%s', self.uploader.hostname, self.uploader.jobno)
                self.__test_id_link_to_jobno(self.uploader.jobno)
            self.uploader.close()
        logger.info('Finished!')

    def get_current_test_info(self, per_module=False, session_id=None):
        response = {'jobno': self.test_id, 'session_id': session_id}
        if per_module:
            for module in self.enabled_modules:
                try:
                    if module == 'volta':
                        response[module] = self.volta.get_info()
                        response['currents_parser_alive'] = self.process_currents.isAlive()
                    elif module == 'phone':
                        response[module] = self.phone.get_info()
                        response['events_parser_alive'] = self.events_parser.get_info()
                    elif module == 'uploader':
                        response['api_url'] = "{api}/mobile/{jobno}".format(
                            api=self.uploader.hostname,
                            jobno=self.uploader.jobno
                        )
                        response['api_jobno'] = "{jobno}".format(jobno=self.uploader.jobno)
                        response['uploader_sender_alive'] = self.uploader.worker.isAlive()
                except AttributeError:
                    logger.info('Unable to get per_module %s current test info', per_module, exc_info=True)
                    pass
        return response

    def collect_file(self, filename, keep_original=False):
        """
        Move or copy single file to artifacts dir
        """
        dest = self.artifacts_dir + '/' + os.path.basename(filename)
        logger.debug("Collecting file: %s to %s", filename, dest)
        if not filename or not os.path.exists(filename):
            logger.warning("File not found to collect: %s", filename)
            return

        if os.path.exists(dest):
            # FIXME: find a way to store artifacts anyway
            logger.warning("File already exists: %s", dest)
            return

        if keep_original:
            shutil.copy(filename, self.artifacts_dir)
        else:
            shutil.move(filename, self.artifacts_dir)

        os.chmod(dest, 0o644)
