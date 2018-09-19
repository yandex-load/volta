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

logger = logging.getLogger(__name__)


class VoltaBoxBinary(VoltaBox):
    """ VoltaBoxBinary - works with binary box, grabs data and stores data to queue """

    def __init__(self, config, core):
        VoltaBox.__init__(self, config, core)
        self.sample_rate = config.get_option('volta', 'sample_rate', 10000)
        self.baud_rate = config.get_option('volta', 'baud_rate', 230400)
        self.source_opener.baud_rate = self.baud_rate
        self.source_opener.read_timeout = self.grab_timeout
        self.data_source = self.source_opener()
        logger.debug('Data source initialized: %s', self.data_source)
        self.my_metrics = {}
        self.__create_my_metrics()

    def __create_my_metrics(self):
        self.my_metrics['current'] = self.core.data_session.new_metric(
            {
                'type': 'metrics',
                'name': 'current',
                'source': 'voltabox'
            }
        )

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
            self.my_metrics['current']
        )
        logger.info('Starting grab thread...')
        self.pipeline.start()
        logger.debug('Waiting grabber thread finish...')

    def end_test(self):
        try:
            self.reader.close()
        except AttributeError:
            logger.warning('VoltaBox has no Reader. Seems like VoltaBox initialization failed')
            logger.debug('VoltaBox has no Reader. Seems like VoltaBox initialization failed', exc_info=True)
        try:
            self.pipeline.close()
        except AttributeError:
            logger.warning('VoltaBox has no Pipeline. Seems like VoltaBox initialization failed')
        else:
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
            self.my_metrics['current']
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
        else:
            time.sleep(1)

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
