import logging
import requests
import queue as q
import threading
import time

from urlparse import urlparse
from volta.common.interfaces import DataListener
from volta.common.util import get_nowait_from_queue

from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


logger = logging.getLogger(__name__)


class DataUploader(DataListener):
    """ Uploads data to Clickhouse
    have non-interface private method __upload_meta() for meta information upload
    """
    JOBNO_FNAME = 'jobno.log'

    def __init__(self, config):
        super(DataUploader, self).__init__(config)
        self.config = config
        self.addr = self.config.get_option('uploader', 'address')
        self.hostname = urlparse(self.addr).scheme+'://'+urlparse(self.addr).netloc
        self.task = self.config.get_option('uploader', 'task')
        self.test_id = self.config.get_option('core', 'test_id')
        self.key_date = self.config.get_option('core', 'key_date')
        self.create_job_url = self.config.get_option('uploader', 'create_job_url')
        self.update_job_url = self.config.get_option('uploader', 'update_job_url')
        self.data_types_to_tables = {
            'currents': 'volta.currents',
            'sync': 'volta.syncs',
            'event': 'volta.events',
            'metric': 'volta.metrics',
            'fragment': 'volta.fragments',
            'unknown': 'volta.logentries'
        }
        self.clickhouse_output_fmt = {
            'currents': ['key_date', 'test_id', 'uts', 'value'],
            'sync': ['key_date', 'test_id', 'sys_uts', 'log_uts', 'app', 'tag', 'message'],
            'event': ['key_date', 'test_id', 'sys_uts', 'log_uts', 'app', 'tag', 'message'],
            'metric': ['key_date', 'test_id', 'sys_uts', 'log_uts', 'app', 'tag', 'value'],
            'fragment': ['key_date', 'test_id', 'sys_uts', 'log_uts', 'app', 'tag', 'message'],
            'unknown': ['key_date', 'test_id', 'sys_uts', 'message']
        }
        self.operator = config.get_option('core', 'operator')
        self.jobno = None
        self.inner_queue = q.Queue()
        self.worker = WorkerThread(self)
        self.worker.start()

    def put(self, data, type):
        self.inner_queue.put((data, type))

    def create_job(self):
        data = {
            'key_date' : self.config.get_option('core', 'key_date'),
            'test_id': self.config.get_option('core', 'test_id'),
            'version': self.config.get_option('core', 'version'),
            'task': self.config.get_option('uploader', 'task'),
            'person': self.config.get_option('core', 'operator'),
            'component': self.config.get_option('uploader', 'component')
        }
        url = "{url}{path}".format(url=self.hostname, path=self.create_job_url)
        req = requests.post(url, data=data, verify=False)
        logger.debug('Lunapark create job status: %s', req.status_code)
        logger.debug('Req data: %s\nAnsw data: %s', data, req.json())
        req.raise_for_status()

        if req.json()['success'] == False:
            raise RuntimeError('Lunapark id not created: %s' % req.json()['error'])
        else:
            self.jobno = req.json()['jobno']
            logger.info('Lunapark test id: %s', self.jobno)
            logger.info('Report url: %s/mobile/%s', self.hostname, self.jobno)
            self.dump_jobno_to_file()

    def dump_jobno_to_file(self):
        try:
            with open(self.JOBNO_FNAME, 'w') as jobnofile:
                jobnofile.write(
                    "{path}/mobile/{jobno}".format(path=self.hostname, jobno=self.jobno)
                )
        except Exception:
            logger.error('Failed to dump jobno to file: %s', self.JOBNO_FNAME, exc_info=True)

    def update_job(self, data):
        url = "{url}{path}".format(url=self.hostname, path=self.update_job_url)
        req = requests.post(url, data=data, verify=False)
        logger.debug('Lunapark update job status: %s', req.status_code)
        logger.debug('Req data: %s\nAnsw data: %s', data, req.json())
        req.raise_for_status()
        return

    def get_info(self):
        """ mock """
        pass

    def close(self):
        self.worker.stop()
        while not self.worker.is_finished():
            logger.debug('Processing pending uploader queue... qsize: %s', self.inner_queue.qsize())
        logger.debug('Joining uploader thread...')
        self.worker.join()
        logger.info('Uploader finished!')


class WorkerThread(threading.Thread):
    """ Process data

    read data from queue (each chunk is a tuple of (data,type)), send contents to clickhouse via http
        - data (pandas.DataFrame): dfs w/ data contents,
            differs for each data type.
            Should be processed differently from each other
        - type (string): dataframe type
    """
    def __init__(self, uploader):
        super(WorkerThread, self).__init__()
        self._finished = threading.Event()
        self._interrupted = threading.Event()
        self.uploader = uploader

    def run(self):
        while not self._interrupted.is_set():
            self.__get_from_queue_prepare_and_send()
        logger.info('Uploader thread main loop interrupted, '
                    'finishing work and trying to send the rest of data, qsize: %s',
                    self.uploader.inner_queue.qsize())
        self.__get_from_queue_prepare_and_send()
        self._finished.set()

    def __get_from_queue_prepare_and_send(self):
        pending_batch = self.__prepare_batch_of_chunks(
            get_nowait_from_queue(self.uploader.inner_queue)
        )
        for type_ in self.uploader.data_types_to_tables:
            if pending_batch[type_]:
                prepared_body = "".join(key for key in pending_batch[type_])
                url = "{addr}/?query={query}".format(
                    addr=self.uploader.addr,
                    query="INSERT INTO {table} FORMAT TSV".format(
                        table=self.uploader.data_types_to_tables[type_])
                )
                self.__send_chunk(url, prepared_body)

    def __prepare_batch_of_chunks(self, q_data):
        pending_data = {}
        for type_ in self.uploader.data_types_to_tables:
            pending_data[type_] = []
        for data, type_ in q_data:
            if data.empty:
                continue
            if type_ in self.uploader.data_types_to_tables:
                data.loc[:, ('key_date')] = self.uploader.key_date
                data.loc[:, ('test_id')] = self.uploader.test_id
                data = data.to_csv(
                    sep='\t',
                    header=False,
                    index=False,
                    na_rep="",
                    columns=self.uploader.clickhouse_output_fmt.get(type_, [])
                )
                pending_data[type_].append(data)
            else:
                logger.warning('Unknown data type for DataUplaoder, dropped: %s', exc_info=True)
        return pending_data

    def __send_chunk(self, url, data, timeout=10):
        """ TODO: add more stable and flexible retries """
        try:
            r = requests.post(url, data=data, verify=False, timeout=timeout)
        except requests.ConnectionError, requests.ConnectTimeout:
            logger.debug('Connection error, retrying in 1 sec...', exc_info=True)
            time.sleep(1)
            try:
                r = requests.post(url, data=data, verify=False, timeout=timeout)
            except:
                logger.warning('Failed retrying sending data. Dropped', exc_info=True)
        else:
            if r.status_code != 200:
                logger.warning('Request w/ bad status code: %s. Error message:\n%s. Data: %s',
                               r.status_code, r.text, data
                               )
            r.raise_for_status()

    def is_finished(self):
        return self._finished

    def stop(self):
        logger.info('Uploader got interrupt signal')
        self._interrupted.set()
