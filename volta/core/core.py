import logging
import queue as q
import time
import datetime
import os
import uuid

from volta import Boxes
from volta import Phones
from volta.common.eventshandler import EventsRouter
from volta.common.interfaces import DataListener
from volta.common.util import Tee
from volta.Sync.sync import SyncFinder
from volta.Uploader.uploader import DataUploader

logger = logging.getLogger(__name__)


# system time is index everywhere
file_output_fmt = {
    'currents': ['uts', 'value'],
    'sync': ['sys_uts', 'log_uts', 'app', 'tag', 'message'],
    'event': ['sys_uts', 'log_uts', 'app', 'tag', 'message'],
    'metric': ['sys_uts', 'log_uts', 'app', 'tag', 'value'],
    'fragment': ['sys_uts', 'log_uts', 'app', 'tag', 'message'],
    'unknown': ['sys_uts', 'message']
}


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
    Core class, test performer """
    def __init__(self, config):
        """ parse config, @type:dict """
        self.config = config
        self.factory = Factory()
        self.grabber_q = q.Queue()
        self.phone_q = q.Queue()
        self.grabber_listeners = []
        self.event_listeners = {
            'event': [],
            'sync': [],
            'fragment': [],
            'metric': [],
            'unknown': []
        }
        self.start_time = None
        self.artifacts = []
        self.test_id = "{uuid}".format(
            uuid=uuid.uuid4().hex)
        logger.info('Test id: %s', self.test_id)
        self.key_date = datetime.datetime.now().strftime("%Y-%m-%d")
        # TODO: should be configurable by config
        if not os.path.exists(self.key_date):
            os.makedirs(self.key_date)
        self.currents_fname = "{dir}/currents_{id}.data".format(dir=self.key_date, id=self.test_id)
        self.event_fnames = {
            'event': "{dir}/events_{id}.data".format(dir=self.key_date, id=self.test_id),
            'sync': "{dir}/syncs_{id}.data".format(dir=self.key_date, id=self.test_id),
            'fragment': "{dir}/fragments_{id}.data".format(dir=self.key_date, id=self.test_id),
            'metric': "{dir}/metrics_{id}.data".format(dir=self.key_date, id=self.test_id),
            'unknown': "{dir}/unknowns_{id}.data".format(dir=self.key_date, id=self.test_id)
        }

    def configure(self):
        """
        1) VoltaFactory - VOLTA-87
        2) PhoneFactory - VOLTA-120 / VOLTA-131
        3) EventLogParser - VOLTA-129
        4) Sync - VOLTA-133
        5) Uploader - VOLTA-144
        """
        self.volta = self.factory.detect_volta(self.config.get('volta', {}))
        self.phone = self.factory.detect_phone(self.config.get('phone', {}))
        self.phone.prepare()

        # setup syncfinder
        self.sync_finder = SyncFinder(
            self.config.get('sync', {}),
            self.volta.sample_rate
        )
        self.grabber_listeners.append(self.sync_finder)
        self.event_listeners['sync'].append(self.sync_finder)
        self._setup_filelisteners()

        self.uploader = DataUploader(self.config.get('uploader', {}), self.test_id)
        for type, fname in self.event_fnames.items():
            self.event_listeners[type].append(self.uploader)
        self.grabber_listeners.append(self.uploader)

    def _setup_filelisteners(self):
        logger.debug('Creating file listeners...')
        for type, fname in self.event_fnames.items():
            f = FileListener(fname)
            self.artifacts.append(f)
            self.event_listeners[type].append(f)

        # grabber
        grabber_f = FileListener(self.currents_fname)
        self.artifacts.append(grabber_f)
        self.grabber_listeners.append(grabber_f)

    def start_test(self):
        logger.info('Starting test...')
        self.start_time = time.time()

        self.volta.start_test(self.grabber_q)
        self.phone.start(self.phone_q)

        logger.info('Starting test apps and waiting for finish...')
        self.phone.run_test()

        # process phone queue thread
        self.events_parser = EventsRouter(self.phone_q, self.event_listeners)
        self.events_parser.start()

        # process currents thread
        self.process_currents = Tee(
            self.grabber_q,
            self.grabber_listeners,
            'currents'
        )
        self.process_currents.start()

    def end_test(self):
        logger.info('Finishing test...')
        self.volta.end_test()
        self.phone.end()
        self.events_parser.close()
        self.process_currents.close()

    def post_process(self):
        logger.info('Post process...')
        for artifact in self.artifacts:
            artifact.close()
        try:
            meta_data = self.sync_finder.find_sync_points()
        except ValueError:
            logger.error('Unable to sync', exc_info=True)
            meta_data = {}
        meta_data['start'] = self.start_time
        logger.info('meta: %s', meta_data)
        logger.info('Finished!')


class FileListener(DataListener):
    """
    Default listener - saves data to file
    """

    def __init__(self, fname):
        DataListener.__init__(self, fname)
        self.fname = open(fname, 'w')
        self.closed = None
        self.init_header = True
        self.output_separator = '\t'

    def put(self, df, type):
        if not self.closed:
            data = df.to_csv(
                sep=self.output_separator,
                header=self.init_header,
                index=False,
                columns=file_output_fmt.get(type, [])
            )
            self.init_header = False
            self.fname.write((data))
            self.fname.flush()

    def close(self):
        """ close open files """
        self.closed = True
        if self.fname:
            self.fname.close()

