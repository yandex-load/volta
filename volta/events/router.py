""" Events router - phone custom messsage parser and router
"""
import queue as q
import logging
import re
import threading
import time
import numpy as np


logger = logging.getLogger(__name__)


# data sample: lightning: [volta] 12345678 fragment TagFragment start
# following regexp grabs 'app name', 'nanotime', 'type', 'tag' and 'message' from sample above
re_ = re.compile(r"""
    ^(?P<app>\S+)
    \s+
    \[volta\]
    \s+
    (?P<nanotime>\S+)
    \s+
    (?P<type>\S+)
    \s+
    (?P<tag>\S+)
    \s+
    (?P<message>.*)
    $
    """, re.VERBOSE | re.IGNORECASE
)


class EventsRouter(threading.Thread):
    """
    reads source queue, parse message and sort events/sync messages to separate queues.

    Returns: puts df into appropriate destination queue.
    """
    def __init__(self, source, destination):
        super(EventsRouter, self).__init__()
        self.source = source
        self.router = destination
        self._finished = threading.Event()
        self._interrupted = threading.Event()
        self.log_uts_start = None
        self.sys_uts_start = None

    def run(self):
        while not self._interrupted.is_set():
            for _ in range(self.source.qsize()):
                try:
                    df = self.source.get_nowait()
                    # detect syslog ts start
                    if not self.sys_uts_start:
                        self.sys_uts_start = df.sys_uts[0]
                        logger.debug('sys uts start detected: %s', self.sys_uts_start)
                except q.Empty:
                    break
                else:
                    if df is not None:
                        self.__route_data(df)
                if self._interrupted.is_set():
                    break
            time.sleep(1)
            if self._interrupted.is_set():
                break
        self._finished.set()

    def __route_data(self, df):
        """
        Group data by 'type' and send it to listeners
        Args:
            df: pandas dataframe w/ phone events

        Returns:
            put data to listeners

        """
        for dtype, data in df.apply(self.__parse_event, axis=1).groupby('type'):
            if dtype in self.router:
                if dtype == 'metric':
                    data.loc[:, ('value')] = data.message.astype(np.float64)
                if dtype != 'unknown':
                    data.loc[:, ('log_uts')] = data.log_uts.astype(np.int64)
                data.loc[:, ('sys_uts')] = data.sys_uts.map(lambda x: ((x - self.sys_uts_start)))
                [listener.put(data, dtype) for listener in self.router[dtype]]
            else:
                logger.warning('Unknown event type! %s. Message: %s', type, data, exc_info=True)


    def __parse_event(self, row):
        """
        Parse event entry and modify
        """
        row.message = row.message.replace('\t', '__tab__')
        match = re_.match(row.message)
        if match:
            row["app"] = match.group('app')
            try:
                # convert nanotime to us
                log_ts = int(match.group('nanotime')) // 1000
                # detect log ts start
                if not self.log_uts_start:
                    self.log_uts_start = log_ts
                    logger.debug('log uts start detected: %s', self.log_uts_start)
                    row["log_uts"] = 0
                else:
                    row["log_uts"] = int(log_ts - self.log_uts_start)
            except:
                logger.warning('Trash logtimestamp found: %s', row)
            row["type"] = match.group('type')
            row["tag"] = match.group('tag')
            row["message"] = match.group('message')
        else:
            row["type"] = 'unknown'
            row["message"] = row.message
        return row

    def wait(self, timeout=None):
        self._finished.wait(timeout=timeout)

    def close(self):
        self._interrupted.set()
