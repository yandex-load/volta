""" Event parser
"""
import queue as q
import logging
import re
import threading
import time


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


class EventsParser(threading.Thread):
    """
    reads source queue, parse message and sort events/sync messages to separate queues.

    Returns: puts df into appropriate destination queue.
    """
    def __init__(self, source, events, sync):
        super(EventsParser, self).__init__()
        self.source = source
        self.destination = {
            'sync': sync,
            'event': events,
            'metric': events,
            'fragment': events,
            'unknown': events,
        }
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
                        self.sys_uts_start = df.index[0]
                        logger.debug('sys uts start detected: %s', self.sys_uts_start)
                except q.Empty:
                    break
                else:
                    if df is not None:
                        for type, data in df.apply(self.__parse_event, axis=1).groupby('type'):
                            if type in self.destination:
                                data.index = data.index.map(lambda x: ((x - self.sys_uts_start)))
                                data.index.name = 'sys_uts'
                                self.destination[type].put(data)
                            else:
                                logger.warning('Unknown event type! %s. Message: %s', type, data, exc_info=True)
                if self._interrupted.is_set():
                    break
            time.sleep(1)
            if self._interrupted.is_set():
                break
        self._finished.set()

    def __parse_event(self, row):
        match = re_.match(row.message)
        if match:
            row["app"] = match.group('app')
            try:
                # convert nanotime to us
                log_ts = int(int(match.group('nanotime')) // 1000)

                # detect log ts start
                if not self.log_uts_start:
                    self.log_uts_start = log_ts
                    logger.debug('log uts start detected: %s', self.log_uts_start)
                    row["log_uts"] = 0
                else:
                    row["log_uts"] = log_ts - self.log_uts_start
            except:
                logger.warning('Trash logtimestamp found: %s', row)
            row["type"] = match.group('type')
            row["tag"] = match.group('tag')
            row["message"] = match.group('message')
            return row
        else:
            row["type"] = 'unknown'
            row["tag"] = None
            row["log_uts"] = None
            row["app"] = None
            row["message"] = row.message
            return row

    def wait(self, timeout=None):
        self._finished.wait(timeout=timeout)

    def close(self):
        self._interrupted.set()




# =====================================
def main():
    import argparse
    parser = argparse.ArgumentParser(description='')
    parser.add_argument('--debug', dest='debug', action='store_true', default=False)
    args = parser.parse_args()

    logging.basicConfig(
        level="DEBUG" if args.debug else "INFO",
        format='%(asctime)s [%(levelname)s] [Volta EventsHandler] %(filename)s:%(lineno)d %(message)s')
    logger.info("Volta EventsHandler init")

    phone_q = q.Queue()
    import datetime
    import pandas as pd

    # test data:
    test_data = []
    # message for EventParser - common       message
    test_data.append([datetime.datetime.now(), 'MessageEventParserCommon data'])
    # message for EventParser - uncommon:    app: [volta] {nt} event {tag} {message}
    test_data.append([datetime.datetime.now(), 'lightning: [volta] 12345678 event TagEventUncommon MessageEventParserUncommon data'])
    # message for MetricParser:              app: [volta] {nt} metric {tag} {message}
    test_data.append([datetime.datetime.now(), 'lightning: [volta] 12345678 metric TagMetric MessageMetricParser data'])
    # messages for FragmentParser:           app: [volta] {nt} fragment {tag} {start/stop}
    test_data.append([datetime.datetime.now(), 'lightning: [volta] 12345678 fragment TagFragment start'])
    test_data.append([datetime.datetime.now(), 'lightning: [volta] 12345678 fragment TagFragment stop'])
    # message for SyncParser                 app: [volta] {nt} sync {tag} {rise/fall}
    test_data.append([datetime.datetime.now(), 'lightning: [VOLTA] 12345678 sync TagSync rise'])
    test_data.append([datetime.datetime.now(), 'lightning: [volta] 12345678 sync TagSync fall'])
    # wrong type
    test_data.append([datetime.datetime.now(), 'Brokenlightning: [VOLTA] 12345678 syncbroken TagSyncBroken riseBroken'])

    df = pd.DataFrame(test_data, columns=['ts', 'message'])
    phone_q.put(df)

    sync_q = q.Queue()
    events_q = q.Queue()
    events_worker = EventsParser(phone_q, events_q, sync_q)
    events_worker.run()
    for _ in range(events_q.qsize()):
        try:
            logger.info('Events sample:\n %s', events_q.get_nowait())
        except q.Empty:
            pass

    for _ in range(sync_q.qsize()):
        try:
            logger.info('Sync sample:\n %s', sync_q.get_nowait())
        except q.Empty:
            pass


if __name__ == "__main__":
    main()



