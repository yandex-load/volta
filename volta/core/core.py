import logging
import queue as q
import time
import os

from volta.core.validator import VoltaConfig
from volta.common.util import Tee
from volta.providers import boxes
from volta.providers import phones
from volta.listeners.sync.sync import SyncFinder
from volta.listeners.uploader.uploader import DataUploader
from volta.listeners.report.report import FileListener
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
        type = config.get_option('volta', 'type')
        if not type:
            raise RuntimeError('Mandatory option volta.type not specified')
        type = type.lower()
        if type in self.voltas:
            logger.debug('Volta type detected: %s', type)
            return self.voltas[type](config)
        else:
            raise RuntimeError('Unknown VoltaBox type: %s', type)

    def detect_phone(self, config):
        """
        Args:
            config (VoltaConfig): type of Phone

        Returns:
            appropriate Phone class for config.type
        """
        type = config.get_option('phone', 'type')
        if not type:
            raise RuntimeError('Mandatory option phone.type not specified')
        type = type.lower()
        if type in self.phones:
            logger.debug('Phone type detected: %s', type)
            return self.phones[type](config)
        else:
            raise RuntimeError('Unknown Phone type: %s', type)


class Core(object):
    """ Core, test performer

    Attributes:
        config (dict): test config
        test_id (string): local test id
        key_date (string): clickhouse key (sharding)
        event_types (list): currently supported event types
        event_fnames (dict): filename for FileListener for each event type
        currents_fname (string): filename for FileListener for electrical currents
        grabber_listeners (list): list of electrical currents listeners
        event_listeners (list): list of events listeners
        grabber_q (queue.Queue): queue for electrical currents
        phone_q (queue.Queue): queue for phone events
    """
    def __init__(self, config):
        SECTION = 'core'
        """ Configures core, parse config

        Args:
            config (dict): core configuration dict
        """
        self.config = VoltaConfig(config)
        self.enabled_modules = self.config.get_enabled_sections()
        if not self.config:
            raise RuntimeError('Empty config')
        self.factory = Factory()
        self._volta = None
        self._phone = None
        self._sync = None
        self._uploader = None
        self.grabber_q = q.Queue()
        self.phone_q = q.Queue()
        self.grabber_listeners = []
        self.start_time = None
        self.artifacts = []
        self.artifacts_dir = self.config.get_option(SECTION, 'artifacts_dir')
        self.test_id = self.config.get_option(SECTION, 'test_id')
        logger.info('Local test id: %s', self.config.get_option(SECTION, 'test_id'))
        self.event_types = ['event', 'sync', 'fragment', 'metric', 'unknown']
        self.event_listeners = {key:[] for key in self.event_types}

    def init_artifacts(self):
        if not os.path.exists(self.artifacts_dir):
            os.makedirs(self.artifacts_dir)
        if not os.path.exists(os.path.join(self.artifacts_dir, self.test_id)):
            os.makedirs(os.path.join(self.artifacts_dir, self.test_id))
        self.currents_fname = "{artifacts_dir}/{test_id}/currents.data".format(
            artifacts_dir=self.artifacts_dir, test_id=self.test_id
        )
        self.event_fnames = {
            key:"{artifacts_dir}/{test_id}/{data}.data".format(
                artifacts_dir=self.artifacts_dir,
                test_id=self.test_id,
                data=key
            ) for key in self.event_types
        }

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

    def add_artifact_file(self, filename):
        self.artifacts.append(filename)

    def configure(self):
        """ Configures modules and prepare modules for test """
        self.init_artifacts()
        self.volta()

        if 'phone' in self.enabled_modules:
            self.phone.prepare()

        if 'sync' in self.enabled_modules:
            self.sync.sample_rate = self.volta.sample_rate
            self.grabber_listeners.append(self.sync)
            self.event_listeners['sync'].append(self.sync)

        if 'uploader' in self.enabled_modules:
            for type, fname in self.event_fnames.items():
                self.event_listeners[type].append(self.uploader)
            self.grabber_listeners.append(self.uploader)
            self.uploader.create_job()

        self._setup_filelisteners()

    def _setup_filelisteners(self):
        logger.debug('Creating file listeners...')
        for type, fname in self.event_fnames.items():
            listener_config = {'fname': fname}
            f = FileListener(listener_config)
            self.add_artifact_file(f)
            self.event_listeners[type].append(f)

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
        if 'phone' in self.enabled_modules:
            self.phone.end()
            if self.phone_q.qsize() >= 1:
                logger.debug('qsize: %s', self.phone_q.qsize())
                logger.debug('Waiting additional 3 seconds for phone events processing...')
                time.sleep(3)
            self.events_parser.close()

    def post_process(self):
        """
        Post-process actions: sync cross correlation, upload meta information

        """
        logger.info('Post process...')
        for artifact in self.artifacts:
            artifact.close()
        sync_data = {}
        if 'sync' in self.enabled_modules:
            try:
                sync_data = self.sync.find_sync_points()
                logger.debug('Sync data: %s', sync_data)
            except ValueError:
                logger.error('Unable to sync', exc_info=True)
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
                'sys_uts_offset': sync_data.get('sys_uts_offset', None),
                'log_uts_offset': sync_data.get('sys_uts_offset', None),
                'sync_sample': sync_data.get('sync_sample', None)
            }
            self.uploader.update_job(update_job_data)
            if self.uploader.jobno:
                logger.info('Report url: %s/mobile/%s', self.uploader.hostname, self.uploader.jobno)
        logger.info('Finished!')

    def get_current_test_info(self, per_module=False):
        response = {'jobno': self.test_id, 'session_id': self.session_id}
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
                except AttributeError:
                    logger.info('Unable to get per_module %s current test info', per_module, exc_info=True)
                    pass
        return response