""" 500Hz Volta Box
"""
import logging
import queue as q
import time

from volta.common.interfaces import VoltaBox
from volta.common.util import TimeChopper, string_to_np

from netort.data_processing import Drain
from netort.resource import manager as resource

logger = logging.getLogger(__name__)


class VoltaBox500Hz(VoltaBox):
    """ VoltaBox500Hz - works with plain-text 500hz box, grabs data and stores data to queue

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
        self.chop_ratio = config.get_option('volta', 'chop_ratio')
        self.sample_rate = config.get_option('volta', 'sample_rate', 500)
        self.baud_rate = config.get_option('volta', 'baud_rate', 115200)
        self.grab_timeout = config.get_option('volta', 'grab_timeout')
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
        +clean up dirty buffer

            pipeline
                read source data ->
                chop by samplerate w/ ratio ->
                make pandas DataFrame ->
                drain DataFrame to queue `results`
        """
        self.grabber_q = results

        # clean up dirty buffer
        for _ in range(self.sample_rate):
            self.data_source.readline()

        self.reader = BoxPlainTextReader(
            self.data_source, self.sample_rate
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


class BoxPlainTextReader(object):
    """
    Read chunks from source, convert and return numpy.array
    """

    def __init__(self, source, cache_size=1024 * 1024 * 10):
        self.closed = False
        self.cache_size = cache_size
        self.source = source
        self.buffer = ""

    def _read_chunk(self):
        data = self.source.read(self.cache_size)
        if data:
            parts = data.rsplit('\n', 1)
            if len(parts) > 1:
                ready_chunk = self.buffer + parts[0] + '\n'
                self.buffer = parts[1]
                return string_to_np(ready_chunk, type=float, sep='\n')
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


# ==================================================

def main():
    logging.basicConfig(
        level="DEBUG",
        format='%(asctime)s [%(levelname)s] [Volta 500hz] %(filename)s:%(lineno)d %(message)s')
    logger.info("Volta 500 hz box ")
    cfg = {
        'source': '/dev/cu.wchusbserial1420'
        # 'source': '/Users/netort/output.bin'
    }
    worker = VoltaBox500Hz(cfg)
    logger.info('worker args: %s', worker.__dict__)
    grabber_q = q.Queue()
    worker.start_test(grabber_q)
    time.sleep(10)
    logger.info('test finishing...')
    worker.end_test()
    logger.info('Queue size after test: %s', grabber_q.qsize())
    logger.info('1st sample:\n %s', grabber_q.get())
    logger.info('2nd sample:\n %s', grabber_q.get())
    logger.info('3rd sample:\n %s', grabber_q.get())
    logger.info('test finished')

if __name__ == "__main__":
    main()