import threading
import pandas as pd
import numpy as np
import queue as q
import logging
import subprocess
import os
import shlex
import time
import datetime


logger = logging.getLogger(__name__)


def popen(cmnd):
    return subprocess.Popen(
        cmnd,
        bufsize=0,
        preexec_fn=os.setsid,
        close_fds=True,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.PIPE, )


class Drain(threading.Thread):
    """
    Drain a generator to a destination that answers to put(), in a thread
    """

    def __init__(self, source, destination):
        super(Drain, self).__init__()
        self.source = source
        self.destination = destination
        self._finished = threading.Event()
        self._interrupted = threading.Event()

    def run(self):
        for item in self.source:
            self.destination.put(item)
            if self._interrupted.is_set():
                break
        self._finished.set()

    def wait(self, timeout=None):
        self._finished.wait(timeout=timeout)

    def close(self):
        self._interrupted.set()


class TimeChopper(object):
    """
    Group incoming chunks into dataframe by sample rate w/ chop_ratio
    adds utc timestamp from start test w/ offset and assigned frequency
    """

    def __init__(self, source, sample_rate, chop_ratio=1.0):
        self.source = source
        self.sample_rate = sample_rate
        self.buffer = np.array([])
        self.chop_ratio = chop_ratio
        self.slice_size = int(self.sample_rate*self.chop_ratio)

    def __iter__(self):
        logger.debug('Chopper slicing data w/ %s ratio, slice size will be %s', self.chop_ratio, self.slice_size)
        sample_num = 0
        for chunk in self.source:
            if chunk is not None:
                logger.debug('Chopper got %s data', len(chunk))
                self.buffer = np.append(self.buffer, chunk)
                while len(self.buffer) > self.slice_size:
                    ready_sample = self.buffer[:self.slice_size]
                    self.buffer = self.buffer[self.slice_size:]
                    df = pd.DataFrame(data=ready_sample, columns=['value'])
                    idx = "{value}{units}".format(
                        value = int(10 ** 6 / self.sample_rate),
                        units = "us"
                    )
                    # add time offset to start time in order to determine current timestamp and make date_range for df
                    current_ts = int((sample_num * (1./self.sample_rate)) * 10 ** 9)
                    df.loc[:, ('uts')] = pd.date_range(current_ts, periods=len(ready_sample), freq=idx).astype(np.int64) // 1000
                    #df.set_index('uts', inplace=True)
                    sample_num = sample_num + len(ready_sample)
                    yield df



def execute(cmd, shell=False, poll_period=1.0, catch_out=False):
    """
    Wrapper for Popen
    """
    log = logging.getLogger(__name__)
    log.debug("Starting: %s", cmd)

    stdout = ""
    stderr = ""

    if not shell and isinstance(cmd, basestring):
        cmd = shlex.split(cmd)

    if catch_out:
        process = subprocess.Popen(
            cmd,
            shell=shell,
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            close_fds=True)
    else:
        process = subprocess.Popen(cmd, shell=shell, close_fds=True)

    stdout, stderr = process.communicate()
    if stderr:
        log.error("There were errors:\n%s", stderr)

    if stdout:
        log.debug("Process output:\n%s", stdout)
    returncode = process.returncode
    log.debug("Process exit code: %s", returncode)
    return returncode, stdout, stderr


class Tee(threading.Thread):
    """
    Drain a queue and put its contents to list of destinations
    """

    def __init__(self, source, destination, type):
        super(Tee, self).__init__()
        self.source = source
        self.destination = destination
        self.type = type
        self._finished = threading.Event()
        self._interrupted = threading.Event()

    def run(self):
        while not self._interrupted.is_set():
            for _ in range(self.source.qsize()):
                try:
                    item = self.source.get_nowait()
                except q.Queue.empty:
                    break
                else:
                    for destination in self.destination:
                        destination.put(item, self.type)
                    if self._interrupted.is_set():
                        break
            if self._interrupted.is_set():
                break
            time.sleep(1)
        self._finished.set()

    def wait(self, timeout=None):
        self._finished.wait(timeout=timeout)

    def close(self):
        self._interrupted.set()


class LogReader(object):
    """ Read chunks from source and make dataframes

    Attributes:
        cache_size (int): size of block to read from source
        source (string): path to data source

    Returns:
        pandas.DataFrame, fmt: ['sys_uts', 'message']
    """

    def __init__(self, source, regexp, cache_size=1024):
        self.closed = False
        self.cache_size = cache_size #
        self.source = source
        self.buffer = ""
        self.regexp = regexp

    def _read_chunk(self):
        data = self.source.read(self.cache_size)
        if data:
            parts = data.rsplit('\n', 1)
            if len(parts) > 1:
                ready_chunk = self.buffer + parts[0] + '\n'
                self.buffer = parts[1]
                return chunk_to_df(ready_chunk, self.regexp)
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


def chunk_to_df(chunk, regexp):
    """ split chunks by LF, parse contents and create dataframes

    Args:
        chunk (string): chunk of data read from source
    Returns:
        pandas.DataFrame, fmt: ['sys_uts', 'message']
    """
    results = []
    df = None
    for line in chunk.split('\n'):
        if line:
            match = regexp.match(line)
            if match:
                ts = datetime.datetime.strptime("{date} {time}".format(
                        date=match.group('date'),
                        time=match.group('time')),
                    '%m-%d %H:%M:%S.%f').replace(
                    year=datetime.datetime.now().year
                )
                # unix timestamp in microseconds
                sys_uts = int(
                    (ts-datetime.datetime(1970,1,1)).total_seconds() * 10 ** 6
                )
                message = match.group('message')
                results.append([sys_uts, message])
            else:
                logger.debug('Trash data in logs: %s', line)
    if results:
        df = pd.DataFrame(results, columns=['sys_uts', 'message'], dtype=np.int64)
    return df


def string_to_np(data, type=np.uint16, sep=""):
    chunk = np.fromstring(data, dtype=type, sep=sep)
    return chunk
