""" iPhone phone worker
"""
import logging
import queue as q
import re

from volta.common.interfaces import Phone
from volta.common.util import Drain, popen, chunk_to_df, LogReader


logger = logging.getLogger(__name__)


iphone_logevent_re = re.compile(r"""
    ^(?P<month>\S+)
    \s+
    (?P<date>\S+)
    \s+
    (?P<time>\S+)
    \s+
    (?P<message>.*)
    $
    """, re.VERBOSE | re.IGNORECASE
)


class iPhone(Phone):
    """ iPhone worker class - work w/ phone, read phone logs, store data

    Attributes:
        source (string): path to data source, cfgutil id for iphones
        unplug_type (string, optional): type of test execution - NOT available at the moment for now
            `auto`: disable battery charge (by software) or use special USB cord limiting charge over USB
        path_to_util (string, optional): path to Apple Configurators' cfgutil

    Todo:
        unlug_type manual
    """
    def __init__(self, config):
        """
        Args:
            config (dict): module configuration data
        """
        Phone.__init__(self, config)
        self.log_stdout_reader = None
        self.log_stderr_reader = None
        self.path_to_util = config.get('util', "/Applications/Apple\ Configurator\ 2.app/Contents/MacOS/")
        self.source = config.get('source', '0x6382910F98C26')
        # self.unplug_type = config.get('unplug_type', 'auto')

    def prepare(self):
        """ this method skipped by iphone - instruments do the thing """
        return

    def start(self, results):
        """ Grab stage: starts log reader

        pipeline:
            start async logcat reader

        Args:
            results (queue-like object): Phone should put there dataframes, format: ['sys_uts', 'message']
        """

        self.phone_q = results
        self.__start_async_log()

    def run_test(self):
        """ this method skipped by iphone because instruments do the thing """
        return

    def end(self):
        """ pipeline: stop async log process, readers and queues """
        self.log_reader_stdout.close()
        self.log_reader_stderr.close()
        self.log_process.kill()
        self.drain_log_stdout.close()
        self.drain_log_stderr.close()

    def __start_async_log(self):
        """ Start logcat read in subprocess and make threads to read its stdout/stderr to queues """
        cmd = "{path}cfgutil -e {device_id} syslog".format(
            path=self.path_to_util,
            device_id=self.source
        )
        logger.debug("Execute : %s", cmd)
        self.log_process = popen(cmd)

        self.log_reader_stdout = LogReader(self.log_process.stdout, iphone_logevent_re)
        self.drain_log_stdout = Drain(self.log_reader_stdout, self.phone_q)
        self.drain_log_stdout.start()

        self.phone_q_err=q.Queue()
        self.log_reader_stderr = LogReader(self.log_process.stderr, iphone_logevent_re)
        self.drain_log_stderr = Drain(self.log_reader_stderr, self.phone_q_err)
        self.drain_log_stderr.start()
