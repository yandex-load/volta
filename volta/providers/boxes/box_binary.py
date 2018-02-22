""" Binary Volta box
"""
import logging
import Queue as queue
import time
import numpy as np
import json

from volta.common.interfaces import VoltaBox
from volta.common.util import TimeChopper, string_to_np

from netort.data_processing import Drain
from netort.resource import manager as resource

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
        self.source = config.get_option('volta', 'source')
        self.sample_rate = config.get_option('volta', 'sample_rate', 10000)
        self.chop_ratio = config.get_option('volta', 'chop_ratio')
        self.baud_rate = config.get_option('volta', 'baud_rate', 230400)
        self.grab_timeout = config.get_option('volta', 'grab_timeout')
        self.slope = config.get_option('volta', 'slope')
        self.offset = config.get_option('volta', 'offset')
        self.precision = config.get_option('volta', 'precision')
        self.power_voltage = config.get_option('volta', 'power_voltage')
        self.sample_swap = config.get_option('volta', 'sample_swap', False)
        # initialize data source
        try:
            self.source_opener = resource.get_opener(self.source)
        except:
            raise RuntimeError('Device %s not found. Please check VoltaBox USB connection', self.source)
        self.source_opener.baud_rate = self.baud_rate
        self.source_opener.read_timeout = self.grab_timeout
        self.data_source = self.source_opener()
        logger.debug('Data source initialized: %s', self.data_source)
        self.pipeline = None
        self.grabber_q = None
        self.process_currents = None

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
        self.grabber_q = results

        # handshake
        logger.info('Awaiting handshake')
        while self.data_source.readline() != "VOLTAHELLO\n":
            pass

        volta_spec = json.loads(self.data_source.readline())
        self.sample_rate = volta_spec["sps"]
        logger.info('Sample rate handshake success: %s', self.sample_rate)

        while self.data_source.readline() != "DATASTART\n":
            pass

        self.reader = BoxBinaryReader(
            self.data_source,
            self.sample_rate,
            self.slope,
            self.offset,
            self.power_voltage,
            self.precision,
            sample_swap=self.sample_swap
        )
        self.pipeline = Drain(
            TimeChopper(
                self.reader, self.sample_rate, self.chop_ratio
            ),
            self.grabber_q
        )
        logger.info('Starting grab thread...')
        self.pipeline.start()
        logger.debug('Waiting grabber thread finish...')

    def end_test(self):
        self.reader.close()
        self.pipeline.close()
        self.pipeline.join(10)
        self.data_source.close()

    def get_info(self):
        data = {}
        if self.pipeline:
            data['grabber_alive'] = self.pipeline.isAlive()
        if self.grabber_q:
            data['grabber_queue_size'] = self.grabber_q.qsize()
        return data


class VoltaBoxStm32(VoltaBoxBinary):
    """
    Same as VoltaBoxBinary, but doesn't wait for handshake
    """
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
        self.grabber_q = results

        self.reader = BoxBinaryReader(
            self.data_source,
            self.sample_rate,
            self.slope,
            self.offset,
            self.power_voltage,
            self.precision
        )
        self.pipeline = Drain(
            TimeChopper(
                self.reader, self.sample_rate, self.chop_ratio
            ),
            self.grabber_q
        )
        logger.info('Starting grab thread...')
        self.pipeline.start()
        logger.debug('Waiting grabber thread finish...')

class BoxBinaryReader(object):
    """
    Read chunks from source, convert and return numpy.array
    """

    def __init__(self, source, sample_rate, slope=1, offset=0, power_voltage=4700, precision=10, sample_swap=False):
        self.closed = False
        self.source = source
        self.sample_rate = sample_rate
        self.buffer = ""
        self.orphan_byte = None
        self.slope = slope
        self.offset = offset
        self.precision = precision
        self.power_voltage = float(power_voltage)
        self.swap = False
        self.sample_swap = sample_swap

    def __sample_swap(self, data):
        lst = list(data)
        for i in range(len(lst)/2):
            lo = ord(lst[i*2])
            hi = ord(lst[i*2+1])
            word = (hi << 8) + lo
            if word>0x0FFF or (self.swap and (word&0x00F0)==0):
                self.swap = True
                tmp = lst[i*2]
                lst[i*2] = lst[i*2+1]
                lst[i*2+1] = tmp
            else:
                self.swap = False
        data = ''.join(lst)
        return data
    
    def _read_chunk(self):
        data = self.source.read(self.sample_rate * 2 * 10)
        if data:
            if self.orphan_byte:
                data = self.orphan_byte + data
                self.orphan_byte = None
            if len(data) % 2 != 0:
                self.orphan_byte = data[-1:]
                data = data[:-1]
            if self.sample_swap:
                data = self.__sample_swap(data)
            chunk = string_to_np(data).astype(np.float32) * (
                self.power_voltage / (2 ** self.precision)) * self.slope + self.offset
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
