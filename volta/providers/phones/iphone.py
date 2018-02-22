""" iPhone phone worker
"""
import logging
import re
import time

from netort.data_processing import Drain, get_nowait_from_queue

from volta.common.interfaces import Phone
from volta.common.util import Executioner, LogParser


logger = logging.getLogger(__name__)


iphone_logevent_re = r"""
    ^(?P<month>\S+)
    \s+
    (?P<date>\S+)
    \s+
    (?P<time>\S+)
    \s+
    \S+
    \s+
    (?P<message>.*)
    $
    """


class iPhone(Phone):
    """ iPhone worker class - work w/ phone, read phone logs, store data

    Attributes:
        source (string): path to data source, cfgutil id for iphones
        path_to_util (string, optional): path to Apple Configurators' cfgutil

    Todo:
        unlug_type manual
    """
    def __init__(self, config):
        """
        Args:
            config (VoltaConfig): module configuration data
        """
        Phone.__init__(self, config)
        self.log_stdout_reader = None
        self.log_stderr_reader = None
        self.drain_log_stdout = None
        self.path_to_util = config.get_option('phone', 'util')
        self.source = config.get_option('phone', 'source')
        self.phone_q = None
        try:
            self.compiled_regexp = re.compile(
                config.get_option('phone', 'event_regexp', iphone_logevent_re), re.VERBOSE | re.IGNORECASE
            )
        except SyntaxError:
            logger.debug('Unable to parse specified regexp', exc_info=True)
            raise RuntimeError(
                "Unable to parse specified regexp: %s" % config.get_option('phone', 'event_regexp', iphone_logevent_re)
            )
        self.__test_interaction_with_phone()

    def __test_interaction_with_phone(self):
        def read_process_queues_and_report(outs_q, errs_q):
            outputs = get_nowait_from_queue(outs_q)
            for chunk in outputs:
                logger.debug('Command output: %s', chunk.strip('\n'))
                if chunk.strip('\n') == 'unknown':
                    worker.close()
                    raise RuntimeError(
                        'Phone "%s" has an unknown state. Please check device authorization and state' % self.source
                    )

            errors = get_nowait_from_queue(errs_q)
            if errors:
                worker.close()
                raise RuntimeError(
                    'There were errors trying to test connection to the phone %s. Errors :%s' % (
                        self.source, errors
                    )
                )
        cmd = "{path}cfgutil -e {device_id} list".format(path=self.path_to_util, device_id=self.source)
        # get-state
        worker = Executioner(cmd)
        outs_q, errs_q = worker.execute()
        while worker.is_finished() is None:
            read_process_queues_and_report(outs_q, errs_q)
            time.sleep(1)
        read_process_queues_and_report(outs_q, errs_q)
        while not outs_q.qsize() != 0 and errs_q.qsize() != 0:
            time.sleep(0.5)
        worker.close()
        logger.info('Command \'%s\' executed on device %s. Retcode: %s', cmd, self.source, worker.is_finished())

    def prepare(self):
        """ this method skipped by iphone - instruments do the thing """
        return

    def start(self, results):
        """ Grab stage: starts log reader

        pipeline:
            start async reader

        Args:
            results (queue-like object): Phone should put there dataframes, format: ['sys_uts', 'message']
        """

        self.phone_q = results
        self.__start_async_log()

    def run_test(self):
        """ App stage: run app/phone tests """
        return

    def end(self):
        """ pipeline: stop async log process, readers and queues """
        self.worker.close()
        if self.logcat_pipeline:
            self.logcat_pipeline.close()

    def __start_async_log(self):
        """ Start logcat read in subprocess and make threads to read its stdout/stderr to queues """
        cmd = "{path}cfgutil -e {device_id} syslog".format(
            path=self.path_to_util,
            device_id=self.source
        )
        self.worker = Executioner(cmd)
        out_q, err_q = self.worker.execute()

        self.logcat_pipeline = Drain(
            LogParser(
                out_q, self.compiled_regexp, self.config.get_option('phone', 'type')
            ),
            self.phone_q
        )
        self.logcat_pipeline.start()

    def get_info(self):
        data = {}
        if self.drain_log_stdout:
            data['grabber_alive'] = self.drain_log_stdout.isAlive()
        if self.phone_q:
            data['grabber_queue_size'] = self.phone_q.qsize()
        return data
