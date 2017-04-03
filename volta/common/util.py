import threading
import pandas as pd
import logging
import numpy as np

box_columns = ['current']


logger = logging.getLogger(__name__)


class Drain(threading.Thread):
    """
    Drain a generator to a destination that answers to put(), in a thread
    """

    def __init__(self, source, destination):
        super(Drain, self).__init__()
        self.source = source
        self.destination = destination
        self._finished = threading.Event()
        self._interrupted = threading.Event()

    def run(self):
        for item in self.source:
            self.destination.put(item)
            if self._interrupted.is_set():
                break
        self._finished.set()

    def wait(self, timeout=None):
        self._finished.wait(timeout=timeout)

    def close(self):
        self._interrupted.set()


class TimeChopper(object):
    """
    Group incoming chunks into dataframe by sample rate w/ chop_ratio
    """

    def __init__(self, source, sample_rate, chop_ratio=1.0):
        self.source = source
        self.sample_rate = sample_rate
        self.buffer = np.array([])
        self.chop_ratio = chop_ratio
        self.slice_size = int(self.sample_rate*self.chop_ratio)

    def __iter__(self):
        logger.debug('Chopper slicing data w/ %s ratio, slice size will be %s', self.chop_ratio, self.slice_size)
        for chunk in self.source:
            if chunk is not None:
                logger.debug('Chopper got %s data', len(chunk))
                self.buffer = np.append(self.buffer, chunk)
                while len(self.buffer) > self.slice_size:
                    ready_sample = self.buffer[:self.slice_size]
                    to_buffer = self.buffer[self.slice_size:]
                    self.buffer = to_buffer
                    yield pd.DataFrame(data=ready_sample, columns=box_columns)