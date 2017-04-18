import threading
import pandas as pd
import logging
import numpy as np
import subprocess
import os
import shlex
import datetime

box_columns = ['current']


logger = logging.getLogger(__name__)

def popen(cmnd):
    return subprocess.Popen(
        cmnd,
        bufsize=0,
        preexec_fn=os.setsid,
        close_fds=True,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.PIPE, )


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
        start_time = datetime.datetime.utcnow()
        sample_num = 0
        for chunk in self.source:
            if chunk is not None:
                logger.debug('Chopper got %s data', len(chunk))
                self.buffer = np.append(self.buffer, chunk)
                while len(self.buffer) > self.slice_size:
                    ready_sample = self.buffer[:self.slice_size]
                    self.buffer = self.buffer[self.slice_size:]
                    df = pd.DataFrame(data=ready_sample, columns=box_columns)
                    idx = "{value}{units}".format(
                        value = int(10 ** 6 / self.sample_rate),
                        units = "us"
                    )
                    current_ts = start_time + datetime.timedelta(sample_num * (1./self.sample_rate))
                    df['ts'] = pd.date_range(current_ts, periods=len(ready_sample), freq=idx)
                    sample_num = sample_num + len(ready_sample)
                    yield df


def execute(cmd, shell=False, poll_period=1.0, catch_out=False):
    """
    Wrapper for Popen
    """
    log = logging.getLogger(__name__)
    log.debug("Starting: %s", cmd)

    stdout = ""
    stderr = ""

    if not shell and isinstance(cmd, basestring):
        cmd = shlex.split(cmd)

    if catch_out:
        process = subprocess.Popen(
            cmd,
            shell=shell,
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            close_fds=True)
    else:
        process = subprocess.Popen(cmd, shell=shell, close_fds=True)

    stdout, stderr = process.communicate()
    if stderr:
        log.error("There were errors:\n%s", stderr)

    if stdout:
        log.debug("Process output:\n%s", stdout)
    returncode = process.returncode
    log.debug("Process exit code: %s", returncode)
    return returncode, stdout, stderr
