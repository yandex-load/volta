import logging
import queue as q
import time
import datetime
import os
import uuid

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
            'iphone': phones.iPhone,
        }

    def detect_volta(self, config):
        """
        Args:
            config (dict): type of VoltaBox

        Returns:
            appropriate VoltaBox class for config.type
        """
        type = config.get('type')
        if not type:
            raise RuntimeError('Mandatory option volta.type not specified')
        type = type.lower()
        if type in self.voltas:
            logger.debug('Volta type detected: %s', type)
            return self.voltas[type](config)

    def detect_phone(self, config):
        """
        Args:
            config (dict): type of Phone

        Returns:
            appropriate Phone class for config.type
        """
        type = config.get('type')
        if not type:
            raise RuntimeError('Mandatory option phone.type not specified')
        type = type.lower()
        if type in self.phones:
            logger.debug('Phone type detected: %s', type)
            return self.phones[type](config)


class Core(object):
    """ Core, test performer

    Attributes:
        config (dict): test config
        test_id (string): lunapark test id
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
        """ Configures core, parse config

        Args:
            config (dict): core configuration dict
        """
        self.config = config
        if not self.config:
            raise RuntimeError('Empty config')
        self.factory = Factory()
        self.grabber_q = q.Queue()
        self.phone_q = q.Queue()
        self.grabber_listeners = []
        self.start_time = None
        self.artifacts = []
        self.artifacts_dir = config.get('artifacts_dir', "./logs")
        self.test_id = "{date}_{uuid}".format(
            date=datetime.datetime.now().strftime("%Y-%m-%d"),
            uuid=uuid.uuid4().hex
        )
        logger.info('Test id: %s', self.test_id)
        self.key_date = datetime.datetime.now().strftime("%Y-%m-%d")
        if not os.path.exists(self.artifacts_dir):
            os.makedirs(self.artifacts_dir)
        if not os.path.exists(os.path.join(self.artifacts_dir, self.test_id)):
            os.makedirs(os.path.join(self.artifacts_dir, self.test_id))
        self.currents_fname = "{artifacts_dir}/{test_id}/currents.data".format(
            artifacts_dir=self.artifacts_dir, test_id=self.test_id
        )
        self.event_types = ['event', 'sync', 'fragment', 'metric', 'unknown']
        self.event_listeners = {key:[] for key in self.event_types}
        self.event_fnames = {
            key:"{artifacts_dir}/{test_id}/{data}.data".format(
                artifacts_dir=self.artifacts_dir,
                test_id=self.test_id,
                data=key
            ) for key in self.event_types
        }

    def configure(self):
        """
        Configures modules and prepare modules for test

        pipeline:
            volta
            phone
            sync
            uploader
            report
        """
        if self.config.get('volta', {}):
            self.volta = self.factory.detect_volta(self.config.get('volta'))
        if self.config.get('phone', {}):
            self.phone = self.factory.detect_phone(self.config.get('phone'))
            self.phone.prepare()

        if self.config.get('sync', {}):
            self.config['sync']['sample_rate'] = self.volta.sample_rate
            # setup syncfinder
            self.sync_finder = SyncFinder(
                self.config.get('sync')
            )
            self.grabber_listeners.append(self.sync_finder)
            self.event_listeners['sync'].append(self.sync_finder)

        if self.config.get('uploader', {}):
            uploader_cfg = self.config.get('uploader', {})
            if not uploader_cfg.get('test_id'):
                uploader_cfg['test_id'] = self.test_id
            self.uploader = DataUploader(uploader_cfg)
            for type, fname in self.event_fnames.items():
                self.event_listeners[type].append(self.uploader)
            self.grabber_listeners.append(self.uploader)

            # create job
            create_job_data = {
                'key_date' : self.uploader.key_date,
                'test_id': self.test_id,
                'version': '2',
                'task': self.uploader.task,
                'person': self.uploader.operator,
            }
            self.uploader.create_job(create_job_data)

        self._setup_filelisteners()

    def _setup_filelisteners(self):
        logger.debug('Creating file listeners...')
        for type, fname in self.event_fnames.items():
            listener_config = {'fname': fname}
            f = FileListener(listener_config)
            self.artifacts.append(f)
            self.event_listeners[type].append(f)

        # grabber
        listener_config = {'fname': self.currents_fname}
        grabber_f = FileListener(listener_config)
        self.artifacts.append(grabber_f)
        self.grabber_listeners.append(grabber_f)

    def start_test(self):
        """
        Start test: start grabbers and process data to listeners

        pipeline:
            volta
            phone
        """
        logger.info('Starting test...')
        self.start_time = int(time.time() * 10 ** 6)

        if self.config.get('volta', {}):
            self.volta.start_test(self.grabber_q)
            # process currents thread
            self.process_currents = Tee(
                self.grabber_q,
                self.grabber_listeners,
                'currents'
            )
            self.process_currents.start()

        if self.config.get('phone', {}):
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
        if self.config.get('volta', {}):
            self.volta.end_test()
            self.process_currents.close()
        if self.config.get('phone', {}):
            self.phone.end()
            self.events_parser.close()

    def post_process(self):
        """
        Post-process actions: sync cross correlation, upload meta information

        """
        logger.info('Post process...')
        for artifact in self.artifacts:
            artifact.close()
        sync_data = {}
        if self.config.get('sync', {}):
            try:
                sync_data = self.sync_finder.find_sync_points()
            except ValueError:
                logger.error('Unable to sync', exc_info=True)
        update_job_data = {
            'test_id': self.test_id,
            'test_start': self.start_time,
            'sys_uts_offset': sync_data.get('sys_uts_offset', None),
            'log_uts_offset': sync_data.get('sys_uts_offset', None),
            'sync_sample': sync_data.get('sync_sample', None),
            'name': 'test name',
            'dsc': 'test dsc',
            'person': self.uploader.operator,
            'device_id': 'test device_id',
            'device_model': 'test device_model',
            'device_os': 'test device_os',
            'app': 'test app',
            'ver': 'test ver',
            'meta': 'teeeeest meta',
            'task': 'LOAD-272'
        }
        self.uploader.update_job(update_job_data)
        logger.info('Finished!')
