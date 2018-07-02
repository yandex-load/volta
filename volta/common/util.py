import threading
import pandas as pd
import numpy as np
import queue as q
import logging
import subprocess
import shlex
import time
import datetime
import queue
import re

from netort.data_processing import get_nowait_from_queue


logger = logging.getLogger(__name__)


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
            # exec_time_start = time.time()
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
                    df.loc[:, ('ts')] = pd.date_range(
                        current_ts, periods=len(ready_sample), freq=idx
                    ).astype(np.int64) // 1000
                    sample_num = sample_num + len(ready_sample)
                    yield df
            # logger.debug('Chopping took %s time', time.time() - exec_time_start)


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
    # data sample: [volta] 12345678 fragment TagFragment start
    # following regexp grabs 'nanotime', 'type', 'tag' and 'message' from sample above
    volta_custom_event = re.compile(
        r"""
            ^
            \[volta\]
            \s+
            (?P<nanotime>\S+)
            \s+
            (?P<custom_metric_type>\S+)
            \s+
            (?P<tag>\S+)
            \s+
            (?P<message>.*)
            $
        """, re.VERBOSE | re.IGNORECASE
    )

    def __init__(self, source, log_fmt_regexp, phone_type, cache_size=10):
        self.closed = False
        self.source = source
        self.log_fmt_regexp = log_fmt_regexp
        self.phone_type = phone_type
        self.buffer = []
        self.cache_size = cache_size
        self.log_uts_start = None
        self.sys_uts_start = None

    def _read_chunk(self):
        data = get_nowait_from_queue(self.source)
        if not data:
            time.sleep(1)
        else:
            ready_to_go_chunks = []
            for chunk in data:
                match = self.log_fmt_regexp.match(chunk)
                # we need this for multiline log entries concatenation
                if match:
                    if not self.buffer:
                        self.buffer.append(match.groupdict())
                    else:
                        ready_to_go_chunk = self.buffer.pop(0)
                        self.buffer.append(match.groupdict())
                        ready_to_go_chunks.append(ready_to_go_chunk)
                else:
                    if not self.buffer:
                        logger.warn('Trash data in logs, dropped data: \n%s', chunk)
                    else:
                        self.buffer[0]['value'] = self.buffer[0]['value'] + str(chunk)
            return ready_to_go_chunks

    def __iter__(self):
        while not self.closed:
            log_entries = self._read_chunk()
            if log_entries:
                for log_entry in log_entries:
                    # exec_time_start = time.time()
                    try:
                        ts = self.__parse_timestamp(log_entry, self.phone_type)
                        if ts:
                            if not self.sys_uts_start:
                                log_entry['ts'] = 0
                                self.sys_uts_start = ts
                            else:
                                log_entry['ts'] = ts - self.sys_uts_start
                        else:
                            logger.debug('Timestamp of log entry malformed? %s', log_entry)
                            continue
                    except ValueError:
                        continue
                    else:
                        log_entry = self.__parse_custom_message(log_entry)
                        log_entry['sys_uts'] = log_entry['ts']
                        log_entry['value'] = log_entry['value']\
                            .replace('\t', '__tab__') \
                            .replace('\n', '__nl__') \
                            .replace('\r', '') \
                            .replace('\f', '') \
                            .replace('\v', '')
                        df = pd.DataFrame(
                            data={
                                log_entry['ts']:
                                    log_entry
                            },
                        ).T
                        df.loc[:, ('value')] = df['value'].astype(np.str)
                        yield df
                    # logger.debug('log event parsing took %s time', time.time() - exec_time_start)
            else:
                time.sleep(0.5)

    @staticmethod
    def __parse_timestamp(log_entry, phone_type):
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
        try:
            ts = formatter[phone_type](log_entry)
        except (ValueError, IndexError):
            logger.debug('Malformed data in logs: %s', log_entry, exc_info=True)
            return
        else:
            return int((ts - datetime.datetime(1970, 1, 1)).total_seconds() * 10 ** 6)

    def __parse_custom_message(self, log_entry):
        """
        Parse event entry and modify
        """
        match = None
        try:
            if log_entry['value'] != '':
                match = self.volta_custom_event.match(log_entry['value'])
        except Exception:
            logger.debug('Unknown error in custom message parse: %s', exc_info=True)
            return log_entry
        else:
            if match:
                try:
                    # convert nanotime to us
                    log_ts = int(match.group('nanotime')) // 1000
                    log_entry['custom_metric_type'] = match.group('custom_metric_type')
                    log_entry['message'] = match.group('message')
                    log_entry['tag'] = match.group('tag')
                    # detect log ts start
                    if not self.log_uts_start:
                        self.log_uts_start = log_ts
                        logger.debug('log uts start detected: %s', self.log_uts_start)
                        log_entry['log_uts'] = 0
                        return log_entry
                    else:
                        log_entry['log_uts'] = int(log_ts - self.log_uts_start)
                        return log_entry
                except Exception:
                    logger.warning('Trash logtimestamp found: %s', log_entry)
            else:
                return log_entry

    def close(self):
        self.closed = True


def format_ts_from_android(log_entry):
    # android fmt, sample: 02-12 12:12:12.121
    return datetime.datetime.strptime(
        "{date} {time}".format(
            date=log_entry.get('date'),
            time=log_entry.get('time')
        ),
        '%m-%d %H:%M:%S.%f').replace(
            year=datetime.datetime.now().year
        )


def format_ts_from_iphone(log_entry):
    # iphone fmt, sample: Aug 25 18:48:14
    return datetime.datetime.strptime(
        "{month} {date} {time}".format(
            month=log_entry.get('month'),
            date=log_entry.get('date'),
            time=log_entry.get('time')
        ),
        '%b %d %H:%M:%S').replace(
        year=datetime.datetime.now().year
    )


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


# FIXME OLD JUNK
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
