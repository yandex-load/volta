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
import queue


logger = logging.getLogger(__name__)


def popen(cmnd):
    return subprocess.Popen(
        cmnd,
        bufsize=0,
        close_fds=True,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.PIPE, )


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
                    # df.set_index('uts', inplace=True)
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


class Executioner(object):
    """ Process executioner and pipe reader """
    def __init__(
            self, cmd, terminate_if_errors=False, shell=False
    ):
        self.cmd = shlex.split(cmd)
        self.terminate_if_errors = terminate_if_errors
        self.process = None
        self.shell = shell
        self.out_queue = queue.Queue()
        self.errors_queue = queue.Queue()
        self.closed = False
        self.process_out_reader = None
        self.process_err_reader = None

    def execute(self):
        self.process = subprocess.Popen(
            self.cmd,
            shell=self.shell,
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            close_fds=True
        )
        self.process_out_reader = threading.Thread(
            target=self.__read_pipe, args=(self.process.stdout, self.out_queue)
        )
        self.process_out_reader.setDaemon(True)
        self.process_err_reader = threading.Thread(
            target=self.__read_pipe, args=(self.process.stderr, self.errors_queue)
        )
        self.process_err_reader.setDaemon(True)
        self.process_out_reader.start()
        self.process_err_reader.start()
        return self.out_queue, self.errors_queue

    def is_finished(self):
        return self.process.poll()

    def __read_pipe(self, source, destination):
        while not self.closed:
            try:
                data = source.readline()
            except ValueError:
                logger.warning('Executioner %s pipe unexpectedly closed: %s', self.cmd, source, exc_info=True)
                self.close()
            else:
                if data:
                    destination.put(data)
                else:
                    time.sleep(1)

    def close(self):
        if self.process:
            if self.process.poll() is None:
                logger.debug('Executioner got close signal, but the process \'%s\' is still alive, killing...', self.cmd)
                self.process.terminate()
                self.process.wait()
        self.closed = True
        self.process_out_reader.join()
        self.process_err_reader.join()


class LogParser(object):
    def __init__(self, source, regexp, type_, cache_size=10):
        self.closed = False
        self.source = source
        self.regexp = regexp
        self.type_ = type_
        self.buffer = []
        self.cache_size = cache_size

    def _read_chunk(self):
        try:
            data = self.source.get_nowait()
        except q.Empty:
            time.sleep(0.5)
        else:
            return prepare_logstring(data, self.regexp, self.type_)

    def __iter__(self):
        while not self.closed:
            while len(self.buffer) < self.cache_size:
                chunk = self._read_chunk()
                if chunk:
                    self.buffer.append(chunk)
            df = pd.DataFrame(self.buffer, columns=['sys_uts', 'message'], dtype=np.int64)
            self.buffer = []
            yield df

    def close(self):
        self.closed = True


def format_ts_from_android(match_):
    # android fmt, sample: 02-12 12:12:12.121
    return datetime.datetime.strptime("{date} {time}".format(
        date=match_.group('date'),
        time=match_.group('time')),
        '%m-%d %H:%M:%S.%f').replace(
        year=datetime.datetime.now().year
    )


def format_ts_from_iphone(match_):
    # iphone fmt, sample: Aug 25 18:48:14
    return datetime.datetime.strptime("{month} {date} {time}".format(
        month=match_.group('month'),
        date=match_.group('date'),
        time=match_.group('time')),
        '%b %d %H:%M:%S').replace(
        year=datetime.datetime.now().year
    )


def prepare_logstring(data, regexp, type_):
    """ split chunks by LF, parse contents and create dataframes

    Args:
        data (string): chunk of data read from source
    Returns:
        pandas.DataFrame, fmt: ['sys_uts', 'message']
    """
    formatter = {
        'android': format_ts_from_android,
        'iphone': format_ts_from_iphone
    }

    if data.startswith('---------'):
        return

    match = regexp.match(data)
    if match:
        # FIXME more flexible and stable logic should be here
        try:
            ts = formatter[type_](match)
        except (ValueError, IndexError):
            logger.warning('Trash data in logs: %s, skipped', match.groups())
            logger.debug('Trash data in logs: %s', data, exc_info=True)
            return
        # unix timestamp in microseconds
        sys_uts = int(
            (ts-datetime.datetime(1970, 1, 1)).total_seconds() * 10 ** 6
        )
        message = match.group('message')
        message = message\
            .replace('\t', '__tab__')\
            .replace('\n', '__nl__')\
            .replace('\r', '')\
            .replace('\f', '')\
            .replace('\v', '')
        return [sys_uts, message]
    else:
        logger.debug('Trash data in logs: %s', data)







######################
### OLD JUNK BELOW ###
######################
# FIXME


def chunk_to_df(chunk, regexp, type_):
    """ split chunks by LF, parse contents and create dataframes

    Args:
        chunk (string): chunk of data read from source
    Returns:
        pandas.DataFrame, fmt: ['sys_uts', 'message']
    """
    formatter = {
        'android': format_ts_from_android,
        'iphone': format_ts_from_iphone
    }

    results = []
    df = None
    for line in chunk.split('\n'):
        if line:
            if line.startswith('---------'):
                continue
            match = regexp.match(line)
            if match:
                # FIXME more flexible and stable logic should be here
                try:
                    ts = formatter[type_](match)
                except ValueError:
                    logger.warning('Trash data in logs: %s, skipped', match.groups())
                    logger.debug('Trash data in logs. Chunk: %s. Line: %s', chunk, line, exc_info=True)
                    continue
                # unix timestamp in microseconds
                sys_uts = int(
                    (ts-datetime.datetime(1970,1,1)).total_seconds() * 10 ** 6
                )
                message = match.group('message')
                message = message\
                    .replace('\t', '__tab__')\
                    .replace('\n', '__nl__')\
                    .replace('\r', '')\
                    .replace('\f', '')\
                    .replace('\v', '')
                results.append([sys_uts, message])
            else:
                logger.debug('Trash data in logs: %s', line)
    if results:
        df = pd.DataFrame(results, columns=['sys_uts', 'message'], dtype=np.int64)
    return df


def string_to_np(data, type=np.uint16, sep=""):
    chunk = np.fromstring(data, dtype=type, sep=sep)
    return chunk


class LogReader(object):
    """ Read chunks from source and make dataframes

    Attributes:
        cache_size (int): size of block to read from source
        source (string): path to data source

    Returns:
        pandas.DataFrame, fmt: ['sys_uts', 'message']
    """

    def __init__(self, source, regexp, type_, cache_size=1024):
        self.closed = False
        self.cache_size = cache_size
        self.source = source
        self.buffer = ""
        self.regexp = regexp
        self.type_ = type_

    def _read_chunk(self):
        data = self.source.read(self.cache_size)
        if data:
            parts = data.rsplit('\n', 1)
            if len(parts) > 1:
                ready_chunk = self.buffer + parts[0] + '\n'
                self.buffer = parts[1]
                return chunk_to_df(ready_chunk, self.regexp, self.type_)
            else:
                self.buffer += parts[0]
        else:
            self.buffer += self.source.readline()
        return None

    def __iter__(self):
        while not self.closed:
            yield self._read_chunk()
        # yield self._read_chunk()

    def close(self):
        self.closed = True
