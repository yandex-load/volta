import logging
import queue as q
import time
import datetime
import os
import uuid

from volta import Boxes
from volta import Phones
from volta.common.eventshandler import EventsRouter
from volta.common.util import Tee
from volta.Sync.sync import SyncFinder
from volta.Uploader.uploader import DataUploader
from volta.Report.report import FileListener


logger = logging.getLogger(__name__)


class Factory(object):
    def __init__(self):
        """ find VoltaBox and Phone """
        self.voltas = {
            '500hz': Boxes.VoltaBox500Hz,
            'binary': Boxes.VoltaBoxBinary,

        }
        self.phones = {
            'android': Phones.AndroidPhone,
            'iphone': Phones.iPhone,
        }

    def detect_volta(self, config):
        type = config.get('type')
        if not type:
            raise RuntimeError('Mandatory option volta.type not specified')
        type = type.lower()
        if type in self.voltas:
            logger.debug('Volta type detected: %s', type)
            return self.voltas[type](config)

    def detect_phone(self, config):
        type = config.get('type')
        if not type:
            raise RuntimeError('Mandatory option phone.type not specified')
        type = type.lower()
        if type in self.phones:
            logger.debug('Phone type detected: %s', type)
            return self.phones[type](config)


class Core(object):
    """ Core
    Core class, test performer
    """
    def __init__(self, config):
        """ Configures core, parse config

        Parameters
        ----------
            config : dict
                core configuration dict
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
        self.test_id = "{uuid}".format(uuid=uuid.uuid4().hex)
        logger.info('Test id: %s', self.test_id)
        self.key_date = datetime.datetime.now().strftime("%Y-%m-%d")
        # TODO: should be configurable by config
        if not os.path.exists(self.key_date):
            os.makedirs(self.key_date)
        self.currents_fname = "{dir}/currents_{id}.data".format(dir=self.key_date, id=self.test_id)
        self.event_types = ['event', 'sync', 'fragment', 'metric', 'unknown']
        self.event_listeners = {key:[] for key in self.event_types}
        self.event_fnames = {
            key:"{dir}/{data}_{id}.data".format(
                dir=self.key_date,
                data=key,
                id=self.test_id
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
        self.start_time = time.time()

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
        if self.config.get('sync', {}):
            try:
                meta_data = self.sync_finder.find_sync_points()
            except ValueError:
                logger.error('Unable to sync', exc_info=True)
                meta_data = {}
            meta_data['start'] = self.start_time
            logger.info('meta: %s', meta_data)
        logger.info('Finished!')
