""" Binary Volta box
"""
import logging
import Queue as queue
import time
import numpy as np
import json

from volta.common.interfaces import VoltaBox
from volta.common.util import Drain, TimeChopper, string_to_np
from volta.common.resource import manager as resource

logger = logging.getLogger(__name__)


class VoltaBoxBinary(VoltaBox):
    """ VoltaBoxBinary - works with binary box, grabs data and stores data to queue

    Attributes:
        source (string): path to data source, should be able to be opened by resource manager
            may be url, e.g. 'http://myhost.tld/path/to/file'
            may be device, e.g. '/dev/cu.wchusbserial1420'
            may be path to file, e.g. '/home/users/netort/path/to/file.data'
        sample_rate (int): volta box sample rate - depends on software and which type of volta box you use
        chop_ratio (int): chop ratio for incoming data, 1 means 1 second (500 for sample_rate 500)
        baud_rate (int): baud rate for device if device specified in source
        grab_timeout (int): timeout for grabber
    """
    def __init__(self, config):
        VoltaBox.__init__(self, config)
        self.source = config.get('source', '/dev/cu.wchusbserial1420')
        self.sample_rate = config.get('sample_rate', 10000)
        self.chop_ratio = config.get('chop_ratio', 1)
        self.baud_rate = config.get('baud_rate', 230400)
        self.grab_timeout = config.get('grab_timeout', 1)
        # initialize data source
        self.source_opener = resource.get_opener(self.source)
        self.source_opener.baud_rate = self.baud_rate
        self.source_opener.read_timeout = self.grab_timeout
        self.data_source = self.source_opener()
        logger.debug('Data source initialized: %s', self.data_source)

    def start_test(self, results):
        """ Grab stage - starts grabber thread and puts data to results queue
        + handshake w/ device, get samplerate

            pipeline
                read source data ->
                chop by samplerate w/ ratio ->
                make pandas DataFrame ->
                drain DataFrame to queue `results`

        Args:
            results: object answers to put() and get() methods
        """

        # handshake
        while self.data_source.readline() != "VOLTAHELLO\n":
            pass

        volta_spec = json.loads(self.data_source.readline())
        self.sample_rate = volta_spec["sps"]
        logger.info('Sample rate handshake success: %s', self.sample_rate)

        while self.data_source.readline() != "DATASTART\n":
            pass

        self.reader = BoxBinaryReader(
            self.data_source, self.sample_rate
        )
        self.pipeline = Drain(
            TimeChopper(
                self.reader, self.sample_rate, self.chop_ratio
            ),
            results
        )
        logger.info('Starting grab thread...')
        self.pipeline.start()
        logger.debug('Waiting grabber thread finish...')

    def end_test(self):
        self.reader.close()
        self.pipeline.close()
        self.pipeline.join(10)
        self.data_source.close()


class BoxBinaryReader(object):
    """
    Read chunks from source, convert and return numpy.array
    """

    def __init__(self, source, sample_rate):
        self.closed = False
        self.source = source
        self.sample_rate = sample_rate
        self.buffer = ""
        self.orphan_byte = None

    def _read_chunk(self):
        data = self.source.read(self.sample_rate * 2 * 10)
        if data:
            if self.orphan_byte:
                data = self.orphan_byte+data
                self.orphan_byte = None
            if (len(data) % 2 != 0):
                self.orphan_byte = data[-1:]
                data = data[:-1]
            chunk = string_to_np(data).astype(np.float32)
            return chunk

    def __iter__(self):
        while not self.closed:
            yield self._read_chunk()
        yield self._read_chunk()

    def close(self):
        self.closed = True


# ==================================================

def main():
    logging.basicConfig(
        level="DEBUG",
        format='%(asctime)s [%(levelname)s] [Volta Binary] %(filename)s:%(lineno)d %(message)s')
    logger.info("Volta Binary Box")
    cfg = {
        'source': '/dev/cu.wchusbserial1420',
        # 'sample_rate': 1000
    }
    worker = VoltaBoxBinary(cfg)
    logger.info('worker args: %s', worker.__dict__)
    q = queue.Queue()
    worker.start_test(q)
    time.sleep(15)
    logger.info('test finishing...')
    worker.end_test()
    logger.info('Queue size after test: %s', q.qsize())
    logger.info('Sample: %s', q.get())
    logger.info('test finished')

if __name__ == "__main__":
    main()