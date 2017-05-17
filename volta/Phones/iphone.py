""" iPhone phone worker
"""
import logging
import time
import queue as q
import pandas as pd
import datetime

from volta.common.interfaces import Phone
from volta.common.util import Drain, popen


logger = logging.getLogger(__name__)


class iPhone(Phone):
    def __init__(self, config):
        Phone.__init__(self, config)
        self.log_stdout_reader = None
        self.log_stderr_reader = None
        self.path_to_util = "/Applications/Apple\ Configurator\ 2.app/Contents/MacOS/"
        # mandatory options
        self.source = config.get('source', '0x6382910F98C26')
        # self.unplug_type = config.get('unplug_type', 'auto')

    def prepare(self):
        return

    def start(self, phone_q):
        """
        pipeline:
            start async logcat reader
        """
        self.phone_q = phone_q
        self.__start_async_log()

    def run_test(self):
        return

    def end(self):
        """
        pipeline:
            stop async logcat process, readers and queues
        """

        self.log_reader_stdout.close()
        self.log_reader_stderr.close()
        self.log_process.kill()
        self.drain_log_stdout.close()
        self.drain_log_stderr.close()

    def __start_async_log(self):
        """
        Start logcat read in subprocess and make threads to read its stdout/stderr to queues

        """
        cmd = "{path}cfgutil -e {device_id} syslog".format(
            path=self.path_to_util,
            device_id=self.source
        )
        logger.debug("Execute : %s", cmd)
        self.log_process = popen(cmd)

        self.log_reader_stdout = LogReader(self.log_process.stdout)
        self.drain_log_stdout = Drain(self.log_reader_stdout, self.phone_q)
        self.drain_log_stdout.start()

        self.phone_q_err=q.Queue()
        self.log_reader_stderr = LogReader(self.log_process.stderr)
        self.drain_log_stderr = Drain(self.log_reader_stderr, self.phone_q_err)
        self.drain_log_stderr.start()


def string_to_df(chunk):
    results = []
    df = None
    for line in chunk.split('\n'):
        try:
            # TODO regexp should be here, just like in eventshandler
            # input format:
            # Apr 13 14:17:18 Benders-iPhone kernel(AppleBiometricSensor)[0] <Debug>: exit
            ts = datetime.datetime.strptime(line[:15], '%b %d %H:%M:%S').replace(year=datetime.datetime.now().year)
            sys_uts = int(
                (ts-datetime.datetime(1970,1,1)).total_seconds() * 10 ** 6
            )
            message = line[15:]
        except:
            logger.error('cfgutil log parsing exception', exc_info=True)
            pass
        else:
            results.append([sys_uts, message])
    if results:
        df = pd.DataFrame(results, columns=['sys_uts', 'message'])
        #df.set_index('sys_uts', inplace=True)
    return df


class LogReader(object):
    """
    Read chunks from source
    """

    def __init__(self, source, cache_size=1024):
        self.closed = False
        self.cache_size = cache_size # read from pipe blocks waiting for equal block if cache size is large
        self.source = source
        self.buffer = ""

    def _read_chunk(self):
        data = self.source.read(self.cache_size)
        if data:
            parts = data.rsplit('\n', 1)
            if len(parts) > 1:
                ready_chunk = self.buffer + parts[0] + '\n'
                self.buffer = parts[1]
                return string_to_df(ready_chunk)
            else:
                self.buffer += parts[0]
        else:
            self.buffer += self.source.readline()
        return None

    def __iter__(self):
        while not self.closed:
            yield self._read_chunk()
        yield self._read_chunk()

    def close(self):
        self.closed = True
