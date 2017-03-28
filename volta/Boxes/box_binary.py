""" Binary Volta box
"""
import serial
import logging
import queue
import pandas as pd
import time
import numpy as np
import json
from volta.common.interfaces import VoltaBox
from volta.common.util import Drain, TimeChopper

logger = logging.getLogger(__name__)


class VoltaBoxBinary(VoltaBox):
    def __init__(self, config):
        VoltaBox.__init__(self, config)
        self.grab_timeout = config.get('grab_timeout', 1)
        self.device = config.get('device', '/dev/cu.wchusbserial1420')
        self.sample_rate = None
        self.baud_rate = 230400
        self.chop_ratio = config.get('chop_ratio', 1)
        self.volta_serial = serial.Serial(self.device, self.baud_rate, timeout=self.grab_timeout)
        logger.debug('serial initialized: %s', self.volta_serial)

    def start_test(self, results):
        """ handshake w/ device, get samplerate
            pipeline
                read serial data ->
                chop by samplerate w/ ratio ->
                make pandas DataFrame ->
                drain DataFrame to queue `results`
        Args:
            results: object answers to put() and get() methods

        Returns:
            puts pandas DataFrame to specified queue
        """

        # handshake
        while self.volta_serial.readline() != "VOLTAHELLO\n":
            pass

        volta_spec = json.loads(self.volta_serial.readline())
        self.sample_rate = volta_spec["sps"]
        logger.info('Sample rate handshake success: %s', self.sample_rate)

        # clean up dirty buffer
        while self.volta_serial.readline() != "DATASTART\n":
            pass

        self.pipeline = Drain(
            TimeChopper(
                BoxBinaryReader(
                    self.volta_serial, self.sample_rate
                ),
                self.sample_rate, self.chop_ratio
            ),
            results
        )
        logger.info('Starting grab thread')
        self.pipeline.start()
        logger.info('Waiting grabber thread finish...')

    def end_test(self):
        self.pipeline.close()
        self.volta_serial.close()


def string_to_np(data):
    start_time = time.time()
    chunk = np.fromstring(data, dtype=np.uint16).astype(np.float32)
    logger.debug("Chunk decode time: %.2fms", (time.time() - start_time) * 1000)
    return chunk


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
            if (len(data) % 2 != 0):
                self.orphan_byte = data[len(data)-1:]
                #logger.info('Orphan byte happened: %s', self.orphan_byte)
                data = data[:len(data)-1]
            return string_to_np(data)

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
    logger.info("Volta Binary Box")
    cfg = {
        'device': '/dev/cu.wchusbserial1420'
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