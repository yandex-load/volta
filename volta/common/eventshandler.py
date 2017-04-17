""" Event parser
"""
import queue as q
import logging
import re
import threading
import datetime


logger = logging.getLogger(__name__)


class EventsParser(threading.Thread):
    """
    reads source queue, parse message and sort events/sync messages to separate queues.
    
    Returns: puts (Timedata, parsed_message_dict) tuple into appropriate queue.
    """
    def __init__(self, source, events, sync):
        super(EventsParser, self).__init__()
        self.source = source
        self.events = events
        self.sync = sync
        self._finished = threading.Event()
        self._interrupted = threading.Event()

    def run(self):
        for _ in range(self.source.qsize()):
            try:
                df = self.source.get_nowait()
            except q.Empty:
                break
            else:
                for row in df.itertuples():
                    ts = row.ts
                    parsed_message = self.__parse_event(row.message)
                    if parsed_message['type'] == 'sync':
                        self.sync.put((ts, parsed_message))
                    else:
                        self.events.put((ts, parsed_message))
            if self._interrupted.is_set():
                break
        self._finished.set()

    def __parse_event(self, data):
        re_ = re.compile(r"""
            ^(?P<app>\S+)
            \s+
            \[[voltaVOLTA]\S+?\]
            \s+
            (?P<nanotime>\S+)
            \s+
            (?P<type>\S+)
            \s+
            (?P<tag>\S+)
            \s+
            (?P<message>.*?)
            $
            """, re.X
        )
        match = re_.match(data)
        if match:
            return match.groupdict()
        else:
            return {'message': data, 'type': 'unknown'}

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

    df = pd.DataFrame(test_data, columns=['ts', 'message'])
    phone_q.put(df)

    sync_q = q.Queue()
    events_q = q.Queue()
    events_worker = EventsParser(phone_q, events_q, sync_q)
    events_worker.run()
    for _ in range(events_q.qsize()):
        try:
            logger.info('Events: %s', events_q.get_nowait())
        except q.Empty:
            pass

    for _ in range(sync_q.qsize()):
        try:
            logger.info('Sync: %s', sync_q.get_nowait())
        except q.Empty:
            pass


if __name__ == "__main__":
    main()



